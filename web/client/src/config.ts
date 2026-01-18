/**
 * Centralized configuration for the frontend.
 * Uses environment variables where available, with sane local defaults.
 */

export const CONFIG = {
    // Port for the Python API
    API_PORT: (import.meta as any).env?.VITE_API_PORT || "8000",

    // Base URL for the Python API
    get API_BASE_URL() {
        return (import.meta as any).env?.VITE_API_URL || `http://localhost:${this.API_PORT}`;
    },

    // WebSocket URL
    get WS_BASE_URL() {
        return (import.meta as any).env?.VITE_WS_URL || this.API_BASE_URL.replace(/^http/, 'ws');
    },
};
