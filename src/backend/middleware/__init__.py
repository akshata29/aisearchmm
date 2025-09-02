"""
Middleware components for request logging, error handling, security, and monitoring.
"""

import json
import time
import traceback
from typing import Callable, Dict, Any, Optional
from aiohttp import web, hdrs

from core.exceptions import ApplicationError, ValidationError, ErrorCategory
from core.config import SecurityConfig
from utils.logging_config import StructuredLogger, set_request_id, clear_request_id, get_request_id


class RequestLoggingMiddleware:
    """Middleware for logging HTTP requests and responses."""

    def __init__(self, enable_request_logging: bool = True, enable_performance_logging: bool = True):
        self.enable_request_logging = enable_request_logging
        self.enable_performance_logging = enable_performance_logging
        self.logger = StructuredLogger("request")

    @web.middleware
    async def __call__(self, request: web.Request, handler: Callable) -> web.Response:
        """Log request and response details."""
        # Generate and set request ID
        request_id = set_request_id()
        
        start_time = time.time()
        
        # Log incoming request
        if self.enable_request_logging:
            self.logger.info(
                f"Incoming request: {request.method} {request.path}",
                method=request.method,
                path=request.path,
                query_string=str(request.query_string),
                user_agent=request.headers.get("User-Agent"),
                remote_addr=request.remote,
                request_id=request_id
            )

        try:
            # Add request ID to request for downstream handlers
            request['request_id'] = request_id
            
            # Process request
            response = await handler(request)
            
            # Calculate duration
            duration = time.time() - start_time
            
            # Log response
            if self.enable_request_logging:
                self.logger.info(
                    f"Request completed: {request.method} {request.path}",
                    method=request.method,
                    path=request.path,
                    status_code=response.status,
                    duration_ms=round(duration * 1000, 2),
                    request_id=request_id
                )
            
            # Log performance metrics
            if self.enable_performance_logging:
                self.logger.log_request_metrics(
                    method=request.method,
                    path=request.path,
                    status_code=response.status,
                    duration=duration
                )
            
            # Add request ID to response headers
            response.headers['X-Request-ID'] = request_id
            
            return response
            
        except Exception as error:
            duration = time.time() - start_time
            
            # Log error
            self.logger.error(
                f"Request failed: {request.method} {request.path}",
                method=request.method,
                path=request.path,
                error=str(error),
                error_type=type(error).__name__,
                duration_ms=round(duration * 1000, 2),
                request_id=request_id,
                exc_info=True
            )
            
            raise
        finally:
            # Clear request ID from context
            clear_request_id()


class ErrorHandlingMiddleware:
    """Middleware for centralized error handling."""

    def __init__(self):
        self.logger = StructuredLogger("error_handler")

    @web.middleware
    async def __call__(self, request: web.Request, handler: Callable) -> web.Response:
        """Handle exceptions and return structured error responses."""
        try:
            return await handler(request)
        
        except ApplicationError as error:
            # Handle known application errors
            return self._create_error_response(error)
        
        except json.JSONDecodeError as error:
            # Handle JSON parsing errors
            app_error = ValidationError(
                message="Invalid JSON in request body",
                details={"json_error": str(error)}
            )
            return self._create_error_response(app_error)
        
        except UnicodeDecodeError as error:
            # Handle encoding errors
            app_error = ValidationError(
                message="Invalid character encoding in request",
                details={"encoding_error": str(error)}
            )
            return self._create_error_response(app_error)
        
        except web.HTTPError as error:
            # Handle aiohttp HTTP errors
            if error.status_code == 413:
                app_error = ValidationError(
                    message="Request entity too large",
                    details={"max_size": "100MB"}
                )
            elif error.status_code == 414:
                app_error = ValidationError(
                    message="Request URI too long"
                )
            elif error.status_code == 408:
                app_error = ApplicationError(
                    message="Request timeout",
                    category=ErrorCategory.EXTERNAL_SERVICE,
                    status_code=408
                )
            else:
                app_error = ApplicationError(
                    message=error.reason or "HTTP error",
                    status_code=error.status_code
                )
            return self._create_error_response(app_error)
        
        except Exception as error:
            # Handle unexpected errors
            self.logger.error(
                "Unhandled exception occurred",
                error=str(error),
                error_type=type(error).__name__,
                traceback=traceback.format_exc(),
                exc_info=True
            )
            
            app_error = ApplicationError(
                message="An unexpected error occurred",
                category=ErrorCategory.INTERNAL,
                details={"error_id": get_request_id()}
            )
            return self._create_error_response(app_error)

    def _create_error_response(self, error: ApplicationError) -> web.Response:
        """Create a JSON error response."""
        response_data = error.to_dict()
        
        # Add request ID if available
        request_id = get_request_id()
        if request_id:
            response_data["request_id"] = request_id
        
        return web.json_response(
            response_data,
            status=error.status_code
        )


