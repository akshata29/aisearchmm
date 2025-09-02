#!/usr/bin/env pwsh

param(
    [Parameter(Mandatory = $false)]
    [string]$EnvironmentName = $env:AZURE_ENV_NAME,
    
    [Parameter(Mandatory = $false)]
    [string]$ResourceGroupName = $null,
    
    [Parameter(Mandatory = $false)]
    [switch]$Force = $false
)

# Set error action preference
$ErrorActionPreference = "Stop"

# Colors for output
$Green = [System.ConsoleColor]::Green
$Yellow = [System.ConsoleColor]::Yellow
$Red = [System.ConsoleColor]::Red
$Blue = [System.ConsoleColor]::Blue

function Write-ColorOutput {
    param([string]$Message, [System.ConsoleColor]$Color = [System.ConsoleColor]::White)
    Write-Host $Message -ForegroundColor $Color
}

Write-ColorOutput "🔧 Setting up local development environment..." $Blue

# Check if azd is available
if (-not (Get-Command "azd" -ErrorAction SilentlyContinue)) {
    Write-ColorOutput "❌ Azure Developer CLI (azd) is not installed. Please install it first." $Red
    exit 1
}

# Check if az CLI is available  
if (-not (Get-Command "az" -ErrorAction SilentlyContinue)) {
    Write-ColorOutput "❌ Azure CLI (az) is not installed. Please install it first." $Red
    exit 1
}

# Get environment name if not provided
if (-not $EnvironmentName) {
    $EnvironmentName = Read-Host "Enter your Azure environment name"
    if (-not $EnvironmentName) {
        Write-ColorOutput "❌ Environment name is required." $Red
        exit 1
    }
}

Write-ColorOutput "📋 Using environment: $EnvironmentName" $Yellow

# Get azd environment variables
try {
    $azdEnvVars = azd env get-values --environment $EnvironmentName | ConvertFrom-Json
    Write-ColorOutput "✅ Retrieved environment variables from azd." $Green
} catch {
    Write-ColorOutput "❌ Failed to get environment variables from azd. Make sure the environment exists and you're logged in." $Red
    Write-ColorOutput "   Run 'azd env list' to see available environments." $Yellow
    exit 1
}

# Set resource group name if not provided
if (-not $ResourceGroupName) {
    $ResourceGroupName = $azdEnvVars.AZURE_RESOURCE_GROUP
    if (-not $ResourceGroupName) {
        $ResourceGroupName = $EnvironmentName
    }
}

Write-ColorOutput "📋 Using resource group: $ResourceGroupName" $Yellow

# Define the .env file path
$envFilePath = "src/backend/.env"

# Check if .env file exists and handle accordingly
if (Test-Path $envFilePath) {
    if (-not $Force) {
        $overwrite = Read-Host "📄 .env file already exists. Overwrite? (y/N)"
        if ($overwrite -ne "y" -and $overwrite -ne "Y") {
            Write-ColorOutput "❌ Operation cancelled." $Yellow
            exit 0
        }
    }
    Write-ColorOutput "🗑️  Removing existing .env file..." $Yellow
    Remove-Item $envFilePath -Force
}

Write-ColorOutput "🔑 Fetching API keys from Azure services..." $Yellow

# Get current user information
try {
    $currentUser = az ad signed-in-user show | ConvertFrom-Json
    $tenantId = $currentUser.tenantId
    Write-ColorOutput "✅ Retrieved tenant information." $Green
} catch {
    Write-ColorOutput "❌ Failed to get current user information. Make sure you're logged in to Azure CLI." $Red
    exit 1
}

# Function to safely get resource keys
function Get-ResourceKey {
    param(
        [string]$ResourceName,
        [string]$ResourceType,
        [string]$KeyCommand
    )
    
    try {
        $result = Invoke-Expression $KeyCommand
        if ($result) {
            Write-ColorOutput "  ✅ Retrieved $ResourceType key for $ResourceName" $Green
            return $result
        } else {
            Write-ColorOutput "  ⚠️  Warning: Empty key returned for $ResourceName" $Yellow
            return ""
        }
    } catch {
        Write-ColorOutput "  ❌ Failed to get $ResourceType key for $ResourceName" $Red
        Write-ColorOutput "     Error: $($_.Exception.Message)" $Red
        return ""
    }
}

# Get service names from azd outputs
$aiServicesName = $azdEnvVars.AI_SERVICES_NAME
$openAiServiceName = $azdEnvVars.OPENAI_SERVICE_NAME  
$searchServiceName = $azdEnvVars.SEARCH_SERVICE_NAME

Write-ColorOutput "🔍 Service names:" $Blue
Write-ColorOutput "  - AI Services: $aiServicesName" $Blue
Write-ColorOutput "  - OpenAI Service: $openAiServiceName" $Blue  
Write-ColorOutput "  - Search Service: $searchServiceName" $Blue

# Fetch API keys
Write-ColorOutput "🔑 Fetching API keys..." $Yellow

$documentIntelligenceKey = Get-ResourceKey $aiServicesName "Document Intelligence" "az cognitiveservices account keys list --name '$aiServicesName' --resource-group '$ResourceGroupName' --query 'key1' -o tsv"

$openAiApiKey = Get-ResourceKey $openAiServiceName "OpenAI" "az cognitiveservices account keys list --name '$openAiServiceName' --resource-group '$ResourceGroupName' --query 'key1' -o tsv"

