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
    const pingIntervalRef = useRef<NodeJS.Timeout | null>(null);

    const connect = useCallback(() => {
        if (!user?.openId) return;

        // Evitar crear múltiples conexiones si ya existe una activa o conectando
        if (socketRef.current && (socketRef.current.readyState === WebSocket.OPEN || socketRef.current.readyState === WebSocket.CONNECTING)) {
            return;
        }

        // Determinar la URL del WebSocket
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsBase = CONFIG.WS_BASE_URL.replace(/^ws(s)?:/i, protocol);

        // Normalizar para evitar dobles // y duplicar /ws
        const normalizedBase = wsBase.replace(/\/+$/, '');
        const baseWithoutWs = normalizedBase.replace(/\/ws$/i, '');
        const wsUrl = `${baseWithoutWs}/ws/${user.openId}`;

        console.log(`[WebSocket] Intentando conectar: ${wsUrl}`);
        const socket = new WebSocket(wsUrl);
        socketRef.current = socket;

        socket.onopen = () => {
            console.log('[WebSocket] Conectado');
            setIsConnected(true);
            if (reconnectTimeoutRef.current) {
                clearTimeout(reconnectTimeoutRef.current);
                reconnectTimeoutRef.current = null;
            }

            // Keepalive ping (helps prevent idle disconnects)
            if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);
            pingIntervalRef.current = setInterval(() => {
                try {
                    if (socket.readyState === WebSocket.OPEN) {
                        socket.send(JSON.stringify({ action: 'PING' }));
                    }
                } catch (e) {
                    // ignore
                }
            }, 20000);
        };

        socket.onmessage = (event) => {
            try {
                const message: SocketMessage = JSON.parse(event.data);
                setLastMessage(message);
            } catch (e) {
                console.error('[WebSocket] Error parseando mensaje', e);
            }
        };

        socket.onclose = (event) => {
            console.log(`[WebSocket] Desconectado: ${event.code} ${event.reason}`);
            setIsConnected(false);
            if (pingIntervalRef.current) {
                clearInterval(pingIntervalRef.current);
                pingIntervalRef.current = null;
            }

            // Solo reconectar si el cierre no fue intencional y el usuario sigue autenticado
            if (socketRef.current === socket && user?.openId) {
                socketRef.current = null;
                if (!reconnectTimeoutRef.current) {
                    console.log('[WebSocket] Programando reconexión en 5s...');
                    reconnectTimeoutRef.current = setTimeout(() => {
                        reconnectTimeoutRef.current = null;
                        connect();
                    }, 5000);
                }
            }
        };

        socket.onerror = (error) => {
            console.error('[WebSocket] Error:', error);
            socket.close();
        };
    }, [user?.openId]);

    useEffect(() => {
        if (user?.openId) {
            connect();
        }

        return () => {
            if (reconnectTimeoutRef.current) {
                clearTimeout(reconnectTimeoutRef.current);
                reconnectTimeoutRef.current = null;
            }
            if (pingIntervalRef.current) {
                clearInterval(pingIntervalRef.current);
                pingIntervalRef.current = null;
            }

            if (socketRef.current) {
                console.log('[WebSocket] Cerrando por limpieza');
                const socketToClose = socketRef.current;
                socketRef.current = null;
                socketToClose.close();
            }
        };
    }, [user?.openId]);

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
