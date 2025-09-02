"""
Retry and resilience utilities for external service calls.
Provides exponential backoff, circuit breaker patterns, and timeout handling.
"""

import asyncio
import time
import random
from typing import Any, Callable, Optional, Type, Union, List
from dataclasses import dataclass
from functools import wraps
from enum import Enum

from core.exceptions import ExternalServiceError, RateLimitError
from utils.logging_config import StructuredLogger


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"         # Failing, rejecting requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    backoff_factor: float = 1.0
    
    # Exceptions that should trigger retries
    retryable_exceptions: tuple = (
        ConnectionError,
        TimeoutError,
        asyncio.TimeoutError,
        ExternalServiceError,
    )
    
    # Exceptions that should NOT trigger retries
    non_retryable_exceptions: tuple = (
        ValueError,
        TypeError,
        RateLimitError,
    )


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    expected_exception: Type[Exception] = Exception
    half_open_max_calls: int = 3


class CircuitBreaker:
    """Circuit breaker implementation for fault tolerance."""

    def __init__(self, config: CircuitBreakerConfig, name: str = "circuit_breaker"):
        self.config = config
        self.name = name
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0
        self.half_open_calls = 0
        self.logger = StructuredLogger(f"circuit_breaker.{name}")

    async def __aenter__(self):
        """Async context manager entry."""
        await self._check_state()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if exc_type and issubclass(exc_type, self.config.expected_exception):
            await self._record_failure()
        else:
            await self._record_success()

    async def call(self, func: Callable, *args, **kwargs):
        """Call a function through the circuit breaker."""
        async with self:
            return await func(*args, **kwargs)

    async def _check_state(self):
        """Check and update circuit breaker state."""
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.config.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                self.logger.info(f"Circuit breaker {self.name} moved to HALF_OPEN state")
            else:
                raise ExternalServiceError(
                    service=self.name,
                    operation="circuit_breaker_check",
                    message="Circuit breaker is OPEN"
                )
        
        elif self.state == CircuitState.HALF_OPEN:
            if self.half_open_calls >= self.config.half_open_max_calls:
                self.state = CircuitState.OPEN
                self.last_failure_time = time.time()
                self.logger.warning(f"Circuit breaker {self.name} moved back to OPEN state")
                raise ExternalServiceError(
                    service=self.name,
                    operation="circuit_breaker_check",
                    message="Circuit breaker is OPEN (half-open limit exceeded)"
                )
            
            self.half_open_calls += 1

    async def _record_success(self):
        """Record a successful operation."""
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.logger.info(f"Circuit breaker {self.name} moved to CLOSED state")
        
        self.failure_count = 0

    async def _record_failure(self):
        """Record a failed operation."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.config.failure_threshold:
            self.state = CircuitState.OPEN
            self.logger.warning(
                f"Circuit breaker {self.name} moved to OPEN state",
                failure_count=self.failure_count,
                threshold=self.config.failure_threshold
            )


class RetryHandler:
    """Handles retry logic with exponential backoff."""

    def __init__(self, config: RetryConfig, name: str = "retry_handler"):
        self.config = config
        self.name = name
        self.logger = StructuredLogger(f"retry.{name}")

    async def execute(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with retry logic."""
        last_exception = None
        
        for attempt in range(1, self.config.max_attempts + 1):
            try:
                start_time = time.time()
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                
                if attempt > 1:
                    self.logger.info(
                        f"Operation succeeded after {attempt} attempts",
                        operation=func.__name__,
                        attempts=attempt,
                        duration_ms=round(duration * 1000, 2)
                    )
                
                return result
                
            except Exception as e:
                last_exception = e
                
                # Check if exception is retryable
                if not self._is_retryable(e):
                    self.logger.warning(
                        f"Non-retryable exception occurred",
                        operation=func.__name__,
                        exception=str(e),
                        exception_type=type(e).__name__,
                        attempt=attempt
                    )
                    raise
                
                # Don't retry on last attempt
                if attempt == self.config.max_attempts:
                    self.logger.error(
                        f"Operation failed after {attempt} attempts",
                        operation=func.__name__,
                        exception=str(e),
                        exception_type=type(e).__name__,
                        total_attempts=attempt
                    )
                    raise
                
                # Calculate delay and wait
                delay = self._calculate_delay(attempt)
                
                self.logger.warning(
                    f"Operation failed, retrying in {delay:.2f}s",
                    operation=func.__name__,
                    exception=str(e),
                    exception_type=type(e).__name__,
                    attempt=attempt,
                    retry_delay=delay
                )
                
                await asyncio.sleep(delay)
        
        # This should never be reached, but just in case
        if last_exception:
            raise last_exception

    def _is_retryable(self, exception: Exception) -> bool:
        """Check if an exception is retryable."""
        # Check non-retryable exceptions first
        if isinstance(exception, self.config.non_retryable_exceptions):
            return False
        
        # Check retryable exceptions
        return isinstance(exception, self.config.retryable_exceptions)

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for the given attempt."""
        # Exponential backoff
        delay = (
            self.config.base_delay *
            self.config.backoff_factor *
            (self.config.exponential_base ** (attempt - 1))
        )
        
        # Apply maximum delay
        delay = min(delay, self.config.max_delay)
        
        # Add jitter to avoid thundering herd
        if self.config.jitter:
            jitter = delay * 0.1 * random.random()
            delay += jitter
        
        return delay


class ResilientClient:
    """Base class for resilient service clients."""

    def __init__(
        self,
        service_name: str,
        retry_config: Optional[RetryConfig] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None
    ):
        self.service_name = service_name
        self.retry_config = retry_config or RetryConfig()
        self.circuit_breaker_config = circuit_breaker_config or CircuitBreakerConfig()
        
        self.retry_handler = RetryHandler(self.retry_config, service_name)
        self.circuit_breaker = CircuitBreaker(self.circuit_breaker_config, service_name)
        
        self.logger = StructuredLogger(f"resilient_client.{service_name}")

    async def execute_with_resilience(self, operation: str, func: Callable, *args, **kwargs) -> Any:
        """Execute a function with retry and circuit breaker protection."""
        async def resilient_operation():
            async with self.circuit_breaker:
                return await func(*args, **kwargs)
        
        try:
            return await self.retry_handler.execute(resilient_operation)
        except Exception as e:
            # Log the final failure
            self.logger.error(
                f"Resilient operation failed",
                service=self.service_name,
                operation=operation,
                exception=str(e),
                exception_type=type(e).__name__
            )
            
            # Convert to service-specific error if not already
            if not isinstance(e, ExternalServiceError):
                raise ExternalServiceError(
                    service=self.service_name,
                    operation=operation,
                    message=str(e),
                    original_error=e
                )
            raise


def with_retry(
    config: Optional[RetryConfig] = None,
    service_name: str = "unknown"
):
    """Decorator for adding retry behavior to async functions."""
    retry_config = config or RetryConfig()
    
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            retry_handler = RetryHandler(retry_config, f"{service_name}.{func.__name__}")
            return await retry_handler.execute(func, *args, **kwargs)
        return wrapper
    return decorator


def with_circuit_breaker(
    config: Optional[CircuitBreakerConfig] = None,
    service_name: str = "unknown"
):
    """Decorator for adding circuit breaker behavior to async functions."""
    cb_config = config or CircuitBreakerConfig()
    
    def decorator(func: Callable):
        circuit_breaker = CircuitBreaker(cb_config, f"{service_name}.{func.__name__}")
        
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await circuit_breaker.call(func, *args, **kwargs)
        return wrapper
    return decorator


async def with_timeout(coro, timeout: float, operation: str = "operation"):
    """Execute coroutine with timeout."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        raise ExternalServiceError(
            service="timeout",
            operation=operation,
            message=f"Operation timed out after {timeout}s"
        )