class SecurityMiddleware:
    """Middleware for security headers and basic protection."""

    def __init__(self, config: SecurityConfig):
        self.config = config
        self.logger = StructuredLogger("security")

    @web.middleware
    async def __call__(self, request: web.Request, handler: Callable) -> web.Response:
        """Add security headers and perform basic security checks."""
        
        # Validate request size
        content_length = request.headers.get('Content-Length')
        if content_length:
            try:
                size = int(content_length)
                max_size = 100 * 1024 * 1024  # 100MB
                if size > max_size:
                    raise ValidationError(
                        message="Request entity too large",
                        details={"size": size, "max_size": max_size}
                    )
            except ValueError:
                raise ValidationError(message="Invalid Content-Length header")

        # Process request
        response = await handler(request)
        
        # Add security headers
        self._add_security_headers(response)
        
        return response

    def _add_security_headers(self, response: web.Response) -> None:
        """Add security headers to response."""
        headers = {
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY',
            'X-XSS-Protection': '1; mode=block',
            'Referrer-Policy': 'strict-origin-when-cross-origin',
            'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';",
        }
        
        for header, value in headers.items():
            response.headers[header] = value


class CORSMiddleware:
    """Enhanced CORS middleware with configurable settings."""

    def __init__(self, config: SecurityConfig):
        self.config = config
        self.logger = StructuredLogger("cors")

    @web.middleware
    async def __call__(self, request: web.Request, handler: Callable) -> web.Response:
        """Handle CORS requests with configurable settings."""
        
        # Handle preflight requests
        if request.method == "OPTIONS":
            response = web.Response()
            self._add_cors_headers(response, request)
            return response
        
        # Process regular request
        response = await handler(request)
        self._add_cors_headers(response, request)
        
        return response

    def _add_cors_headers(self, response: web.Response, request: web.Request) -> None:
        """Add CORS headers to response."""
        origin = request.headers.get('Origin')
        
        # Check if origin is allowed
        if self._is_origin_allowed(origin):
            response.headers['Access-Control-Allow-Origin'] = origin or '*'
        elif '*' in self.config.allowed_origins:
            response.headers['Access-Control-Allow-Origin'] = '*'
        
        response.headers['Access-Control-Allow-Methods'] = ', '.join(self.config.allowed_methods)
        response.headers['Access-Control-Allow-Headers'] = ', '.join(self.config.allowed_headers)
        response.headers['Access-Control-Max-Age'] = str(self.config.max_age)
        response.headers['Access-Control-Allow-Credentials'] = 'true'

    def _is_origin_allowed(self, origin: Optional[str]) -> bool:
        """Check if origin is in allowed list."""
        if not origin:
            return False
        
        if '*' in self.config.allowed_origins:
            return True
        
        return origin in self.config.allowed_origins


class RequestValidationMiddleware:
    """Middleware for basic request validation."""

    def __init__(self, enable_validation: bool = True):
        self.enable_validation = enable_validation
        self.logger = StructuredLogger("validation")

    @web.middleware
    async def __call__(self, request: web.Request, handler: Callable) -> web.Response:
        """Validate incoming requests."""
        
        if not self.enable_validation:
            return await handler(request)
        
        # Validate Content-Type for POST/PUT requests
        if request.method in ['POST', 'PUT', 'PATCH']:
            content_type = request.headers.get('Content-Type', '')
            
            # Check for JSON endpoints
            if request.path.startswith('/api/') or request.path in ['/chat', '/upload', '/process_document']:
                if not any(ct in content_type for ct in ['application/json', 'multipart/form-data', 'text/plain']):
                    raise ValidationError(
                        message="Invalid Content-Type",
                        details={
                            "expected": ["application/json", "multipart/form-data"],
                            "received": content_type
                        }
                    )
        
        return await handler(request)


def create_middleware_stack(
    security_config: SecurityConfig,
    enable_request_logging: bool = True,
    enable_performance_logging: bool = True,
    enable_validation: bool = True
) -> list:
    """Create the complete middleware stack."""
    
    middleware_stack = []
    
    # Request logging (first to capture all requests)
    if enable_request_logging or enable_performance_logging:
        middleware_stack.append(
            RequestLoggingMiddleware(enable_request_logging, enable_performance_logging).__call__
        )
    
    # Error handling (early to catch all errors)
    middleware_stack.append(ErrorHandlingMiddleware().__call__)
    
    # Security middleware
    middleware_stack.append(SecurityMiddleware(security_config).__call__)
    
    # CORS handling
    middleware_stack.append(CORSMiddleware(security_config).__call__)
    
    # Request validation (before business logic)
    if enable_validation:
        middleware_stack.append(RequestValidationMiddleware(enable_validation).__call__)
    
    return middleware_stack
