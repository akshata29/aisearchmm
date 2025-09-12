Azure deployment helper

Files added:
- `deploy-azure.ps1` - PowerShell script that creates Resource Group, ACR, builds images, pushes, and creates App Service + Function App.
- `frontend/Dockerfile`, `frontend/entrypoint.sh`, `frontend/env-config.template.js` - frontend container which injects runtime config from env.
- `backend/Dockerfile` - backend container using Azure Functions Python base image.

Quick usage

1. Login to Azure (if not already):

```powershell
az login
```

2. From `deploy` folder run the deployment script (adjust parameters as needed):

```powershell
.\deploy-azure.ps1 -resourceGroup my-rg -location eastus -acrName myacr -envFile ..\.env
```

Notes
- The frontend Docker image builds the Vite app (or similar) into /dist and serves via nginx. The `env-config.template.js` is copied into the output and `entrypoint.sh` will substitute placeholders with environment variables at container start. Ensure your SPA reads runtime config from `window.__RUNTIME_CONFIG__` (example below).
- The backend Dockerfile uses the Azure Functions Python image; the Function App will run as a container from ACR.
- The deployment script now assigns system-managed identities to the Web App and Function App and grants them the AcrPull role so they can pull images from ACR securely.

Runtime config usage (frontend)

In your frontend code access runtime values like:

```js
const apiBase = window.__RUNTIME_CONFIG__?.API_BASE_URL || process.env.API_BASE_URL
```

If the `env-config.template.js` doesn't exist in your source, the container will still run but `window.__RUNTIME_CONFIG__` may be undefined.
