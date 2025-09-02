import logging
import time
from typing import Dict, Any
from aiohttp import web
from azure.storage.blob.aio import ContainerClient, BlobServiceClient
from azure.storage.blob import generate_blob_sas, BlobSasPermissions
from azure.core.exceptions import AzureError, ResourceNotFoundError

from datetime import datetime, timedelta

# Set up structured logging
logger = logging.getLogger(__name__)


class CitationFilesHandler:
    """
    Production-ready handler for serving citation files with enhanced security,
    logging, and error handling.
    """
    
    # Security and performance constants
    DEFAULT_SAS_DURATION_MINUTES = 60
    MAX_SAS_DURATION_MINUTES = 240  # 4 hours max
    SUPPORTED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg'}
    
    def __init__(
        self,
        blob_service_client: BlobServiceClient,
        samples_container_client: ContainerClient,
        artifacts_container_client: ContainerClient,
        sas_duration_minutes: int = DEFAULT_SAS_DURATION_MINUTES
    ):
        """
        Initialize citation files handler.
        
        Args:
            blob_service_client: Azure Blob Service client
            samples_container_client: Container client for document samples
            artifacts_container_client: Container client for images/figures
            sas_duration_minutes: SAS token duration in minutes
        """
        self.container_client = samples_container_client
        self.artifacts_container_client = artifacts_container_client
        self.blob_service_client = blob_service_client
        self.sas_duration_minutes = min(sas_duration_minutes, self.MAX_SAS_DURATION_MINUTES)
        
        logger.info("Citation files handler initialized", extra={
            "sas_duration_minutes": self.sas_duration_minutes,
            "supported_image_extensions": list(self.SUPPORTED_IMAGE_EXTENSIONS)
        })

    def _validate_filename(self, filename: str) -> None:
        """
        Validate filename for security and format compliance.
        
        Args:
            filename: Filename to validate
            
        Raises:
            ValueError: If filename is invalid
        """
        if not filename or not isinstance(filename, str):
            raise ValueError("Filename is required and must be a string")
            
        # Basic security checks
        if any(char in filename for char in ['..', '<', '>', ':', '"', '|', '?', '*']):
            raise ValueError("Filename contains invalid characters")
            
        # Check for null bytes and other dangerous patterns
        if '\x00' in filename or len(filename) > 500:
            raise ValueError("Invalid filename format")

    def _is_image_file(self, blob_name: str) -> bool:
        """
        Determine if the file is an image based on extension and path patterns.
        
        Args:
            blob_name: Blob name/path
            
        Returns:
            True if file appears to be an image
        """
        blob_lower = blob_name.lower()
        
        # Check file extension
        for ext in self.SUPPORTED_IMAGE_EXTENSIONS:
            if blob_lower.endswith(ext):
                return True
        
        # Check for figure patterns
        if 'figure_' in blob_lower or '/images/' in blob_lower or '/figures/' in blob_lower:
            return True
            
        return False

    async def handle(self, request):
        """
        Handle citation file requests with enhanced error handling and monitoring.
        
        Args:
            request: HTTP request containing fileName in JSON body
            
        Returns:
            JSON response with signed URL or error message
        """
        request_id = f"citation_{int(time.time())}"
        start_time = time.time()
        
        try:
            # Validate request body
            try:
                data = await request.json()
            except Exception as e:
                logger.warning("Invalid JSON in citation request", extra={
                    "request_id": request_id,
                    "error": str(e),
                    "remote_addr": request.remote
                })
                return web.json_response({
                    "status": "error", 
                    "message": "Invalid JSON in request body"
                }, status=400)

            filename = data.get("fileName")
            if not filename:
                logger.warning("Missing fileName in citation request", extra={
                    "request_id": request_id,
                    "data": data,
                    "remote_addr": request.remote
                })
                return web.json_response({
                    "status": "error", 
                    "message": "fileName is required"
                }, status=400)

            # Validate filename
            try:
                self._validate_filename(filename)
            except ValueError as e:
                logger.warning("Invalid filename in citation request", extra={
                    "request_id": request_id,
                    "file_name": filename,
                    "error": str(e),
                    "remote_addr": request.remote
                })
                return web.json_response({
                    "status": "error", 
                    "message": str(e)
                }, status=400)

            logger.info("Processing citation file request", extra={
                "request_id": request_id,
                "file_name": filename,
                "remote_addr": request.remote
            })

            # Get signed URL
            response = await self._get_file_url(filename, request_id)
            
            duration = time.time() - start_time
            logger.info("Citation file request completed", extra={
                "request_id": request_id,
                "file_name": filename,
                "duration_seconds": round(duration, 3)
            })
            
            return web.json_response({
                "status": "success",
                "url": response
            })
            
        except ResourceNotFoundError as e:
            logger.warning("Citation file not found", extra={
                "request_id": request_id,
                "file_name": filename if 'filename' in locals() else "unknown",
                "error": str(e)
            })
            return web.json_response({
                "status": "error", 
                "message": "File not found"
            }, status=404)
            
        except AzureError as e:
            logger.error("Azure service error in citation handler", extra={
                "request_id": request_id,
                "file_name": filename if 'filename' in locals() else "unknown",
                "error_type": "AzureError",
                "error": str(e)
            }, exc_info=True)
            return web.json_response({
                "status": "error", 
                "message": "Storage service error"
            }, status=500)
            
        except Exception as e:
            logger.error("Unexpected error in citation handler", extra={
                "request_id": request_id,
                "file_name": filename if 'filename' in locals() else "unknown",
                "error_type": type(e).__name__,
                "error": str(e)
            }, exc_info=True)
            return web.json_response({
                "status": "error", 
                "message": "Internal server error"
            }, status=500)

    async def _get_file_url(self, blob_name: str, request_id: str = "") -> str:
        """
        Generate a secure SAS URL for the requested file.
        
        Args:
            blob_name: Name/path of the blob
            request_id: Request ID for logging correlation
            
        Returns:
            Signed URL for the file
            
        Raises:
            ResourceNotFoundError: If file doesn't exist
            AzureError: If Azure service error occurs
        """
        try:
            # Normalize blob path
            normalized_blob_name = blob_name.replace("\\", "/")
            
            # Determine container based on file type
            is_image = self._is_image_file(normalized_blob_name)
            container_client = self.artifacts_container_client if is_image else self.container_client
            container_name = "artifacts" if is_image else "samples"
            
            logger.debug("Generating SAS URL", extra={
                "request_id": request_id,
                "blob_name": normalized_blob_name,
                "is_image": is_image,
                "container": container_name
            })
            
            # Get blob client
            blob_client = container_client.get_blob_client(normalized_blob_name)
            
            # Check if blob exists
            blob_exists = await blob_client.exists()
            if not blob_exists:
                logger.warning("Requested blob does not exist", extra={
                    "request_id": request_id,
                    "blob_name": normalized_blob_name,
                    "container": container_name
                })
                raise ResourceNotFoundError(f"Blob '{normalized_blob_name}' not found in container '{container_name}'")
            
            # Generate user delegation key for secure access
            start_time = datetime.utcnow()
            expiry_time = start_time + timedelta(hours=1)
            
            user_delegation_key = await self.blob_service_client.get_user_delegation_key(
                key_start_time=start_time, 
                key_expiry_time=expiry_time
            )
            
            # Generate SAS token
            sas_token = generate_blob_sas(
                account_name=blob_client.account_name or "",
                container_name=container_client.container_name,
                blob_name=normalized_blob_name,
                user_delegation_key=user_delegation_key,
                permission=BlobSasPermissions(read=True),
                expiry=datetime.utcnow() + timedelta(minutes=self.sas_duration_minutes),
            )

            signed_url = f"{blob_client.url}?{sas_token}"
            
            logger.info("SAS URL generated successfully", extra={
                "request_id": request_id,
                "blob_name": normalized_blob_name,
                "container": container_name,
                "sas_duration_minutes": self.sas_duration_minutes
            })
            
            return signed_url
            
        except ResourceNotFoundError:
            # Re-raise as-is
            raise
        except AzureError as e:
            logger.error("Azure error generating SAS URL", extra={
                "request_id": request_id,
                "blob_name": blob_name,
                "error_type": "AzureError",
                "error": str(e)
            }, exc_info=True)
            raise
        except Exception as e:
            logger.error("Unexpected error generating SAS URL", extra={
                "request_id": request_id,
                "blob_name": blob_name,
                "error_type": type(e).__name__,
                "error": str(e)
            }, exc_info=True)
            raise AzureError(f"Failed to generate SAS URL: {str(e)}")
