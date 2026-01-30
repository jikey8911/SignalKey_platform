declare module 'http-proxy' {
    import { IncomingMessage, ServerResponse } from 'http';
    import { Server } from 'http';

    interface ProxyServerOptions {
        target?: string;
        changeOrigin?: boolean;
        ws?: boolean;
    }

    interface ProxyServer {
        web(req: IncomingMessage, res: ServerResponse): void;
        ws(req: IncomingMessage, socket: any, head: any, options?: any): void;
        on(event: string, handler: (...args: any[]) => void): void;
    }

    function createProxyServer(options?: ProxyServerOptions): ProxyServer;

    export default { createProxyServer };
}
