"""
Centralized Azure client factory that returns a cached bundle of async clients
per (session_id, auth_mode). Supports Managed Identity (DefaultAzureCredential)
and API key/connection string based authentication.

Design notes:
- Async factory because several Azure async clients and DefaultAzureCredential
  async variant are used in the codebase.
- Session cache keyed by (session_id, AuthMode). Callers should clear when the
  session ends using clear_session.
"""
from __future__ import annotations

import os
import logging
from enum import Enum
from dataclasses import dataclass
from typing import Callable, Optional, Dict, Tuple

from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider, ClientSecretCredential
from azure.core.credentials import AzureKeyCredential
from azure.storage.blob.aio import BlobServiceClient
from azure.search.documents.aio import SearchClient
from azure.search.documents.indexes.aio import SearchIndexClient
from azure.ai.documentintelligence.aio import DocumentIntelligenceClient
from openai import AsyncAzureOpenAI

from .config import get_config

logger = logging.getLogger("azure_client_factory")


class AuthMode(Enum):
    MANAGED_IDENTITY = "managed_identity"
    API_KEY = "api_key"


@dataclass
class SessionClients:
    """Bundle of ready-to-use async clients for a session."""
    openai_client: AsyncAzureOpenAI
    blob_service_client: BlobServiceClient
    document_intelligence_client: Optional[DocumentIntelligenceClient]
    get_search_client: Callable[[str], SearchClient]
    search_index_client: SearchIndexClient
    credential: Optional[DefaultAzureCredential]
    auth_mode: AuthMode

    async def close(self) -> None:
        """Close any aio clients to clean up resources."""
        # Close blob client
        try:
            await self.blob_service_client.close()
        except Exception:
            logger.debug("Error closing blob_service_client", exc_info=True)

        # Close search index client if it has close
        try:
            await self.search_index_client.close()
        except Exception:
            logger.debug("Error closing search_index_client", exc_info=True)

        # Note: openai AsyncAzureOpenAI doesn't have close; DocumentIntelligenceClient does
        if self.document_intelligence_client is not None:
            try:
                await self.document_intelligence_client.close()
            except Exception:
                logger.debug("Error closing document_intelligence_client", exc_info=True)


