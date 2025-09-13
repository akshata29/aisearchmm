"""
Health check and monitoring utilities for the application.
Provides endpoints for health monitoring and service status checks.
"""

import asyncio
import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from aiohttp import web
from azure.search.documents.aio import SearchClient
from azure.storage.blob.aio import BlobServiceClient
from openai import AsyncAzureOpenAI

from core.config import ApplicationConfig
from core.exceptions import ExternalServiceError
from utils.logging_config import StructuredLogger


@dataclass
class ServiceStatus:
    """Status information for a service."""
    name: str
    status: str  # healthy, unhealthy, degraded
    response_time_ms: Optional[float] = None
    error: Optional[str] = None
    last_check: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


@dataclass
class HealthCheckResult:
    """Overall health check result."""
    status: str  # healthy, unhealthy, degraded
    timestamp: str
    uptime_seconds: float
    version: str = "1.0.0"
    services: List[ServiceStatus] = None
    summary: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.services is None:
            self.services = []


class HealthChecker:
    """Health checker for application services."""

    def __init__(self, config: ApplicationConfig):
        self.config = config
        self.logger = StructuredLogger("health_check")
        self.start_time = time.time()
        
        # Service clients for health checks
        self._search_client: Optional[SearchClient] = None
        self._blob_client: Optional[BlobServiceClient] = None
        self._openai_client: Optional[AsyncAzureOpenAI] = None

    def set_clients(
        self,
        search_client: SearchClient,
        blob_client: BlobServiceClient,
        openai_client: AsyncAzureOpenAI
    ):
        """Set service clients for health checks."""
        self._search_client = search_client
        self._blob_client = blob_client
        self._openai_client = openai_client
        try:
            # Attempt to log auth_mode if provided on blob client or openai client
            auth_mode = None
            cred = getattr(blob_client, 'credential', None)
            if cred is not None:
                # If credential is a string account key, assume API_KEY
                if isinstance(cred, str):
                    auth_mode = 'api_key'
                else:
                    auth_mode = 'managed_identity'
            self.logger.info('HealthChecker clients set', extra={'auth_mode': auth_mode})
        except Exception:
            self.logger.debug('Could not determine auth_mode in health checker', exc_info=True)

    async def check_health(self, include_detailed: bool = False) -> HealthCheckResult:
        """Perform comprehensive health check."""
        timestamp = datetime.utcnow().isoformat() + "Z"
        uptime = time.time() - self.start_time
        
        services = []
        
        if include_detailed:
            # Check all services
            services = await self._check_all_services()
        
        # Determine overall status
        overall_status = self._determine_overall_status(services)
        
        # Create summary
        summary = self._create_summary(services) if services else None
        
        return HealthCheckResult(
            status=overall_status,
            timestamp=timestamp,
            uptime_seconds=uptime,
            services=services,
            summary=summary
        )

    async def _check_all_services(self) -> List[ServiceStatus]:
        """Check health of all services."""
        services = []
        
        # Check services in parallel
        tasks = [
            self._check_search_service(),
            self._check_storage_service(),
            self._check_openai_service(),
            self._check_database_connection(),
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, ServiceStatus):
                services.append(result)
            elif isinstance(result, Exception):
                self.logger.error(f"Health check failed: {result}", exc_info=True)
                services.append(ServiceStatus(
                    name="unknown",
                    status="unhealthy",
                    error=str(result),
                    last_check=datetime.utcnow().isoformat() + "Z"
                ))
        
        return services

    async def _check_search_service(self) -> ServiceStatus:
        """Check Azure Search service health."""
        start_time = time.time()
        
        try:
            if not self._search_client:
                return ServiceStatus(
                    name="azure_search",
                    status="unhealthy",
                    error="Search client not initialized",
                    last_check=datetime.utcnow().isoformat() + "Z"
                )
            
            # Simple search to test connectivity
            result = await self._search_client.search(
                search_text="*",
                top=1,
                select="content_id"
            )
            
            # Consume the first result to ensure the query executes
            async for _ in result:
                break
            
            response_time = (time.time() - start_time) * 1000
            
            return ServiceStatus(
                name="azure_search",
                status="healthy",
                response_time_ms=round(response_time, 2),
                last_check=datetime.utcnow().isoformat() + "Z",
                details={
                    "endpoint": self.config.search_service.endpoint,
                    "index": self.config.search_service.index_name
                }
            )
            
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return ServiceStatus(
                name="azure_search",
                status="unhealthy",
                response_time_ms=round(response_time, 2),
                error=str(e),
                last_check=datetime.utcnow().isoformat() + "Z"
            )

    async def _check_storage_service(self) -> ServiceStatus:
        """Check Azure Storage service health."""
        start_time = time.time()
        
        try:
            if not self._blob_client:
                return ServiceStatus(
                    name="azure_storage",
                    status="unhealthy",
                    error="Blob client not initialized",
                    last_check=datetime.utcnow().isoformat() + "Z"
                )
            
            # Check container existence
            container_client = self._blob_client.get_container_client(
                self.config.storage.samples_container
            )
            
            await container_client.get_container_properties()
            
            response_time = (time.time() - start_time) * 1000
            
            return ServiceStatus(
                name="azure_storage",
                status="healthy",
                response_time_ms=round(response_time, 2),
                last_check=datetime.utcnow().isoformat() + "Z",
                details={
                    "account_url": self.config.storage.artifacts_account_url,
                    "containers": [
                        self.config.storage.artifacts_container,
                        self.config.storage.samples_container
                    ]
                }
            )
            
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return ServiceStatus(
                name="azure_storage",
                status="unhealthy",
                response_time_ms=round(response_time, 2),
                error=str(e),
                last_check=datetime.utcnow().isoformat() + "Z"
            )

    async def _check_openai_service(self) -> ServiceStatus:
        """Check Azure OpenAI service health."""
        start_time = time.time()
        
        try:
            if not self._openai_client:
                return ServiceStatus(
                    name="azure_openai",
                    status="unhealthy",
                    error="OpenAI client not initialized",
                    last_check=datetime.utcnow().isoformat() + "Z"
                )
            
            # Simple embeddings call to test connectivity
            response = await self._openai_client.embeddings.create(
                model=self.config.azure_openai.embedding_deployment,
                input="health check"
            )
            
            response_time = (time.time() - start_time) * 1000
            
            return ServiceStatus(
                name="azure_openai",
                status="healthy",
                response_time_ms=round(response_time, 2),
                last_check=datetime.utcnow().isoformat() + "Z",
                details={
                    "endpoint": self.config.azure_openai.endpoint,
                    "deployment": self.config.azure_openai.deployment,
                    "embedding_deployment": self.config.azure_openai.embedding_deployment
                }
            )
            
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return ServiceStatus(
                name="azure_openai",
                status="unhealthy",
                response_time_ms=round(response_time, 2),
                error=str(e),
                last_check=datetime.utcnow().isoformat() + "Z"
            )

    async def _check_database_connection(self) -> ServiceStatus:
        """Check database/index connectivity."""
        # For this application, we'll check if we can access the search index
        return await self._check_search_service()

    def _determine_overall_status(self, services: List[ServiceStatus]) -> str:
        """Determine overall health status from service statuses."""
        if not services:
            return "healthy"  # No detailed checks performed
        
        statuses = [service.status for service in services]
        
        if any(status == "unhealthy" for status in statuses):
            return "unhealthy"
        elif any(status == "degraded" for status in statuses):
            return "degraded"
        else:
            return "healthy"

    def _create_summary(self, services: List[ServiceStatus]) -> Dict[str, Any]:
        """Create summary of service health."""
        total_services = len(services)
        healthy_count = sum(1 for s in services if s.status == "healthy")
        degraded_count = sum(1 for s in services if s.status == "degraded")
        unhealthy_count = sum(1 for s in services if s.status == "unhealthy")
        
        avg_response_time = None
        response_times = [s.response_time_ms for s in services if s.response_time_ms is not None]
        if response_times:
            avg_response_time = round(sum(response_times) / len(response_times), 2)
        
        return {
            "total_services": total_services,
            "healthy_services": healthy_count,
            "degraded_services": degraded_count,
            "unhealthy_services": unhealthy_count,
            "average_response_time_ms": avg_response_time
        }


