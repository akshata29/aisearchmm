"""
Centralized configuration management for the AI Search Multimodal application.
Provides type-safe configuration with validation and environment-specific settings.
"""

import os
import logging
from pathlib import Path
from typing import Optional, Union
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

logger = logging.getLogger(__name__)


@dataclass
class AzureOpenAIConfig:
    """Azure OpenAI service configuration."""
    endpoint: str
    deployment: str
    model_name: str
    embedding_deployment: str
    embedding_model_name: str = "text-embedding-ada-002"
    api_key: Optional[str] = None
    api_version: str = "2024-08-01-preview"
    timeout: int = 30
    max_retries: int = 3

    def __post_init__(self):
        if not self.endpoint:
            raise ValueError("AZURE_OPENAI_ENDPOINT is required")
        if not self.deployment:
            raise ValueError("AZURE_OPENAI_DEPLOYMENT is required")
        if not self.model_name:
            raise ValueError("AZURE_OPENAI_MODEL_NAME is required")
        if not self.embedding_deployment:
            raise ValueError("AZURE_OPENAI_EMBEDDING_DEPLOYMENT is required")


@dataclass
class SearchServiceConfig:
    """Azure Cognitive Search service configuration."""
    endpoint: str
    index_name: str
    api_key: Optional[str] = None
    api_version: str = "2024-05-01-preview"
    timeout: int = 30
    max_retries: int = 3

    def __post_init__(self):
        if not self.endpoint:
            raise ValueError("SEARCH_SERVICE_ENDPOINT is required")
        if not self.index_name:
            raise ValueError("SEARCH_INDEX_NAME is required")


@dataclass
class StorageConfig:
    """Azure Storage configuration."""
    artifacts_account_url: str
    artifacts_container: str
    samples_container: str
    connection_timeout: int = 30
    read_timeout: int = 300
    max_retries: int = 3

    def __post_init__(self):
        if not self.artifacts_account_url:
            raise ValueError("ARTIFACTS_STORAGE_ACCOUNT_URL is required")
        if not self.artifacts_container:
            raise ValueError("ARTIFACTS_STORAGE_CONTAINER is required")
        if not self.samples_container:
            raise ValueError("SAMPLES_STORAGE_CONTAINER is required")


@dataclass
class DocumentIntelligenceConfig:
    """Azure Document Intelligence configuration."""
    endpoint: str
    key: Optional[str] = None
    timeout: int = 120
    max_retries: int = 3

    def __post_init__(self):
        if not self.endpoint:
            raise ValueError("DOCUMENTINTELLIGENCE_ENDPOINT is required")


@dataclass
class ServerConfig:
    """Web server configuration."""
    host: str = "localhost"
    port: int = 5000
    debug: bool = False
    max_request_size: int = 100 * 1024 * 1024  # 100MB
    request_timeout: int = 300  # 5 minutes
    keepalive_timeout: int = 75
    client_timeout: int = 30

    def __post_init__(self):
        if self.port < 1 or self.port > 65535:
            raise ValueError(f"Invalid port number: {self.port}")


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    format: str = "json"  # json or text
    enable_request_logging: bool = True
    enable_performance_logging: bool = True
    log_file: Optional[str] = None
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5

    def __post_init__(self):
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.level.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {self.level}. Must be one of {valid_levels}")
        self.level = self.level.upper()

        valid_formats = ["json", "text"]
        if self.format.lower() not in valid_formats:
            raise ValueError(f"Invalid log format: {self.format}. Must be one of {valid_formats}")
        self.format = self.format.lower()


@dataclass
class SecurityConfig:
    """Security configuration."""
    allowed_origins: list[str] = field(default_factory=lambda: ["*"])
    allowed_methods: list[str] = field(default_factory=lambda: ["GET", "POST", "PUT", "DELETE", "OPTIONS"])
    allowed_headers: list[str] = field(default_factory=lambda: ["Content-Type", "Authorization"])
    max_age: int = 86400  # 24 hours
    enable_request_validation: bool = True
    enable_rate_limiting: bool = False
    rate_limit_requests: int = 100
    rate_limit_window: int = 60  # seconds


