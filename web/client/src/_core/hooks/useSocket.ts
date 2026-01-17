import { useEffect, useRef, useState, useCallback } from 'react';

interface SocketMessage {
    event: string;
    data: any;
}

export function useSocket(userId: string | undefined) {
    const socketRef = useRef<WebSocket | null>(null);
    const [isConnected, setIsConnected] = useState(false);
    const [lastMessage, setLastMessage] = useState<SocketMessage | null>(null);
    const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

    const connect = useCallback(() => {
        if (!userId) return;

        // Determinar la URL del WebSocket basándose en la ubicación actual
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        // Usar 127.0.0.1 en lugar de localhost para evitar problemas de IPv6 vs IPv4
        const host = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
            ? '127.0.0.1:8000'
            : `${window.location.hostname}:8000`;
        const wsUrl = `${protocol}//${host}/ws/${userId}`;

        console.log(`Intentando conectar a WebSocket: ${wsUrl}`);
        const socket = new WebSocket(wsUrl);

        socket.onopen = () => {
            console.log('WebSocket Conectado');
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
                console.error('Error parseando mensaje de WebSocket', e);
            }
        };

        socket.onclose = () => {
            console.log('WebSocket Desconectado');
            setIsConnected(false);
            // Intento de reconexión tras 5 segundos
            reconnectTimeoutRef.current = setTimeout(() => {
                connect();
            }, 5000);
        };

        socket.onerror = (error) => {
            console.error('WebSocket Error:', error);
            socket.close();
        };

        socketRef.current = socket;
    }, [userId]);

    useEffect(() => {
        connect();
        return () => {
            if (socketRef.current) {
                socketRef.current.close();
            }
            if (reconnectTimeoutRef.current) {
                clearTimeout(reconnectTimeoutRef.current);
            }
        };
    }, [connect]);

    const sendMessage = (message: any) => {
        if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
            socketRef.current.send(JSON.stringify(message));
        }
    };

    return { isConnected, lastMessage, sendMessage };
}
