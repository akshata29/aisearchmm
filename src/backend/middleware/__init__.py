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
from core.azure_client_factory import ClientFactory, AuthMode
from core.config import get_config


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
        """Add comprehensive security headers to response."""
        # Comprehensive CSP policy that allows necessary resources while maintaining security
        # Updated CSP: allow trusted CDNs (e.g. Monaco loader on cdn.jsdelivr.net) while keeping strict defaults.
        csp_policy = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://unpkg.com; "  # Allow Monaco loader from CDNs
            "style-src 'self' 'unsafe-inline' data:; "  # Allow inline styles and data URLs for fonts
            "img-src 'self' *.blob.core.windows.net *.azureedge.net data: blob: https:; "  # Allow Azure storage and common image sources
            "font-src 'self' data: https: *.gstatic.com *.googleapis.com; "  # Allow web fonts
            "connect-src 'self' https://cdn.jsdelivr.net *.blob.core.windows.net *.azure.com *.azureedge.net *.openai.azure.com wss: ws: https:; "  # Allow API connections and CDN module loads
            "media-src 'self' *.blob.core.windows.net data: blob:; "  # Allow media files from storage
            "object-src 'none'; "  # Block plugins for security
            "frame-src 'self'; "  # Allow same-origin frames
            "worker-src 'self' blob: https://cdn.jsdelivr.net; "  # Allow web workers and worker scripts from CDN
            "child-src 'self' blob:; "  # Allow child contexts
            "manifest-src 'self'; "  # Allow web app manifest
            "form-action 'self'; "  # Restrict form submissions
            "base-uri 'self'; "  # Restrict base URI
            "upgrade-insecure-requests"  # Upgrade HTTP to HTTPS
        )
        
        headers = {
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'SAMEORIGIN',  # Allow same-origin frames (less restrictive than DENY)
            'X-XSS-Protection': '1; mode=block',
            'Referrer-Policy': 'strict-origin-when-cross-origin',
            'Content-Security-Policy': csp_policy,
            'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',  # Enforce HTTPS
            'Permissions-Policy': 'geolocation=(), microphone=(), camera=()',  # Restrict sensitive permissions
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


class SessionResolverMiddleware:
    """Resolve a per-request session bundle (session_id + auth_mode) and attach it to the request.

    Headers supported:
    - X-Session-Id: arbitrary session identifier
    - X-Use-Managed-Identity: 'true'|'false' to choose auth mode for the session bundle
    Fallback: use config to auto-detect auth mode if header not present.
    """

    def __init__(self):
        self.logger = StructuredLogger("session_resolver")
        self.config = get_config()

    @web.middleware
    async def __call__(self, request: web.Request, handler: Callable) -> web.Response:
        # Read session id from header or cookie; default to request id
        session_id = request.headers.get("X-Session-Id") or request.cookies.get("session_id") or request.get("request_id") or "default"
        header_mi = request.headers.get("X-Use-Managed-Identity")
        # Log raw header value for debugging
        self.logger.debug("SessionResolver: raw X-Use-Managed-Identity header", extra={"raw_header": header_mi, "session_id": session_id})

        if header_mi is not None:
            use_mi = header_mi.lower() == "true"
            auth_mode = AuthMode.MANAGED_IDENTITY if use_mi else AuthMode.API_KEY
            self.logger.info("SessionResolver: header specified auth mode", extra={"session_id": session_id, "header_value": header_mi, "auth_mode": auth_mode.value})
        else:
            # Auto-detect from existing configured keys
            has_api_keys = bool(self.config.azure_openai.api_key or self.config.search_service.api_key or self.config.document_intelligence.key)
            auth_mode = AuthMode.API_KEY if has_api_keys else AuthMode.MANAGED_IDENTITY
            self.logger.info("SessionResolver: header missing, auto-detected auth mode", extra={"session_id": session_id, "has_api_keys": has_api_keys, "auth_mode": auth_mode.value})

        # If there's a cached session bundle for the other auth mode, clear it so toggling auth mode takes effect
        try:
            other_mode = AuthMode.MANAGED_IDENTITY if auth_mode == AuthMode.API_KEY else AuthMode.API_KEY
            await ClientFactory.clear_session(session_id, other_mode)
            self.logger.debug("SessionResolver: cleared cached bundle for other auth mode", extra={"session_id": session_id, "cleared_mode": other_mode.value})
        except Exception:
            # ignore errors while clearing; not critical
            self.logger.debug("SessionResolver: error clearing other-mode bundle (ignored)", extra={"session_id": session_id}, exc_info=True)

        # Obtain or create session bundle
        try:
            bundle = await ClientFactory.get_session_clients(session_id, auth_mode)
            request["session_bundle"] = bundle
            request["session_id"] = session_id
            request["auth_mode"] = auth_mode
            self.logger.info("Attached session bundle to request", extra={"session_id": session_id, "auth_mode": auth_mode.value})
        except Exception as e:
            self.logger.error("Failed to create session bundle", extra={"error": str(e), "session_id": session_id}, exc_info=True)
            # proceed without bundle but handler should validate presence when required

        # Call the next handler and attach debug response headers for verification
        response = await handler(request)

        try:
            # Attach the resolved auth mode and session id to the response so clients can verify
            if response is not None and hasattr(response, 'headers'):
                response.headers['X-Session-Auth-Mode'] = auth_mode.value
                response.headers['X-Session-Id'] = session_id
                self.logger.debug("Added debug response headers for auth mode", extra={"session_id": session_id, "auth_mode": auth_mode.value, "status": getattr(response, 'status', None)})
        except Exception:
            # Don't let header attaching break response path
            self.logger.debug("Failed to attach debug response headers", extra={"session_id": session_id}, exc_info=True)

        return response


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

    # Session resolver: attach session bundle (auth mode + clients) to request
    middleware_stack.append(SessionResolverMiddleware().__call__)
    
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
