# Private Repository Deployment

This folder contains deployment files for scenarios where your application needs to access private npm/PyPI repositories during the build process.

## Files

- `deploy-azure-private.ps1` - PowerShell deployment script with support for private registry credentials
- `../src/frontend/Dockerfile.private` - Frontend Dockerfile with npm private registry support  
- `../src/backend/Dockerfile.private` - Backend Dockerfile with PyPI private registry support

## Usage

### For Private npm Registry

```powershell
.\deploy-azure-private.ps1 `
  -resourceGroup "my-rg" `
  -location "eastus" `
  -acrName "myacr" `
  -npmToken "npm_1234567890abcdef" `
  -privateNpmRegistry "https://my-private-registry.com" `
  -privateNpmToken "private_token_here"
```

### For Private PyPI Repository

```powershell
.\deploy-azure-private.ps1 `
  -resourceGroup "my-rg" `
  -location "eastus" `
  -acrName "myacr" `
  -privatePipIndex "https://my-pypi.company.com/simple/" `
  -privatePipToken "pypi_token_here" `
  -privatePipUsername "username" `
  -pipTrustedHost "my-pypi.company.com"
```

### Combined Example

```powershell
.\deploy-azure-private.ps1 `
  -resourceGroup "my-rg" `
  -location "eastus" `
  -acrName "myacr" `
  -npmToken "npm_1234567890abcdef" `
  -privateNpmRegistry "https://npm.company.com" `
  -privateNpmToken "npm_private_token" `
  -privatePipIndex "https://pypi.company.com/simple/" `
  -privatePipToken "pypi_token" `
  -privatePipUsername "pypi_user" `
  -pipTrustedHost "pypi.company.com"
```

## Security Notes

- **Build Args Only**: Private credentials are passed as Docker build arguments and only exist in intermediate build layers, not in the final runtime image.
- **Multi-stage Builds**: Both Dockerfiles use multi-stage builds to ensure secrets don't leak into the final image.
- **No Credentials in Logs**: The deployment script masks sensitive parameters in build command output.

## Parameters

### npm Registry Parameters
- `npmToken` - NPM authentication token for npmjs.org
- `privateNpmRegistry` - URL of your private npm registry (e.g., "https://npm.company.com")
- `privateNpmToken` - Authentication token for the private npm registry

### PyPI Repository Parameters  
- `privatePipIndex` - URL of your private PyPI index (e.g., "https://pypi.company.com/simple/")
- `privatePipToken` - Authentication token for private PyPI
- `privatePipUsername` - Username for private PyPI authentication
- `pipTrustedHost` - Trusted host for pip (e.g., "pypi.company.com")

## Default Deployment

For standard deployments without private repositories, continue using the original `deploy-azure.ps1` script with the standard `Dockerfile` files.
