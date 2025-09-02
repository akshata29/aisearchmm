# Local Development Environment Setup

This document explains the automated setup process for local development of the Azure AI Search Multimodal RAG Demo.

## Overview

The application now includes automated scripts that generate the necessary `.env` file for local development by fetching API keys and configuration from your deployed Azure resources.

## How It Works

### During Deployment (`azd up`)

When you run `azd up`, the deployment process automatically:

1. Provisions all Azure resources (AI Services, Search, Storage, etc.)
2. Deploys the application to Azure App Service
3. Runs the data ingestion process
4. **Automatically generates a local `.env` file** with all necessary configuration

### Manual Setup

If you need to generate or regenerate the `.env` file for an existing deployment:

#### Windows
```powershell
scripts/setup-local-env.ps1 -EnvironmentName <YOUR_ENVIRONMENT_NAME>
```

#### Linux/macOS
```bash
./scripts/setup-local-env.sh --environment <YOUR_ENVIRONMENT_NAME>
```

## What Gets Configured

The setup scripts automatically configure the following in your `.env` file:

### Azure Service Endpoints and Keys
- **Azure OpenAI**: Endpoint, API key, model names, and deployment names
- **Azure AI Search**: Endpoint, API key, and index name
- **Document Intelligence**: Endpoint and API key
- **Azure Storage**: Account URL and container names
- **Azure AI Inference**: Embedding endpoint, API key, and model name

### Local Development Settings
- `HOST=localhost`
- `PORT=5000`
- `AZURE_TENANT_ID` (automatically detected)

### Production Configuration
- Performance settings (timeouts, concurrency limits)
- Security settings (CORS, rate limiting)
- Monitoring settings (logging, health checks)
- Resilience settings (circuit breaker, retry policies)

## Service Principal Authentication

For local development, you may need to set up service principal authentication:

1. The scripts automatically set `AZURE_TENANT_ID`
2. You need to manually set `AZURE_CLIENT_ID` and `AZURE_CLIENT_SECRET` if required

To create a service principal:
```bash
az ad sp create-for-rbac --name "MyApp" --role contributor --scopes /subscriptions/<subscription-id>/resourceGroups/<resource-group>
```

## Script Options

### PowerShell Script (`setup-local-env.ps1`)
- `-EnvironmentName`: Azure environment name (default: from `$env:AZURE_ENV_NAME`)
- `-ResourceGroupName`: Resource group name (default: auto-detected)
- `-Force`: Overwrite existing `.env` file without prompting

### Bash Script (`setup-local-env.sh`)
- `--environment`: Azure environment name
- `--resource-group`: Resource group name  
- `--force`: Overwrite existing `.env` file without prompting
- `--help`: Show usage information

## Troubleshooting

### Common Issues

1. **Missing API keys**: If some API keys are empty, ensure you have the necessary permissions to access the resources
2. **Authentication errors**: Make sure you're logged in to both Azure CLI (`az login`) and Azure Developer CLI (`azd auth login`)
3. **Resource not found**: Verify the environment name and resource group are correct

### Required Permissions

Your user account needs the following Azure RBAC roles:
- **Cognitive Services User** (for AI Services and OpenAI)
- **Search Service Contributor** (for Search service)
- **Storage Blob Data Contributor** (for Storage account)

## Infrastructure Changes

The infrastructure has been updated to support local development:

### Search Service
- Changed `disableLocalAuth` from `true` to `false` to enable API key access for local development
- Production deployments still use managed identity for security

### Additional Outputs
- Added service names to infrastructure outputs for script automation
- Added `AZURE_TENANT_ID` output for service principal configuration

### Environment Variables
The deployment now outputs all necessary values for local development while maintaining security best practices for production.