$searchApiKey = Get-ResourceKey $searchServiceName "Search" "az search admin-key show --service-name '$searchServiceName' --resource-group '$ResourceGroupName' --query 'primaryKey' -o tsv"

# Create .env file content
$envContent = @"
# Azure OpenAI Configuration
AZURE_OPENAI_ENDPOINT=$($azdEnvVars.AZURE_OPENAI_ENDPOINT)
AZURE_OPENAI_API_KEY=$openAiApiKey
AZURE_OPENAI_MODEL_NAME=$($azdEnvVars.AZURE_OPENAI_MODEL_NAME)
AZURE_OPENAI_DEPLOYMENT=$($azdEnvVars.AZURE_OPENAI_DEPLOYMENT)
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=$($azdEnvVars.AZURE_OPENAI_EMBEDDING_DEPLOYMENT)

# Azure AI Search Configuration
SEARCH_SERVICE_ENDPOINT=$($azdEnvVars.SEARCH_SERVICE_ENDPOINT)
SEARCH_API_KEY=$searchApiKey
SEARCH_INDEX_NAME=$($azdEnvVars.SEARCH_INDEX_NAME)

# Knowledge Agent Configuration
KNOWLEDGE_AGENT_NAME=$($azdEnvVars.KNOWLEDGE_AGENT_NAME)

# Azure Storage Configuration
ARTIFACTS_STORAGE_ACCOUNT_URL=$($azdEnvVars.ARTIFACTS_STORAGE_ACCOUNT_URL)
ARTIFACTS_STORAGE_CONTAINER=$($azdEnvVars.ARTIFACTS_STORAGE_CONTAINER)
SAMPLES_STORAGE_CONTAINER=$($azdEnvVars.SAMPLES_STORAGE_CONTAINER)

# Document Intelligence Configuration
DOCUMENTINTELLIGENCE_ENDPOINT=$($azdEnvVars.DOCUMENTINTELLIGENCE_ENDPOINT)
DOCUMENTINTELLIGENCE_KEY=$documentIntelligenceKey

# Azure AI Inference (Embedding) Configuration
AZURE_INFERENCE_EMBED_ENDPOINT=$($azdEnvVars.AZURE_INFERENCE_EMBED_ENDPOINT)
AZURE_INFERENCE_API_KEY=$($azdEnvVars.AZURE_INFERENCE_EMBED_API_KEY)
AZURE_INFERENCE_EMBED_MODEL_NAME=$($azdEnvVars.AZURE_INFERENCE_EMBED_MODEL_NAME)

# Azure Service Principal (SPN) Authentication - REQUIRED for local development
AZURE_TENANT_ID=$tenantId
AZURE_CLIENT_ID=
AZURE_CLIENT_SECRET=

# Local development settings
HOST=localhost
PORT=5000

# Production Configuration Settings
LOG_LEVEL=INFO
LOG_FORMAT=json
ENABLE_PERFORMANCE_LOGGING=true
ENABLE_REQUEST_LOGGING=true

# Performance Configuration
MAX_CONCURRENT_UPLOADS=10
UPLOAD_TIMEOUT_SECONDS=300
SEARCH_TIMEOUT_SECONDS=30
REQUEST_TIMEOUT_SECONDS=60
MAX_FILE_SIZE_MB=100

# Security Settings
ENABLE_CORS=true
CORS_ORIGINS=http://localhost:3000,https://yourdomain.com
SAS_TOKEN_DURATION_MINUTES=60
ENABLE_REQUEST_RATE_LIMITING=true
MAX_REQUESTS_PER_MINUTE=100

# Monitoring and Health Checks
ENABLE_HEALTH_CHECKS=true
HEALTH_CHECK_TIMEOUT_SECONDS=30
STATUS_RETENTION_HOURS=24

# Resilience Configuration
ENABLE_CIRCUIT_BREAKER=true
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
RETRY_MAX_ATTEMPTS=3

# Environment Configuration
ENVIRONMENT=development
DEBUG_MODE=false
"@

# Write .env file
try {
    $envContent | Out-File -FilePath $envFilePath -Encoding UTF8
    Write-ColorOutput "✅ Created .env file at $envFilePath" $Green
} catch {
    Write-ColorOutput "❌ Failed to create .env file: $($_.Exception.Message)" $Red
    exit 1
}

Write-ColorOutput "" 
Write-ColorOutput "🎉 Local development environment setup complete!" $Green
Write-ColorOutput ""
Write-ColorOutput "📝 Next steps:" $Blue
Write-ColorOutput "  1. Review and update the .env file if needed" $Blue
Write-ColorOutput "  2. If using service principal authentication, set AZURE_CLIENT_ID and AZURE_CLIENT_SECRET" $Blue
Write-ColorOutput "  3. Run 'start.bat' in src/backend directory to start the backend" $Blue
Write-ColorOutput "  4. Run 'npm run dev' in src/frontend directory to start the frontend" $Blue
Write-ColorOutput ""

# Check for missing or empty keys
$warnings = @()
if (-not $documentIntelligenceKey) { $warnings += "Document Intelligence API key" }
if (-not $openAiApiKey) { $warnings += "OpenAI API key" }
if (-not $searchApiKey) { $warnings += "Search API key" }

if ($warnings.Count -gt 0) {
    Write-ColorOutput "⚠️  Warnings:" $Yellow
    foreach ($warning in $warnings) {
        Write-ColorOutput "  - Missing or empty: $warning" $Yellow
    }
    Write-ColorOutput "  You may need to manually set these values in the .env file." $Yellow
}
