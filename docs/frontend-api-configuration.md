# Frontend API Configuration for Multi-App Service Deployment

## Overview

This document explains the changes made to configure the frontend to properly communicate with the backend API when both services are deployed as separate Azure App Services.

## Problem

Originally, the frontend was configured to make API calls to relative endpoints (e.g., `/chat`, `/upload`), which worked when both frontend and backend were served from the same domain. However, when deploying as separate App Services:
- Frontend: `https://{resourceGroup}-frontend.azurewebsites.net`
- Backend: `https://{resourceGroup}-backend.azurewebsites.net`

The frontend needs to make cross-origin requests to the backend service.

## Solution

Implemented a runtime configuration system that allows the frontend to dynamically determine the correct API base URL:

### 1. Created API Configuration Utility (`src/frontend/src/utils/api-config.ts`)

```typescript
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
    const cleanEndpoint = endpoint.startsWith('/') ? endpoint.slice(1) : endpoint;
    
    if (baseUrl === window.location.origin) {
        return `/${cleanEndpoint}`;
    }
    
    return `${baseUrl}/${cleanEndpoint}`;
};
```

### 2. Updated API Constants (`src/frontend/src/constants/app.ts`)

Modified the `API_ENDPOINTS` object to use the `buildApiUrl` function:

```typescript
export const API_ENDPOINTS = {
    CHAT: buildApiUrl("chat"),
    LIST_INDEXES: buildApiUrl("list_indexes"),
    GET_CITATION_DOC: buildApiUrl("get_citation_doc"),
    // ... other endpoints
} as const;
```

### 3. Updated Direct API Calls

Updated the following components to use `buildApiUrl`:
- `src/frontend/src/api/api.ts`
- `src/frontend/src/components/upload/DocumentUpload/DocumentUpload.tsx`
- `src/frontend/src/components/search/SearchSettings/SearchSettings.tsx`
- `src/frontend/src/components/admin/Admin.tsx`

### 4. Enhanced Deployment Scripts

Updated both deployment scripts to set the `API_BASE_URL` environment variable:

**deploy-azure.ps1 and deploy-azure-private.ps1:**
```powershell
# Set the API_BASE_URL for the frontend to point to the backend service
$backendUrl = "https://$($resourceGroup)-backend.azurewebsites.net"
Write-Host "Setting API_BASE_URL for frontend to: $backendUrl"

az webapp config appsettings set --name $frontendApp --resource-group $resourceGroup --settings ... API_BASE_URL=$backendUrl | Out-Null
```

## How It Works

### Development Environment
- Vite dev server proxies API calls to `localhost:5000`
- `getApiBaseUrl()` returns `window.location.origin`
- API calls are made to relative URLs like `/chat`
- Vite proxy handles the routing to the backend

### Production Environment
- Docker container starts with `entrypoint.sh`
- `entrypoint.sh` processes `env-config.template.js` and replaces `{{API_BASE_URL}}` with the actual backend URL
- Frontend loads the runtime config from `/env-config.js`
- `getApiBaseUrl()` returns the configured backend URL
- API calls are made to absolute URLs like `https://{resourceGroup}-backend.azurewebsites.net/chat`

## Runtime Configuration Flow

1. **Container Start**: `entrypoint.sh` generates `/env-config.js` from template
2. **Page Load**: `index.html` loads `/env-config.js` which sets `window.__RUNTIME_CONFIG__`
3. **API Calls**: `getApiBaseUrl()` checks for runtime config and returns appropriate base URL
4. **Request Routing**: `buildApiUrl()` constructs full URLs for cross-origin requests

## Benefits

- **Environment Agnostic**: Same code works in development and production
- **Runtime Configuration**: No need to rebuild images for different environments
- **Backward Compatible**: Continues to work with single-domain deployments
- **Flexible**: Easy to point to different backend services for testing

## Files Modified

### New Files
- `src/frontend/src/utils/api-config.ts`

### Modified Files
- `src/frontend/src/constants/app.ts`
- `src/frontend/src/api/api.ts`
- `src/frontend/src/components/upload/DocumentUpload/DocumentUpload.tsx`
- `src/frontend/src/components/search/SearchSettings/SearchSettings.tsx`
- `src/frontend/src/components/admin/Admin.tsx`
- `deploy/deploy-azure.ps1`
- `deploy/deploy-azure-private.ps1`

### Unchanged (by design)
- `src/frontend/vite.config.ts` - Proxy configuration preserved for development
- `src/frontend/env-config.template.js` - Template already supported API_BASE_URL
- `src/frontend/entrypoint.sh` - Runtime config injection already implemented
- `src/frontend/index.html` - Runtime config loading already implemented

## Testing

After deployment, verify the configuration by:
1. Opening browser developer tools
2. Checking that `window.__RUNTIME_CONFIG__.API_BASE_URL` points to the backend service
3. Verifying that API requests in the Network tab show the correct backend URLs
4. Testing actual functionality (chat, upload, admin) to ensure cross-origin requests work