class ClientFactory:
    """Factory that builds and caches SessionClients bundles."""

    # cache keyed by (session_id, auth_mode.value)
    _cache: Dict[Tuple[str, str], SessionClients] = {}

    # track event loop id when bundle was created to avoid reuse across loops
    _bundle_loop_id: Dict[Tuple[str, str], int] = {}
    # counter for how many times cached bundles were invalidated/recreated
    _invalidation_count: int = 0

    @classmethod
    async def get_session_clients(cls, session_id: str, auth_mode: AuthMode) -> SessionClients:
        key = (session_id, auth_mode.value)
        if key in cls._cache:
            # verify the cached bundle was created on the same running event loop
            try:
                import asyncio
                current_loop_id = id(asyncio.get_running_loop())
                created_loop_id = cls._bundle_loop_id.get(key)
                if created_loop_id is not None and created_loop_id != current_loop_id:
                    # loop mismatch: clear old bundle and recreate
                    logger.warning("Cached session clients were created on a different event loop; recreating", extra={"session_id": session_id, "auth_mode": auth_mode.value})
                    try:
                        await cls.clear_session(session_id, auth_mode)
                    except Exception:
                        logger.debug("Error clearing stale session bundle", exc_info=True)
                else:
                    logger.info("Reusing cached session clients", extra={"session_id": session_id, "auth_mode": auth_mode.value})
                    return cls._cache[key]
            except RuntimeError:
                # no running loop; fall through to create a new bundle
                logger.debug("No running event loop detected when checking cached bundle; recreating bundle")

        config = get_config()

        credential: Optional[DefaultAzureCredential] = None

        # Prepare client kwargs (user agent etc can be added here)
        client_kwargs = {}

        # Build credential and clients based on auth mode
        # OpenAI: needs special bearer token provider for AAD path
        openai_client: AsyncAzureOpenAI
        blob_client: BlobServiceClient
        docint_client: Optional[DocumentIntelligenceClient] = None

        if auth_mode == AuthMode.MANAGED_IDENTITY:
            # Prefer an explicit ClientSecretCredential constructed from .env values when present.
            # This lets local runs that load `.env` (via load_dotenv) use the SPN defined there without
            # requiring the variables to be exported into the system environment outside Python.
            tenant_id = os.environ.get("AZURE_TENANT_ID")
            client_id = os.environ.get("AZURE_CLIENT_ID")
            client_secret = os.environ.get("AZURE_CLIENT_SECRET")
            if tenant_id and client_id and client_secret:
                logger.info("Initializing clients using ClientSecretCredential (from .env)", extra={"session_id": session_id})
                credential = ClientSecretCredential(tenant_id, client_id, client_secret)
                # Record and log the event loop id that created this credential to aid debugging
                try:
                    import asyncio
                    created_loop_id = id(asyncio.get_running_loop())
                    logger.info("ClientSecretCredential created on loop", extra={"session_id": session_id, "loop_id": created_loop_id})
                except Exception:
                    logger.debug("Could not determine event loop id after creating ClientSecretCredential", exc_info=True)
            else:
                logger.info("Initializing clients using Managed Identity (DefaultAzureCredential)", extra={"session_id": session_id})
                credential = DefaultAzureCredential()
            # Diagnostic: verify we can obtain a storage scope token using the credential
            try:
                # `get_token` is async on DefaultAzureCredential (aio) and returns an AccessToken
                token = await credential.get_token("https://storage.azure.com/.default")
                logger.info("DefaultAzureCredential acquired storage token", extra={"session_id": session_id, "expires_on": getattr(token, 'expires_on', None)})
            except Exception as e:
                logger.error("DefaultAzureCredential failed to acquire storage token", extra={"session_id": session_id, "error": str(e)} , exc_info=True)

            # OpenAI bearer token provider
            token_provider = get_bearer_token_provider(
                credential,
                "https://cognitiveservices.azure.com/.default",
            )

            openai_client = AsyncAzureOpenAI(
                azure_ad_token_provider=token_provider,
                api_version=config.azure_openai.api_version,
                azure_endpoint=config.azure_openai.endpoint,
                timeout=config.azure_openai.timeout,
                max_retries=config.azure_openai.max_retries,
            )

            # Blob (use AAD credential)
            blob_client = BlobServiceClient(
                account_url=config.storage.artifacts_account_url,
                credential=credential,
            )
            # Log the type of credential attached to the blob client for debugging
            try:
                logger.debug("BlobServiceClient created with credential type", extra={"session_id": session_id, "credential_type": type(blob_client.credential).__name__})
            except Exception:
                logger.debug("Could not determine blob client credential type", exc_info=True)

            # Document Intelligence: AAD works only on custom subdomain endpoints
            doc_endpoint = config.document_intelligence.endpoint
            if doc_endpoint and ("cognitiveservices.azure.com" in doc_endpoint or ".cognitiveservices." in doc_endpoint):
                try:
                    docint_client = DocumentIntelligenceClient(endpoint=doc_endpoint, credential=credential)
                except Exception as e:
                    logger.warning("Failed creating Document Intelligence client with AAD; falling back to key if available", exc_info=True)
                    docint_client = None
            else:
                # Endpoint likely regional; fall back to key auth automatically
                logger.info("Document Intelligence endpoint does not appear to support AAD; will attempt key-based auth", extra={"endpoint": doc_endpoint})
                docint_client = None

        else:
            logger.info("Initializing clients using API Key / connection string auth", extra={"session_id": session_id})

            # OpenAI with API key
            if not config.azure_openai.api_key:
                raise ValueError("API key auth selected but AZURE_OPENAI_API_KEY is missing")

            openai_client = AsyncAzureOpenAI(
                api_key=config.azure_openai.api_key,
                api_version=config.azure_openai.api_version,
                azure_endpoint=config.azure_openai.endpoint,
                timeout=config.azure_openai.timeout,
                max_retries=config.azure_openai.max_retries,
            )

            # Blob with connection string
            # Prefer existing account key env var used in repo; fall back to connection string
            account_key = os.environ.get("ARTIFACTS_STORAGE_ACCOUNT_KEY")
            conn_str = os.environ.get("ARTIFACTS_STORAGE_CONNECTION_STRING")
            if account_key:
                # Keep compatibility with existing code that passed the key string directly
                blob_client = BlobServiceClient(
                    account_url=config.storage.artifacts_account_url,
                    credential=account_key,
                )
                try:
                    logger.debug("BlobServiceClient created with account key", extra={"session_id": session_id})
                except Exception:
                    logger.debug("Could not log account key blob client creation", exc_info=True)
            elif conn_str:
                blob_client = BlobServiceClient.from_connection_string(conn_str)
            else:
                # If neither is present, attempt to create with account_url only (may require anonymous/public access)
                logger.warning("No storage account key or connection string found; attempting BlobServiceClient using account_url (may fail)")
                blob_client = BlobServiceClient(account_url=config.storage.artifacts_account_url)
                try:
                    logger.debug("BlobServiceClient created without explicit credential", extra={"session_id": session_id})
                except Exception:
                    logger.debug("Could not log anonymous blob client creation", exc_info=True)

            # Document Intelligence using key if available
            if config.document_intelligence.key:
                docint_client = DocumentIntelligenceClient(endpoint=config.document_intelligence.endpoint, credential=AzureKeyCredential(config.document_intelligence.key))
            else:
                docint_client = None

        # Search credential: prefer API key if present and auth_mode==API_KEY, else AAD credential
        if auth_mode == AuthMode.API_KEY and config.search_service.api_key:
            search_cred = AzureKeyCredential(config.search_service.api_key)
        else:
            # If credential is None here, DefaultAzureCredential will be created for search as needed
            search_cred = credential or DefaultAzureCredential()

        # Build search index client
        search_index_client = SearchIndexClient(
            endpoint=config.search_service.endpoint,
            credential=search_cred,
            **client_kwargs,
        )

        def get_search_client(index_name: str) -> SearchClient:
            return SearchClient(
                endpoint=config.search_service.endpoint,
                index_name=index_name,
                credential=search_cred,
                **client_kwargs,
            )

        bundle = SessionClients(
            openai_client=openai_client,
            blob_service_client=blob_client,
            document_intelligence_client=docint_client,
            get_search_client=get_search_client,
            search_index_client=search_index_client,
            credential=credential,
            auth_mode=auth_mode,
        )
        cls._cache[key] = bundle
        try:
            import asyncio
            cls._bundle_loop_id[key] = id(asyncio.get_running_loop())
        except RuntimeError:
            # if no running loop, ignore loop tracking
            cls._bundle_loop_id.pop(key, None)
        logger.info("Session clients created and cached", extra={"session_id": session_id, "auth_mode": auth_mode.value})
        return bundle

    @classmethod
    async def clear_session(cls, session_id: str, auth_mode: AuthMode) -> None:
        key = (session_id, auth_mode.value)
        bundle = cls._cache.pop(key, None)
        # Remove loop tracking for this bundle as well
        cls._bundle_loop_id.pop(key, None)

        if bundle:
            try:
                await bundle.close()
            except Exception:
                logger.debug("Error while closing session clients", exc_info=True)
            # increment invalidation counter
            try:
                cls._invalidation_count += 1
            except Exception:
                pass
            logger.info("Cleared cached session bundle", extra={"session_id": session_id, "auth_mode": auth_mode.value, "invalidation_count": cls._invalidation_count})

    @classmethod
    async def clear_all(cls) -> None:
        keys = list(cls._cache.keys())
        for key in keys:
            bundle = cls._cache.pop(key, None)
            # remove loop id tracking
            cls._bundle_loop_id.pop(key, None)

            if bundle:
                try:
                    await bundle.close()
                except Exception:
                    logger.debug("Error while closing session clients", exc_info=True)
                try:
                    cls._invalidation_count += 1
                except Exception:
                    pass
