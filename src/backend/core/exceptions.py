"""
Custom exception classes and error handling utilities for the application.
Provides structured error responses and categorized exceptions.
"""

from typing import Any, Dict, Optional
from enum import Enum


class ErrorCategory(Enum):
    """Categories of errors for better classification and handling."""
    VALIDATION = "validation"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    EXTERNAL_SERVICE = "external_service"
    RATE_LIMIT = "rate_limit"
    INTERNAL = "internal"
    CONFIGURATION = "configuration"


class ApplicationError(Exception):
    """Base exception class for application-specific errors."""

    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.INTERNAL,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None
    ):
        super().__init__(message)
        self.message = message
        self.category = category
        self.status_code = status_code
        self.details = details or {}
        self.original_error = original_error

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for JSON serialization."""
        error_dict = {
            "error": {
                "message": self.message,
                "category": self.category.value,
                "status_code": self.status_code,
                "details": self.details
            }
        }
        
        if self.original_error:
            error_dict["error"]["original_error"] = {
                "type": type(self.original_error).__name__,
                "message": str(self.original_error)
            }
        
        return error_dict


class ValidationError(ApplicationError):
    """Raised when input validation fails."""

    def __init__(self, message: str, field: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        details = details or {}
        if field:
            details["field"] = field
        super().__init__(
            message=message,
            category=ErrorCategory.VALIDATION,
            status_code=400,
            details=details
        )


class AuthenticationError(ApplicationError):
    """Raised when authentication fails."""

    def __init__(self, message: str = "Authentication failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            category=ErrorCategory.AUTHENTICATION,
            status_code=401,
            details=details
        )


class AuthorizationError(ApplicationError):
    """Raised when authorization fails."""

    def __init__(self, message: str = "Access denied", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            category=ErrorCategory.AUTHORIZATION,
            status_code=403,
            details=details
        )


class NotFoundError(ApplicationError):
    """Raised when a requested resource is not found."""

    def __init__(self, resource: str, identifier: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        details = details or {}
        details["resource"] = resource
        if identifier:
            details["identifier"] = identifier
        
        message = f"{resource} not found"
        if identifier:
            message += f": {identifier}"
        
        super().__init__(
            message=message,
            category=ErrorCategory.NOT_FOUND,
            status_code=404,
            details=details
        )


class ConflictError(ApplicationError):
    """Raised when a request conflicts with current state."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            category=ErrorCategory.CONFLICT,
            status_code=409,
            details=details
        )


class ExternalServiceError(ApplicationError):
    """Raised when an external service call fails."""

    def __init__(
        self,
        service: str,
        operation: str,
        message: str,
        status_code: Optional[int] = None,
        original_error: Optional[Exception] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        details = details or {}
        details.update({
            "service": service,
            "operation": operation
        })
        if status_code:
            details["service_status_code"] = status_code
        
        super().__init__(
            message=f"{service} service error: {message}",
            category=ErrorCategory.EXTERNAL_SERVICE,
            status_code=502,
            details=details,
            original_error=original_error
        )


class RateLimitError(ApplicationError):
    """Raised when rate limit is exceeded."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        details = details or {}
        if retry_after:
            details["retry_after"] = retry_after
        
        super().__init__(
            message=message,
            category=ErrorCategory.RATE_LIMIT,
            status_code=429,
            details=details
        )


class ConfigurationError(ApplicationError):
    """Raised when there's a configuration issue."""

    def __init__(self, message: str, config_key: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        details = details or {}
        if config_key:
            details["config_key"] = config_key
        
        super().__init__(
            message=message,
            category=ErrorCategory.CONFIGURATION,
            status_code=500,
            details=details
        )


class SearchServiceError(ExternalServiceError):
    """Specific error for Azure Search service issues."""

    def __init__(self, operation: str, message: str, original_error: Optional[Exception] = None):
        super().__init__(
            service="Azure Search",
            operation=operation,
            message=message,
            original_error=original_error
        )


class OpenAIServiceError(ExternalServiceError):
    """Specific error for Azure OpenAI service issues."""

    def __init__(self, operation: str, message: str, original_error: Optional[Exception] = None):
        super().__init__(
            service="Azure OpenAI",
            operation=operation,
            message=message,
            original_error=original_error
        )


class StorageServiceError(ExternalServiceError):
    """Specific error for Azure Storage service issues."""

    def __init__(self, operation: str, message: str, original_error: Optional[Exception] = None):
        super().__init__(
            service="Azure Storage",
            operation=operation,
            message=message,
            original_error=original_error
        )


class DocumentIntelligenceError(ExternalServiceError):
    """Specific error for Azure Document Intelligence service issues."""

    def __init__(self, operation: str, message: str, original_error: Optional[Exception] = None):
        super().__init__(
            service="Azure Document Intelligence",
            operation=operation,
            message=message,
            original_error=original_error
        )


def handle_azure_error(error: Exception, service: str, operation: str) -> ApplicationError:
    """Convert Azure SDK errors to application errors."""
    error_message = str(error)
    
    # Handle common Azure error patterns
    if "authentication" in error_message.lower():
        return AuthenticationError(f"Authentication failed for {service}: {error_message}")
    elif "authorization" in error_message.lower() or "forbidden" in error_message.lower():
        return AuthorizationError(f"Access denied to {service}: {error_message}")
    elif "not found" in error_message.lower():
        return NotFoundError(f"{service} resource", details={"operation": operation})
    elif "rate" in error_message.lower() and "limit" in error_message.lower():
        return RateLimitError(f"Rate limit exceeded for {service}")
    elif "timeout" in error_message.lower():
        return ExternalServiceError(service, operation, "Request timeout", original_error=error)
    elif "connection" in error_message.lower():
        return ExternalServiceError(service, operation, "Connection error", original_error=error)
    else:
        return ExternalServiceError(service, operation, error_message, original_error=error)