class HealthHandler:
    """HTTP handler for health check endpoints."""

    def __init__(self, health_checker: HealthChecker):
        self.health_checker = health_checker
        self.logger = StructuredLogger("health_handler")

    async def handle_health_check(self, request: web.Request) -> web.Response:
        """Handle health check requests."""
        # Check if detailed health check is requested
        detailed = request.query.get('detailed', 'false').lower() == 'true'
        
        try:
            health_result = await self.health_checker.check_health(include_detailed=detailed)
            
            # Determine HTTP status code based on health
            if health_result.status == "healthy":
                status_code = 200
            elif health_result.status == "degraded":
                status_code = 200  # Still operational
            else:
                status_code = 503  # Service unavailable
            
            return web.json_response(
                asdict(health_result),
                status=status_code
            )
            
        except Exception as e:
            self.logger.error(f"Health check failed: {e}", exc_info=True)
            
            # Return minimal unhealthy response
            error_result = HealthCheckResult(
                status="unhealthy",
                timestamp=datetime.utcnow().isoformat() + "Z",
                uptime_seconds=time.time() - self.health_checker.start_time
            )
            
            return web.json_response(
                asdict(error_result),
                status=503
            )

    async def handle_readiness_check(self, request: web.Request) -> web.Response:
        """Handle readiness probe (K8s style)."""
        # Simple check - just verify the application is running
        return web.json_response({
            "status": "ready",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        })

    async def handle_liveness_check(self, request: web.Request) -> web.Response:
        """Handle liveness probe (K8s style)."""
        # Simple check - just verify the application is alive
        return web.json_response({
            "status": "alive",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "uptime_seconds": time.time() - self.health_checker.start_time
        })

    def attach_to_app(self, app: web.Application, health_endpoint: str = "/health"):
        """Attach health check routes to the application."""
        app.router.add_get(health_endpoint, self.handle_health_check)
        app.router.add_get(f"{health_endpoint}/ready", self.handle_readiness_check)
        app.router.add_get(f"{health_endpoint}/live", self.handle_liveness_check)
