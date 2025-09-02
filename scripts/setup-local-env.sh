#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
ENVIRONMENT_NAME=${AZURE_ENV_NAME:-""}
RESOURCE_GROUP_NAME=""
FORCE=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -e|--environment)
            ENVIRONMENT_NAME="$2"
            shift 2
            ;;
        -g|--resource-group)
            RESOURCE_GROUP_NAME="$2"
            shift 2
            ;;
        -f|--force)
            FORCE=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  -e, --environment NAME    Azure environment name"
            echo "  -g, --resource-group NAME Resource group name"
            echo "  -f, --force              Overwrite existing .env file without prompt"
            echo "  -h, --help               Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option $1"
            exit 1
            ;;
    esac
done

function log_info() {
    echo -e "${BLUE}$1${NC}"
}

function log_success() {
    echo -e "${GREEN}$1${NC}"
}

function log_warning() {
    echo -e "${YELLOW}$1${NC}"
}

function log_error() {
    echo -e "${RED}$1${NC}"
}

log_info "🔧 Setting up local development environment..."

# Check if azd is available
if ! command -v azd &> /dev/null; then
    log_error "❌ Azure Developer CLI (azd) is not installed. Please install it first."
    exit 1
fi

# Check if az CLI is available
if ! command -v az &> /dev/null; then
    log_error "❌ Azure CLI (az) is not installed. Please install it first."
    exit 1
fi

# Check if jq is available
if ! command -v jq &> /dev/null; then
    log_error "❌ jq is not installed. Please install it first (required for JSON parsing)."
    exit 1
fi

# Get environment name if not provided
if [[ -z "$ENVIRONMENT_NAME" ]]; then
    read -p "Enter your Azure environment name: " ENVIRONMENT_NAME
    if [[ -z "$ENVIRONMENT_NAME" ]]; then
        log_error "❌ Environment name is required."
        exit 1
    fi
fi

log_warning "📋 Using environment: $ENVIRONMENT_NAME"

# Get azd environment variables
log_info "🔍 Retrieving environment variables from azd..."
if ! AZD_OUTPUT=$(azd env get-values --environment "$ENVIRONMENT_NAME" 2>/dev/null); then
    log_error "❌ Failed to get environment variables from azd. Make sure the environment exists and you're logged in."
    log_warning "   Run 'azd env list' to see available environments."
    exit 1
fi

log_success "✅ Retrieved environment variables from azd."

# Parse azd output into associative array
declare -A azd_vars
while IFS='=' read -r key value; do
    # Remove quotes from value if present
    value=$(echo "$value" | sed 's/^"//;s/"$//')
    azd_vars["$key"]="$value"
done <<< "$AZD_OUTPUT"

# Set resource group name if not provided
if [[ -z "$RESOURCE_GROUP_NAME" ]]; then
    RESOURCE_GROUP_NAME="${azd_vars[AZURE_RESOURCE_GROUP]}"
    if [[ -z "$RESOURCE_GROUP_NAME" ]]; then
        RESOURCE_GROUP_NAME="$ENVIRONMENT_NAME"
    fi
fi

log_warning "📋 Using resource group: $RESOURCE_GROUP_NAME"

# Define the .env file path
ENV_FILE_PATH="src/backend/.env"

# Check if .env file exists and handle accordingly
if [[ -f "$ENV_FILE_PATH" ]] && [[ "$FORCE" != true ]]; then
    read -p "📄 .env file already exists. Overwrite? (y/N): " overwrite
    if [[ "$overwrite" != "y" && "$overwrite" != "Y" ]]; then
        log_warning "❌ Operation cancelled."
        exit 0
    fi
fi

if [[ -f "$ENV_FILE_PATH" ]]; then
    log_warning "🗑️  Removing existing .env file..."
    rm -f "$ENV_FILE_PATH"
fi

log_info "🔑 Fetching API keys from Azure services..."

# Get current user information
if ! CURRENT_USER=$(az ad signed-in-user show 2>/dev/null); then
    log_error "❌ Failed to get current user information. Make sure you're logged in to Azure CLI."
    exit 1
fi

TENANT_ID=$(echo "$CURRENT_USER" | jq -r '.tenantId')
log_success "✅ Retrieved tenant information."

# Function to safely get resource keys
get_resource_key() {
    local resource_name="$1"
    local resource_type="$2"
    local key_command="$3"
    
    if result=$(eval "$key_command" 2>/dev/null) && [[ -n "$result" ]]; then
        log_success "  ✅ Retrieved $resource_type key for $resource_name"
        echo "$result"
    else
        log_warning "  ⚠️  Failed to get $resource_type key for $resource_name"
        echo ""
    fi
}

# Get service names from azd outputs
AI_SERVICES_NAME="${azd_vars[AI_SERVICES_NAME]}"
OPENAI_SERVICE_NAME="${azd_vars[OPENAI_SERVICE_NAME]}"
SEARCH_SERVICE_NAME="${azd_vars[SEARCH_SERVICE_NAME]}"

