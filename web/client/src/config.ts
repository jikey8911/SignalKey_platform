/**
 * Centralized configuration for the frontend.
 * Uses environment variables where available, with sane local defaults.
 */

export const CONFIG = {
    // Port for the Python API
    API_PORT: (import.meta as any).env?.VITE_API_PORT || "8000",

    // Base URL for the Python API
    // We point to /api to use the Express proxy, which handles Auth and CORS
    get API_BASE_URL() {
        return "/api";
    },

    // WebSocket URL
    get WS_BASE_URL() {
        if ((import.meta as any).env?.VITE_WS_URL) {
            return (import.meta as any).env.VITE_WS_URL;
        }

        // Default to same host but different protocol and /ws path
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        return `${protocol}//${window.location.host}/ws`;
    },

    // Alias for backward compatibility
    get API_URL() {
        return this.API_BASE_URL;
    },
};
