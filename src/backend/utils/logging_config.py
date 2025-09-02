"""
Enhanced logging configuration for production-ready application.
Provides structured JSON logging, performance tracking, and request correlation.
"""

import logging
import logging.handlers
import json
import time
import uuid
import sys
from datetime import datetime
from typing import Any, Dict, Optional
from contextvars import ContextVar
from pathlib import Path

from core.config import LoggingConfig

# Context variable for request correlation
request_id_context: ContextVar[Optional[str]] = ContextVar('request_id', default=None)


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured JSON logging."""

    def __init__(self, include_request_id: bool = True):
        super().__init__()
        self.include_request_id = include_request_id

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add request ID if available
        if self.include_request_id:
            request_id = request_id_context.get()
            if request_id:
                log_entry["request_id"] = request_id

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self.formatException(record.exc_info)
            }

        # Add extra fields
        if hasattr(record, 'extra'):
            log_entry.update(record.extra)

        return json.dumps(log_entry, ensure_ascii=False)


class PerformanceLogger:
    """Logger for performance metrics and timing."""

    def __init__(self, logger_name: str = "performance"):
        self.logger = logging.getLogger(logger_name)

    def log_duration(self, operation: str, duration: float, **extra_fields):
        """Log operation duration."""
        self.logger.info(
            f"Operation completed: {operation}",
            extra={
                "operation": operation,
                "duration_ms": round(duration * 1000, 2),
                "metric_type": "duration",
                **extra_fields
            }
        )

    def log_counter(self, metric_name: str, value: int = 1, **extra_fields):
        """Log counter metric."""
        self.logger.info(
            f"Counter: {metric_name}",
            extra={
                "metric_name": metric_name,
                "value": value,
                "metric_type": "counter",
                **extra_fields
            }
        )

    def log_gauge(self, metric_name: str, value: float, **extra_fields):
        """Log gauge metric."""
        self.logger.info(
            f"Gauge: {metric_name}",
            extra={
                "metric_name": metric_name,
                "value": value,
                "metric_type": "gauge",
                **extra_fields
            }
        )


class TimingContext:
    """Context manager for timing operations."""

    def __init__(self, operation: str, logger: Optional[PerformanceLogger] = None, **extra_fields):
        self.operation = operation
        self.logger = logger or PerformanceLogger()
        self.extra_fields = extra_fields
        self.start_time = None
        self.duration = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.duration = time.time() - self.start_time
        status = "error" if exc_type else "success"
        self.logger.log_duration(
            self.operation,
            self.duration,
            status=status,
            **self.extra_fields
        )


def setup_logging(config: LoggingConfig) -> None:
    """Setup application logging configuration."""
    # Remove existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create formatter based on configuration
    if config.format == "json":
        formatter = StructuredFormatter()
    else:
        formatter = logging.Formatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

    # Setup console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(config.level)

    # Setup file handler if configured
    handlers = [console_handler]
    if config.log_file:
        log_path = Path(config.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_path,
            maxBytes=config.max_file_size,
            backupCount=config.backup_count,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(config.level)
        handlers.append(file_handler)

    # Configure root logger
    logging.basicConfig(
        level=config.level,
        handlers=handlers,
        force=True
    )

    # Disable overly verbose loggers
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured with level {config.level} and format {config.format}")


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with structured formatting."""
    return logging.getLogger(name)


def set_request_id(request_id: Optional[str] = None) -> str:
    """Set request ID in context for correlation."""
    if request_id is None:
        request_id = str(uuid.uuid4())
    request_id_context.set(request_id)
    return request_id


def get_request_id() -> Optional[str]:
    """Get current request ID from context."""
    return request_id_context.get()


def clear_request_id() -> None:
    """Clear request ID from context."""
    request_id_context.set(None)


class StructuredLogger:
    """Enhanced logger with structured logging capabilities."""

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.performance = PerformanceLogger(f"{name}.performance")

    def debug(self, message: str, **extra):
        """Log debug message with extra fields."""
        self.logger.debug(message, extra=extra)

    def info(self, message: str, **extra):
        """Log info message with extra fields."""
        self.logger.info(message, extra=extra)

    def warning(self, message: str, **extra):
        """Log warning message with extra fields."""
        self.logger.warning(message, extra=extra)

    def error(self, message: str, exc_info=None, **extra):
        """Log error message with extra fields and optional exception info."""
        self.logger.error(message, exc_info=exc_info, extra=extra)

    def critical(self, message: str, exc_info=None, **extra):
        """Log critical message with extra fields and optional exception info."""
        self.logger.critical(message, exc_info=exc_info, extra=extra)

    def timing_context(self, operation: str, **extra) -> TimingContext:
        """Create a timing context for measuring operation duration."""
        return TimingContext(operation, self.performance, **extra)

    def log_api_call(self, service: str, operation: str, duration: float, status: str, **extra):
        """Log API call metrics."""
        self.performance.log_duration(
            f"{service}.{operation}",
            duration,
            service=service,
            operation=operation,
            status=status,
            **extra
        )

    def log_request_metrics(self, method: str, path: str, status_code: int, duration: float, **extra):
        """Log HTTP request metrics."""
        self.performance.log_duration(
            "http_request",
            duration,
            method=method,
            path=path,
            status_code=status_code,
            **extra
        )