log_info "🔍 Service names:"
log_info "  - AI Services: $AI_SERVICES_NAME"
log_info "  - OpenAI Service: $OPENAI_SERVICE_NAME"
log_info "  - Search Service: $SEARCH_SERVICE_NAME"

# Fetch API keys
log_info "🔑 Fetching API keys..."

DOCUMENT_INTELLIGENCE_KEY=$(get_resource_key "$AI_SERVICES_NAME" "Document Intelligence" "az cognitiveservices account keys list --name '$AI_SERVICES_NAME' --resource-group '$RESOURCE_GROUP_NAME' --query 'key1' -o tsv")

OPENAI_API_KEY=$(get_resource_key "$OPENAI_SERVICE_NAME" "OpenAI" "az cognitiveservices account keys list --name '$OPENAI_SERVICE_NAME' --resource-group '$RESOURCE_GROUP_NAME' --query 'key1' -o tsv")

SEARCH_API_KEY=$(get_resource_key "$SEARCH_SERVICE_NAME" "Search" "az search admin-key show --service-name '$SEARCH_SERVICE_NAME' --resource-group '$RESOURCE_GROUP_NAME' --query 'primaryKey' -o tsv")

# Create .env file content
cat > "$ENV_FILE_PATH" << EOF
# Azure OpenAI Configuration
AZURE_OPENAI_ENDPOINT=${azd_vars[AZURE_OPENAI_ENDPOINT]}
AZURE_OPENAI_API_KEY=$OPENAI_API_KEY
AZURE_OPENAI_MODEL_NAME=${azd_vars[AZURE_OPENAI_MODEL_NAME]}
AZURE_OPENAI_DEPLOYMENT=${azd_vars[AZURE_OPENAI_DEPLOYMENT]}
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=${azd_vars[AZURE_OPENAI_EMBEDDING_DEPLOYMENT]}

# Azure AI Search Configuration
SEARCH_SERVICE_ENDPOINT=${azd_vars[SEARCH_SERVICE_ENDPOINT]}
SEARCH_API_KEY=$SEARCH_API_KEY
SEARCH_INDEX_NAME=${azd_vars[SEARCH_INDEX_NAME]}

# Knowledge Agent Configuration
KNOWLEDGE_AGENT_NAME=${azd_vars[KNOWLEDGE_AGENT_NAME]}

# Azure Storage Configuration
ARTIFACTS_STORAGE_ACCOUNT_URL=${azd_vars[ARTIFACTS_STORAGE_ACCOUNT_URL]}
ARTIFACTS_STORAGE_CONTAINER=${azd_vars[ARTIFACTS_STORAGE_CONTAINER]}
SAMPLES_STORAGE_CONTAINER=${azd_vars[SAMPLES_STORAGE_CONTAINER]}

# Document Intelligence Configuration
DOCUMENTINTELLIGENCE_ENDPOINT=${azd_vars[DOCUMENTINTELLIGENCE_ENDPOINT]}
DOCUMENTINTELLIGENCE_KEY=$DOCUMENT_INTELLIGENCE_KEY

# Azure AI Inference (Embedding) Configuration
AZURE_INFERENCE_EMBED_ENDPOINT=${azd_vars[AZURE_INFERENCE_EMBED_ENDPOINT]}
AZURE_INFERENCE_API_KEY=${azd_vars[AZURE_INFERENCE_EMBED_API_KEY]}
AZURE_INFERENCE_EMBED_MODEL_NAME=${azd_vars[AZURE_INFERENCE_EMBED_MODEL_NAME]}

# Azure Service Principal (SPN) Authentication - REQUIRED for local development
AZURE_TENANT_ID=$TENANT_ID
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
EOF

if [[ $? -eq 0 ]]; then
    log_success "✅ Created .env file at $ENV_FILE_PATH"
else
    log_error "❌ Failed to create .env file"
    exit 1
fi

echo ""
log_success "🎉 Local development environment setup complete!"
echo ""
log_info "📝 Next steps:"
log_info "  1. Review and update the .env file if needed"
log_info "  2. If using service principal authentication, set AZURE_CLIENT_ID and AZURE_CLIENT_SECRET"
log_info "  3. Run './src/start.sh' to start the backend"
log_info "  4. Run 'npm run dev' in src/frontend directory to start the frontend"
echo ""

# Check for missing or empty keys
warnings=()
[[ -z "$DOCUMENT_INTELLIGENCE_KEY" ]] && warnings+=("Document Intelligence API key")
[[ -z "$OPENAI_API_KEY" ]] && warnings+=("OpenAI API key") 
[[ -z "$SEARCH_API_KEY" ]] && warnings+=("Search API key")

if [[ ${#warnings[@]} -gt 0 ]]; then
    log_warning "⚠️  Warnings:"
    for warning in "${warnings[@]}"; do
        log_warning "  - Missing or empty: $warning"
    done
    log_warning "  You may need to manually set these values in the .env file."
fi
