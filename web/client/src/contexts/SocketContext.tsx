import React, { createContext, useContext, useEffect, useRef, useState, useCallback, ReactNode } from 'react';
import { useAuth } from '@/_core/hooks/useAuth';

interface SocketMessage {
    event: string;
    data: any;
}

interface SocketContextType {
    isConnected: boolean;
    lastMessage: SocketMessage | null;
    sendMessage: (message: any) => void;
}

const SocketContext = createContext<SocketContextType | undefined>(undefined);

export function SocketProvider({ children }: { children: ReactNode }) {
    const { user } = useAuth();
    const socketRef = useRef<WebSocket | null>(null);
    const [isConnected, setIsConnected] = useState(false);
    const [lastMessage, setLastMessage] = useState<SocketMessage | null>(null);
    const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

    const connect = useCallback(() => {
        if (!user?.openId) return;

        // Determinar la URL del WebSocket basándose en la ubicación actual
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
            ? '127.0.0.1:8000'
            : `${window.location.hostname}:8000`;
        const wsUrl = `${protocol}//${host}/ws/${user.openId}`;

        console.log(`Intentando conectar a WebSocket Global: ${wsUrl}`);
        const socket = new WebSocket(wsUrl);

        socket.onopen = () => {
            console.log('WebSocket Global Conectado');
            setIsConnected(true);
            if (reconnectTimeoutRef.current) {
                clearTimeout(reconnectTimeoutRef.current);
                reconnectTimeoutRef.current = null;
            }
        };

        socket.onmessage = (event) => {
            try {
                const message: SocketMessage = JSON.parse(event.data);
                setLastMessage(message);
            } catch (e) {
                console.error('Error parseando mensaje de WebSocket Global', e);
            }
        };

        socket.onclose = () => {
            console.log('WebSocket Global Desconectado');
            setIsConnected(false);
            // Intento de reconexión tras 5 segundos
            reconnectTimeoutRef.current = setTimeout(() => {
                connect();
            }, 5000);
        };

        socket.onerror = (error) => {
            console.error('WebSocket Global Error:', error);
            socket.close();
        };

        socketRef.current = socket;
    }, [user?.openId]);

    useEffect(() => {
        if (user?.openId) {
            connect();
        }
        return () => {
            if (socketRef.current) {
                console.log('Cerrando WebSocket Global por desmontaje');
                socketRef.current.close();
            }
            if (reconnectTimeoutRef.current) {
                clearTimeout(reconnectTimeoutRef.current);
            }
        };
    }, [user?.openId, connect]);

    const sendMessage = useCallback((message: any) => {
        if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
            socketRef.current.send(JSON.stringify(message));
        }
    }, []);

    return (
        <SocketContext.Provider value={{ isConnected, lastMessage, sendMessage }}>
            {children}
        </SocketContext.Provider>
    );
}

export function useSocketContext() {
    const context = useContext(SocketContext);
    if (context === undefined) {
        throw new Error('useSocketContext must be used within a SocketProvider');
    }
    return context;
}
