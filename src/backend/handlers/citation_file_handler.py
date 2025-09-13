import logging
import os
import time
from typing import Dict, Any
from aiohttp import web
from azure.storage.blob.aio import ContainerClient, BlobServiceClient
from azure.identity.aio import DefaultAzureCredential
from azure.storage.blob import generate_blob_sas, BlobSasPermissions
from azure.core.exceptions import AzureError, ResourceNotFoundError

from datetime import datetime, timedelta
from core.config import get_config
from core.azure_client_factory import AuthMode

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

            # Prefer a request-scoped bundle (set by SessionResolverMiddleware) so
            # that we reuse the cached session BlobServiceClient when available.
            bundle = request.get("session_bundle")
            if bundle is not None:
                # derive container clients from the bundle's blob service client
                blob_service_client = bundle.blob_service_client
                # Use configured container names from app config (do not hardcode)
                try:
                    cfg = get_config()
                    samples_container_client = blob_service_client.get_container_client(cfg.storage.samples_container)
                    artifacts_container_client = blob_service_client.get_container_client(cfg.storage.artifacts_container)
                except Exception:
                    # If anything goes wrong, fall back to the pre-initialized container clients
                    samples_container_client = self.container_client
                    artifacts_container_client = self.artifacts_container_client
            else:
                # fall back to the instances provided at construction
                blob_service_client = self.blob_service_client
                samples_container_client = self.container_client
                artifacts_container_client = self.artifacts_container_client

            # Determine auth_mode from session bundle if available and pass it explicitly
            auth_mode = None
            if bundle is not None and hasattr(bundle, 'auth_mode'):
                auth_mode = bundle.auth_mode

            # Get signed URL - pass explicit auth_mode so logic is deterministic
            response = await self._get_file_url(
                filename,
                request_id,
                blob_service_client=blob_service_client,
                samples_container_client=samples_container_client,
                artifacts_container_client=artifacts_container_client,
                auth_mode=auth_mode,
            )
            
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

    async def _get_file_url(
        self,
        blob_name: str,
        request_id: str = "",
        blob_service_client: BlobServiceClient = None,
        samples_container_client: ContainerClient = None,
        artifacts_container_client: ContainerClient = None,
        auth_mode: AuthMode = None,
    ) -> str:
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
        # Normalize blob path
        normalized_blob_name = blob_name.replace("\\", "/")

        # Determine container based on file type
        is_image = self._is_image_file(normalized_blob_name)

        # If the caller didn't provide container/blob clients, fall back to instance attributes
        if blob_service_client is None:
            blob_service_client = self.blob_service_client
        if samples_container_client is None:
            samples_container_client = self.container_client
        if artifacts_container_client is None:
            artifacts_container_client = self.artifacts_container_client

        container_client = artifacts_container_client if is_image else samples_container_client
        container_name = "artifacts" if is_image else "samples"

        logger.debug("Generating SAS URL", extra={
            "request_id": request_id,
            "blob_name": normalized_blob_name,
            "is_image": is_image,
            "container": container_name,
        })

        try:
            # Get blob client
            blob_client = container_client.get_blob_client(normalized_blob_name)

            # Check if blob exists. If key-based auth is rejected by the service,
            # try an AAD-backed client (DefaultAzureCredential) and/or fall back
            # to account-key SAS using an available key.
            blob_exists = await blob_client.exists()
            if not blob_exists:
                logger.warning("Requested blob does not exist", extra={
                    "request_id": request_id,
                    "blob_name": normalized_blob_name,
                    "container": container_name,
                })
                raise ResourceNotFoundError(
                    f"Blob '{normalized_blob_name}' not found in container '{container_name}'"
                )

            # Generate SAS based on explicit auth_mode when provided
            start_time = datetime.utcnow()
            expiry_time = start_time + timedelta(hours=1)

            sas_token = None
            # If auth_mode is explicitly Managed Identity, only use user delegation key
            if auth_mode == AuthMode.MANAGED_IDENTITY:
                try:
                    # Diagnostic: log credential type attached to blob_service_client and try to fetch a token
                    try:
                        cred = getattr(blob_service_client, 'credential', None)
                        if cred is not None:
                            cred_type = type(cred).__name__
                        else:
                            cred_type = None
                        logger.info("Attempting user-delegation key: blob client credential info", extra={"request_id": request_id, "credential_type": cred_type})
                        # If credential supports get_token, try to obtain a storage token to validate Bearer issuance
                        if cred is not None and hasattr(cred, 'get_token'):
                            try:
                                token = await cred.get_token("https://storage.azure.com/.default")
                                logger.info("Credential.get_token succeeded before get_user_delegation_key", extra={"request_id": request_id, "expires_on": getattr(token, 'expires_on', None)})
                            except Exception as token_ex:
                                logger.error("Credential.get_token failed before get_user_delegation_key", extra={"request_id": request_id, "error": str(token_ex)}, exc_info=True)
                        else:
                            logger.info("BlobServiceClient.credential does not expose get_token; cannot validate token issuance", extra={"request_id": request_id, "credential_type": cred_type})
                    except Exception:
                        logger.debug("Credential diagnostic check failed", extra={"request_id": request_id}, exc_info=True)

                    # If the existing blob_service_client is not AAD/Bearer-capable (for example,
                    # constructed with an account key), the Storage service will reject a
                    # get_user_delegation_key call. In that case, create a temporary
                    # AAD-backed BlobServiceClient using DefaultAzureCredential to request
                    # the user delegation key. This is deliberate and only used when
                    # auth_mode == MANAGED_IDENTITY and the provided client cannot issue
                    # a Bearer token. We log the behavior so it is visible in production.
                    temp_cred = None
                    temp_blob_service_client = None
                    try:
                        cred = getattr(blob_service_client, 'credential', None)
                        needs_temp_aad = not (cred is not None and hasattr(cred, 'get_token'))

                        if needs_temp_aad:
                            logger.info(
                                "BlobServiceClient not AAD-capable; creating temporary AAD-backed client for user-delegation key",
                                extra={"request_id": request_id, "blob_account": blob_client.account_name}
                            )
                            temp_cred = DefaultAzureCredential()
                            # Use the same account URL as the provided service client
                            account_url = getattr(blob_service_client, 'url', None)
                            if not account_url:
                                # Fallback to constructing from account name
                                account_name = getattr(blob_client, 'account_name', None) or getattr(blob_service_client, 'account_name', None)
                                account_url = f"https://{account_name}.blob.core.windows.net"

                            temp_blob_service_client = BlobServiceClient(account_url=account_url, credential=temp_cred)
                            user_delegation_key = await temp_blob_service_client.get_user_delegation_key(
                                key_start_time=start_time, key_expiry_time=expiry_time
                            )
                        else:
                            user_delegation_key = await blob_service_client.get_user_delegation_key(
                                key_start_time=start_time, key_expiry_time=expiry_time
                            )

                        sas_token = generate_blob_sas(
                            account_name=blob_client.account_name or "",
                            container_name=container_client.container_name,
                            blob_name=normalized_blob_name,
                            user_delegation_key=user_delegation_key,
                            permission=BlobSasPermissions(read=True),
                            expiry=datetime.utcnow() + timedelta(minutes=self.sas_duration_minutes),
                        )
                    finally:
                        # Close temporary clients/credentials if created to avoid leaks
                        if temp_blob_service_client is not None:
                            try:
                                await temp_blob_service_client.close()
                            except Exception:
                                logger.debug("Failed closing temporary BlobServiceClient", extra={"request_id": request_id}, exc_info=True)
                        if temp_cred is not None:
                            try:
                                await temp_cred.close()
                            except Exception:
                                logger.debug("Failed closing temporary DefaultAzureCredential", extra={"request_id": request_id}, exc_info=True)
                except Exception as ade:
                    logger.error("Managed Identity auth selected but user-delegation key request failed", extra={"request_id": request_id, "error": str(ade)})
                    # Surface error to caller (no silent fallback allowed)
                    raise

            # If auth_mode is explicitly API_KEY, only use account-key SAS
            elif auth_mode == AuthMode.API_KEY:
                # Try to extract an account key from the provided blob_service_client if possible
                account_key = None
                try:
                    cred = getattr(blob_service_client, "credential", None)
                    if isinstance(cred, str) and cred:
                        account_key = cred
                    elif hasattr(cred, "key"):
                        account_key = getattr(cred, "key")
                except Exception:
                    account_key = None

                if not account_key:
                    account_key = os.environ.get("ARTIFACTS_STORAGE_ACCOUNT_KEY")

                if account_key:
                    sas_token = generate_blob_sas(
                        account_name=blob_client.account_name or "",
                        container_name=container_client.container_name,
                        blob_name=normalized_blob_name,
                        account_key=account_key,
                        permission=BlobSasPermissions(read=True),
                        expiry=datetime.utcnow() + timedelta(minutes=self.sas_duration_minutes),
                    )
                else:
                    logger.error("API_KEY auth selected but no account key available to generate SAS", extra={"request_id": request_id})
                    raise

            else:
                # No explicit auth_mode: preserve original behavior (try user delegation then account-key fallback)
                try:
                    user_delegation_key = await blob_service_client.get_user_delegation_key(
                        key_start_time=start_time, key_expiry_time=expiry_time
                    )
                    sas_token = generate_blob_sas(
                        account_name=blob_client.account_name or "",
                        container_name=container_client.container_name,
                        blob_name=normalized_blob_name,
                        user_delegation_key=user_delegation_key,
                        permission=BlobSasPermissions(read=True),
                        expiry=datetime.utcnow() + timedelta(minutes=self.sas_duration_minutes),
                    )
                except Exception as ade:
                    logger.warning(
                        "User-delegation key unavailable or failed, attempting account-key SAS fallback",
                        extra={"request_id": request_id, "error": str(ade)}
                    )

                    account_key = None
                    try:
                        cred = getattr(blob_service_client, "credential", None)
                        if isinstance(cred, str) and cred:
                            account_key = cred
                        elif hasattr(cred, "key"):
                            account_key = getattr(cred, "key")
                    except Exception:
                        account_key = None

                    if not account_key:
                        account_key = os.environ.get("ARTIFACTS_STORAGE_ACCOUNT_KEY")

                    if account_key:
                        sas_token = generate_blob_sas(
                            account_name=blob_client.account_name or "",
                            container_name=container_client.container_name,
                            blob_name=normalized_blob_name,
                            account_key=account_key,
                            permission=BlobSasPermissions(read=True),
                            expiry=datetime.utcnow() + timedelta(minutes=self.sas_duration_minutes),
                        )
                    else:
                        raise

            signed_url = f"{blob_client.url}?{sas_token}"

            logger.info("SAS URL generated successfully", extra={
                "request_id": request_id,
                "blob_name": normalized_blob_name,
                "container": container_name,
                "sas_duration_minutes": self.sas_duration_minutes,
            })

            return signed_url

        except ResourceNotFoundError:
            # Re-raise as-is
            raise
        except AzureError as e:
            logger.error(
                "Azure error generating SAS URL",
                extra={
                    "request_id": request_id,
                    "blob_name": blob_name,
                    "error_type": "AzureError",
                    "error": str(e),
                },
                exc_info=True,
            )
            raise
        except Exception as e:
            logger.error(
                "Unexpected error generating SAS URL",
                extra={
                    "request_id": request_id,
                    "blob_name": blob_name,
                    "error_type": type(e).__name__,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise AzureError(f"Failed to generate SAS URL: {str(e)}")
