/**
 * Centralized configuration for the frontend.
 * Uses environment variables where available, with sane local defaults.
 */

export const CONFIG = {
    // Port for the Python API (legacy/local fallback)
    API_PORT: (import.meta as any).env?.VITE_API_PORT || "8000",

    // Base URL for API.
    // - Local (vite dev/proxy): default "/api"
    // - Deploy estático: definir VITE_API_BASE_URL, p.ej. "https://signalkey-platform.onrender.com/api"
    get API_BASE_URL() {
        const fromEnv = (import.meta as any).env?.VITE_API_BASE_URL;
        if (fromEnv && String(fromEnv).trim().length > 0) {
            return String(fromEnv).replace(/\/$/, '');
        }
        return "/api";
    },

    // WebSocket URL
    get WS_BASE_URL() {
        if ((import.meta as any).env?.VITE_WS_URL) {
            return (import.meta as any).env.VITE_WS_URL;
        }

        // Si API_BASE_URL es absoluto, construir WS en ese host.
        const apiBase = this.API_BASE_URL;
        if (/^https?:\/\//i.test(apiBase)) {
            const u = new URL(apiBase);
            const wsProto = u.protocol === 'https:' ? 'wss:' : 'ws:';
            return `${wsProto}//${u.host}/ws`;
        }

        // Fallback local same-host
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        return `${protocol}//${window.location.host}/ws`;
    },

    // Alias for backward compatibility
    get API_URL() {
        return this.API_BASE_URL;
    },
};
