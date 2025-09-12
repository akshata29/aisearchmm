// Utility to get the API base URL from runtime configuration
// This allows the frontend to work with different backend URLs in different environments

declare global {
    interface Window {
        __RUNTIME_CONFIG__: {
            API_BASE_URL?: string;
            [key: string]: any;
        };
    }
}

export const getApiBaseUrl = (): string => {
    // In production, use the runtime config injected by the container
    if (window.__RUNTIME_CONFIG__?.API_BASE_URL) {
        return window.__RUNTIME_CONFIG__.API_BASE_URL;
    }
    
    // In development, use the current origin (which gets proxied by Vite)
    return window.location.origin;
};

export const buildApiUrl = (endpoint: string): string => {
    const baseUrl = getApiBaseUrl();
    // Remove leading slash from endpoint if present to avoid double slashes
    const cleanEndpoint = endpoint.startsWith('/') ? endpoint.slice(1) : endpoint;
    
    // If base URL already includes a path or if it's the same origin, just use the endpoint
    if (baseUrl === window.location.origin) {
        return `/${cleanEndpoint}`;
    }
    
    return `${baseUrl}/${cleanEndpoint}`;
};