@dataclass
class MonitoringConfig:
    """Monitoring and observability configuration."""
    enable_health_checks: bool = True
    enable_metrics: bool = True
    enable_tracing: bool = False
    application_insights_key: Optional[str] = None
    metrics_endpoint: str = "/metrics"
    health_endpoint: str = "/health"


@dataclass
class ApplicationConfig:
    """Main application configuration container."""
    azure_openai: AzureOpenAIConfig
    search_service: SearchServiceConfig
    storage: StorageConfig
    document_intelligence: DocumentIntelligenceConfig
    server: ServerConfig
    logging: LoggingConfig
    security: SecurityConfig
    monitoring: MonitoringConfig
    knowledge_agent_name: Optional[str] = None
    environment: str = "development"

    @classmethod
    def from_environment(cls) -> "ApplicationConfig":
        """Create configuration from environment variables."""
        try:
            # Azure OpenAI Configuration
            azure_openai = AzureOpenAIConfig(
                endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
                deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
                model_name=os.environ["AZURE_OPENAI_MODEL_NAME"],
                embedding_deployment=os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"],
                embedding_model_name=os.environ.get("AZURE_OPENAI_EMBEDDING_MODEL_NAME", "text-embedding-ada-002"),
                api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
                api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-08-01-preview"),
                timeout=int(os.environ.get("AZURE_OPENAI_TIMEOUT", "30")),
                max_retries=int(os.environ.get("AZURE_OPENAI_MAX_RETRIES", "3"))
            )

            # Search Service Configuration
            search_service = SearchServiceConfig(
                endpoint=os.environ["SEARCH_SERVICE_ENDPOINT"],
                index_name=os.environ["SEARCH_INDEX_NAME"],
                api_key=os.environ.get("SEARCH_API_KEY"),
                api_version=os.environ.get("SEARCH_API_VERSION", "2024-05-01-preview"),
                timeout=int(os.environ.get("SEARCH_TIMEOUT", "30")),
                max_retries=int(os.environ.get("SEARCH_MAX_RETRIES", "3"))
            )

            # Storage Configuration
            storage = StorageConfig(
                artifacts_account_url=os.environ["ARTIFACTS_STORAGE_ACCOUNT_URL"],
                artifacts_container=os.environ["ARTIFACTS_STORAGE_CONTAINER"],
                samples_container=os.environ["SAMPLES_STORAGE_CONTAINER"],
                connection_timeout=int(os.environ.get("STORAGE_CONNECTION_TIMEOUT", "30")),
                read_timeout=int(os.environ.get("STORAGE_READ_TIMEOUT", "300")),
                max_retries=int(os.environ.get("STORAGE_MAX_RETRIES", "3"))
            )

            # Document Intelligence Configuration
            document_intelligence = DocumentIntelligenceConfig(
                endpoint=os.environ["DOCUMENTINTELLIGENCE_ENDPOINT"],
                key=os.environ.get("DOCUMENTINTELLIGENCE_KEY"),
                timeout=int(os.environ.get("DOCUMENTINTELLIGENCE_TIMEOUT", "120")),
                max_retries=int(os.environ.get("DOCUMENTINTELLIGENCE_MAX_RETRIES", "3"))
            )

            # Server Configuration
            server = ServerConfig(
                host=os.environ.get("HOST", "localhost"),
                port=int(os.environ.get("PORT", "5000")),
                debug=os.environ.get("DEBUG", "false").lower() == "true",
                max_request_size=int(os.environ.get("MAX_REQUEST_SIZE", str(100 * 1024 * 1024))),
                request_timeout=int(os.environ.get("REQUEST_TIMEOUT", "300")),
                keepalive_timeout=int(os.environ.get("KEEPALIVE_TIMEOUT", "75")),
                client_timeout=int(os.environ.get("CLIENT_TIMEOUT", "30"))
            )

            # Logging Configuration
            logging_config = LoggingConfig(
                level=os.environ.get("LOG_LEVEL", "INFO"),
                format=os.environ.get("LOG_FORMAT", "json"),
                enable_request_logging=os.environ.get("ENABLE_REQUEST_LOGGING", "true").lower() == "true",
                enable_performance_logging=os.environ.get("ENABLE_PERFORMANCE_LOGGING", "true").lower() == "true",
                log_file=os.environ.get("LOG_FILE"),
                max_file_size=int(os.environ.get("LOG_MAX_FILE_SIZE", str(10 * 1024 * 1024))),
                backup_count=int(os.environ.get("LOG_BACKUP_COUNT", "5"))
            )

            # Security Configuration
            allowed_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "*").split(",")
            if allowed_origins == ["*"]:
                allowed_origins = ["*"]
            else:
                allowed_origins = [origin.strip() for origin in allowed_origins]

            security = SecurityConfig(
                allowed_origins=allowed_origins,
                allowed_methods=os.environ.get("CORS_ALLOWED_METHODS", "GET,POST,PUT,DELETE,OPTIONS").split(","),
                allowed_headers=os.environ.get("CORS_ALLOWED_HEADERS", "Content-Type,Authorization").split(","),
                max_age=int(os.environ.get("CORS_MAX_AGE", "86400")),
                enable_request_validation=os.environ.get("ENABLE_REQUEST_VALIDATION", "true").lower() == "true",
                enable_rate_limiting=os.environ.get("ENABLE_RATE_LIMITING", "false").lower() == "true",
                rate_limit_requests=int(os.environ.get("RATE_LIMIT_REQUESTS", "100")),
                rate_limit_window=int(os.environ.get("RATE_LIMIT_WINDOW", "60"))
            )

            # Monitoring Configuration
            monitoring = MonitoringConfig(
                enable_health_checks=os.environ.get("ENABLE_HEALTH_CHECKS", "true").lower() == "true",
                enable_metrics=os.environ.get("ENABLE_METRICS", "true").lower() == "true",
                enable_tracing=os.environ.get("ENABLE_TRACING", "false").lower() == "true",
                application_insights_key=os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"),
                metrics_endpoint=os.environ.get("METRICS_ENDPOINT", "/metrics"),
                health_endpoint=os.environ.get("HEALTH_ENDPOINT", "/health")
            )

            return cls(
                azure_openai=azure_openai,
                search_service=search_service,
                storage=storage,
                document_intelligence=document_intelligence,
                server=server,
                logging=logging_config,
                security=security,
                monitoring=monitoring,
                knowledge_agent_name=os.environ.get("KNOWLEDGE_AGENT_NAME"),
                environment=os.environ.get("ENVIRONMENT", "development")
            )

        except KeyError as e:
            logger.error(f"Missing required environment variable: {e}")
            raise
        except ValueError as e:
            logger.error(f"Invalid configuration value: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise

    def validate(self) -> None:
        """Validate the configuration."""
        # Additional cross-field validation can be added here
        if self.environment not in ["development", "staging", "production"]:
            logger.warning(f"Unknown environment: {self.environment}")

        if self.server.debug and self.environment == "production":
            logger.warning("Debug mode is enabled in production environment")

        logger.info(f"Configuration loaded successfully for environment: {self.environment}")


# Global configuration instance
config: Optional[ApplicationConfig] = None


def get_config() -> ApplicationConfig:
    """Get the global configuration instance."""
    global config
    if config is None:
        config = ApplicationConfig.from_environment()
        config.validate()
    return config


def reload_config() -> ApplicationConfig:
    """Reload the configuration from environment variables."""
    global config
    config = ApplicationConfig.from_environment()
    config.validate()
    return config
