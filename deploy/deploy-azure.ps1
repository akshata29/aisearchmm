param(
  [string]$resourceGroup = "astdnapublic",
  [string]$location = "eastus2",
  [string]$acrName = "aisearchmmacr",
  [string]$backendImage = "backend:latest",
  [string]$envFile = "..\src\backend\.env"
)

Write-Host "Starting deployment: resourceGroup=$resourceGroup location=$location acr=$acrName"

function Ensure-AzCli {
  if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    throw "Azure CLI (az) is required. Install from https://aka.ms/InstallAzureCLI"
  }
}

function Ensure-Docker {
  if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is required. Install from https://docs.docker.com/get-docker/"
  }
}

function Ensure-Node {
  if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "Node.js and npm are required. Install from https://nodejs.org/"
  }
}

Ensure-AzCli
Ensure-Docker
Ensure-Node

# login check
$azAccount = az account show 2>$null
if (-not $azAccount) {
  Write-Host "Please login to Azure..."
  az login | Out-Null
}

# create resource group
az group create --name $resourceGroup --location $location | Out-Null


# create ACR (enable admin for initial deployment, can be disabled later)
if (-not (az acr show --name $acrName -g $resourceGroup --query name --output tsv 2>$null)) {
  az acr create --resource-group $resourceGroup --name $acrName --sku Basic --location $location --admin-enabled true | Out-Null
} else {
  # Ensure admin is enabled for deployment
  az acr update --name $acrName --resource-group $resourceGroup --admin-enabled true | Out-Null
}

$acrLoginServer = az acr show --name $acrName --query loginServer --output tsv

# Login to ACR for pushing images
az acr login --name $acrName | Out-Null

# Build frontend and copy to backend static folder
Write-Host "Building frontend and copying to backend static folder..."
Set-Location "../src/frontend"
npm install
npm run build
Set-Location "../../deploy"

# build and push backend (now includes updated frontend static files)
Write-Host "Building backend image (with updated frontend)..."
docker build -f "$(Resolve-Path ../src/backend/Dockerfile)" -t $backendImage ../src/backend
docker tag $backendImage "$acrLoginServer/$backendImage"
docker push "$acrLoginServer/$backendImage"

# Create App Service plan and Web App for backend (serves both API and frontend)
$planName = "$($resourceGroup)-plan"
if (-not (az appservice plan show --name $planName -g $resourceGroup -o none 2>$null)) {
  az appservice plan create --name $planName --resource-group $resourceGroup --is-linux --sku B1 | Out-Null
}

$backendApp = "$($resourceGroup)-ui"
if (-not (az webapp show --name $backendApp --resource-group $resourceGroup -o none 2>$null)) {
  az webapp create --resource-group $resourceGroup --plan $planName --name $backendApp --deployment-container-image-name "$acrLoginServer/$backendImage" | Out-Null
} else {
  az webapp config container set --name $backendApp --resource-group $resourceGroup --docker-custom-image-name "$acrLoginServer/$backendImage" | Out-Null
}

# Configure webapp with ACR credentials 
Write-Host "Configuring backend app with ACR credentials"
$acrCreds = az acr credential show --name $acrName --resource-group $resourceGroup --query "{username:username,password:passwords[0].value}" -o json | ConvertFrom-Json
Write-Host "ACR Username: $($acrCreds.username)"
Write-Host "ACR Password: [REDACTED - length: $($acrCreds.password.Length)]"
Write-Host "Using ACR Login Server: $acrLoginServer"

az webapp config appsettings set --name $backendApp --resource-group $resourceGroup --settings WEBSITES_PORT=8080 "DOCKER_REGISTRY_SERVER_URL=https://$acrLoginServer" "DOCKER_REGISTRY_SERVER_USERNAME=$($acrCreds.username)" "DOCKER_REGISTRY_SERVER_PASSWORD=$($acrCreds.password)" | Out-Null

# Optional: Enable managed identity and grant AcrPull (can be used instead of admin credentials)
Write-Host "Enabling managed identity for backend app"
az webapp identity assign --name $backendApp --resource-group $resourceGroup | Out-Null
$backendPrincipalId = az webapp show --name $backendApp --resource-group $resourceGroup --query identity.principalId -o tsv
az role assignment create --assignee-object-id $backendPrincipalId --assignee-principal-type ServicePrincipal --role AcrPull --scope "/subscriptions/$(az account show --query id -o tsv)/resourceGroups/$resourceGroup/providers/Microsoft.ContainerRegistry/registries/$acrName" | Out-Null

# Grant storage permissions if storage account exists in same resource group
Write-Host "Checking for storage accounts and granting permissions..."
$storageAccounts = az storage account list --resource-group $resourceGroup --query "[].name" -o tsv
foreach ($storageAccount in $storageAccounts) {
  if ($storageAccount) {
    Write-Host "Granting Storage Blob Data Contributor to backend app for storage account: $storageAccount"
    az role assignment create --assignee-object-id $backendPrincipalId --assignee-principal-type ServicePrincipal --role "Storage Blob Data Contributor" --scope "/subscriptions/$(az account show --query id -o tsv)/resourceGroups/$resourceGroup/providers/Microsoft.Storage/storageAccounts/$storageAccount" | Out-Null
  }
}

# Apply environment variables from .env to backend app
if (Test-Path $envFile) {
  Write-Host "Loading environment from $envFile"
  
  # Apply to backend app
  Write-Host "Setting environment variables on backend app: $backendApp"
  Get-Content $envFile | Where-Object {$_ -notmatch "^\s*#" -and $_ -notmatch "^\s*$"} | ForEach-Object { 
    if ($_ -match "^([A-Za-z_][A-Za-z0-9_]*)=(.*)$") { 
      $key = $matches[1]; 
      $value = $matches[2]; 
      if ($value -match '^"(.*)"$' -or $value -match "^'(.*)'$") { 
        $value = $matches[1] 
      }
      Write-Host "Setting: $key"
      az webapp config appsettings set --name $backendApp --resource-group $resourceGroup --settings "$key=$value" | Out-Null
    } 
  }
}

Write-Host "Deployment complete!"
Write-Host "Application URL: https://$backendApp.azurewebsites.net"
Write-Host ""
Write-Host "The backend serves both the API and frontend static files."
Write-Host "You can access the full application at the URL above."

# Clean up: Delete frontend app service if it exists
Write-Host ""
Write-Host "Cleaning up unnecessary resources..."
$frontendApp = "$($resourceGroup)-frontend"
if (az webapp show --name $frontendApp --resource-group $resourceGroup -o none 2>$null) {
  Write-Host "Deleting unnecessary frontend app service: $frontendApp"
  az webapp delete --name $frontendApp --resource-group $resourceGroup --keep-empty-plan | Out-Null
  Write-Host "Frontend app service deleted successfully."
} else {
  Write-Host "Frontend app service not found - already cleaned up."
}

Write-Host ""
Write-Host "SECURITY NOTE: For production, consider disabling ACR admin user and using only managed identity:"
Write-Host "  az acr update --name $acrName --resource-group $resourceGroup --admin-enabled false"
Write-Host "  Then remove DOCKER_REGISTRY_SERVER_USERNAME/PASSWORD from app settings."
