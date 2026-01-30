import React, { createContext, useContext, useEffect, useRef, useState, useCallback, ReactNode } from 'react';
import { useAuth } from '@/_core/hooks/useAuth';
import { CONFIG } from '@/config';

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

        // Evitar crear múltiples conexiones si ya existe una activa o conectando
        if (socketRef.current && (socketRef.current.readyState === WebSocket.OPEN || socketRef.current.readyState === WebSocket.CONNECTING)) {
            console.log('WebSocket ya está conectado o conectando, evitando duplicado');
            return;
        }

        // Determinar la URL del WebSocket basándose en la ubicación actual
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        // Usar CONFIG.WS_BASE_URL pero asegurar que el protocolo sea correcto si es wss
        const wsBase = CONFIG.WS_BASE_URL.replace(/^ws(s)?:/, protocol);
        const wsUrl = `${wsBase}/ws/${user.openId}`;

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

            // Check if this socket is still the current one. If socketRef.current is null, it means we closed it intentionally.
            if (socketRef.current === socket) {
                socketRef.current = null;

                // Solo reconectar si el usuario sigue autenticado
                if (user?.openId && !reconnectTimeoutRef.current) {
                    console.log('Programando reconexión en 5 segundos...');
                    reconnectTimeoutRef.current = setTimeout(() => {
                        reconnectTimeoutRef.current = null;
                        connect();
                    }, 5000);
                }
            }
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
            // Limpiar timeout de reconexión
            if (reconnectTimeoutRef.current) {
                clearTimeout(reconnectTimeoutRef.current);
                reconnectTimeoutRef.current = null;
            }

            // Cerrar socket si existe
            if (socketRef.current) {
                console.log('Cerrando WebSocket Global por desmontaje');
                const socketToClose = socketRef.current;
                socketRef.current = null; // Mark as null BEFORE closing so onclose knows it was intentional
                socketToClose.close();
            }
        };
    }, [user?.openId]); // Removido 'connect' de las dependencias para evitar ciclos

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
