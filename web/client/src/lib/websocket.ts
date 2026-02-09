import { CONFIG } from '@/config';

type EventHandler = (data: any) => void;

class WebSocketService {
    private socket: WebSocket | null = null;
    private listeners: Map<string, EventHandler[]> = new Map();
    private reconnectTimer: NodeJS.Timeout | null = null;
    private userId: string | null = null;

    constructor() { }

    connect(userId: string) {
        if (this.socket?.readyState === WebSocket.OPEN) return;

        this.userId = userId;

        // Lógica de URL idéntica a tu SocketContext para consistencia
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsBase = CONFIG.WS_BASE_URL.replace(/^ws(s)?:/, protocol);
        const cleanWsBase = wsBase.endsWith('/ws') ? wsBase : `${wsBase}/ws`;
        const url = `${cleanWsBase}/${userId}`;

        console.log(`[WS-Lib] Connecting to ${url}`);
        this.socket = new WebSocket(url);

        this.socket.onopen = () => {
            console.log('[WS-Lib] Connected');
            this.emit('connected', { status: 'connected' });
            if (this.reconnectTimer) {
                clearTimeout(this.reconnectTimer);
                this.reconnectTimer = null;
            }
        };

        this.socket.onmessage = (event) => {
            try {
                const message = JSON.parse(event.data);
                // Emite el evento específico si viene en el formato { event: '...', data: ... }
                if (message.event) {
                    this.emit(message.event, message.data);
                }
                // También emite un evento genérico 'message'
                this.emit('message', message);
            } catch (e) {
                console.error('[WS-Lib] Parse error', e);
            }
        };

        this.socket.onclose = (event) => {
            console.log(`[WS-Lib] Desconectado: ${event.code}`);
            this.socket = null;
            this.emit('disconnected', {});

            // Reintento de conexión automática si hay usuario
            if (this.userId && !this.reconnectTimer) {
                this.reconnectTimer = setTimeout(() => {
                    if (this.userId) this.connect(this.userId);
                }, 5000);
            }
        };

        this.socket.onerror = (err) => {
            console.error('[WS-Lib] Error', err);
        };
    }

    disconnect() {
        this.userId = null;
        if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
        this.socket?.close();
        this.socket = null;
    }

    send(data: any) {
        if (this.socket?.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify(data));
        } else {
            console.warn('[WS-Lib] Cannot send, socket not open');
        }
    }

    on(event: string, handler: EventHandler) {
        if (!this.listeners.has(event)) {
            this.listeners.set(event, []);
        }
        this.listeners.get(event)?.push(handler);
    }

    off(event: string, handler: EventHandler) {
        const handlers = this.listeners.get(event);
        if (handlers) {
            this.listeners.set(event, handlers.filter(h => h !== handler));
        }
    }

    private emit(event: string, data: any) {
        const handlers = this.listeners.get(event);
        handlers?.forEach(h => h(data));
    }
}

export const wsService = new WebSocketService();