"""
Production-ready AI Search Multimodal Application.
Enhanced with logging, monitoring, error handling, and performance optimizations.
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional
import logging

# Comprehensive fix for Windows event loop and DNS issues
if sys.platform == 'win32':
    # Force disable aiodns extension for aiohttp on Windows
    os.environ['AIOHTTP_NO_EXTENSIONS'] = '1'
    
    # Use SelectorEventLoop for Windows to avoid aiodns issues
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # Monkey patch to ensure aiohttp doesn't use aiodns
    try:
        import aiohttp.resolver
        # Force use of built-in resolver instead of aiodns
        aiohttp.resolver.DefaultResolver = aiohttp.resolver.AsyncResolver
    except ImportError:
        pass  # aiohttp not installed yet, will be handled later

from aiohttp import web
from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.aio import SearchClient
from azure.search.documents.indexes.models import (
    SearchIndex, SearchField, SearchFieldDataType, VectorSearch, VectorSearchProfile,
    VectorSearchAlgorithmConfiguration, HnswAlgorithmConfiguration, VectorSearchAlgorithmKind,
    SemanticConfiguration, SemanticPrioritizedFields, SemanticField, SemanticSearch,
    SimpleField, SearchableField, ComplexField, AzureOpenAIVectorizer,
    AzureOpenAIVectorizerParameters, ScoringProfile, ScoringFunction,
    FreshnessScoringFunction, FreshnessScoringParameters, TextWeights,
)
from azure.search.documents.indexes.aio import SearchIndexClient
from azure.search.documents.agent.aio import KnowledgeAgentRetrievalClient
from azure.core.pipeline.policies import UserAgentPolicy
from azure.core.pipeline.transport import AioHttpTransport
from azure.storage.blob.aio import BlobServiceClient
from openai import AsyncAzureOpenAI
import aiohttp

# Import application modules
from admin.admin_handler import AdminHandler
from retrieval.search_grounding import SearchGroundingRetriever
from retrieval.knowledge_agent import KnowledgeAgentGrounding
from retrieval.multimodal_rag import MultimodalRag
from core.data_model import DocumentPerChunkDataModel
from handlers.citation_file_handler import CitationFilesHandler
from handlers.upload_handler import upload_handler
from handlers.feedback_handler import FeedbackHandler
from constants import USER_AGENT

# Import production-ready components
from core.config import get_config, ApplicationConfig
from core.azure_client_factory import ClientFactory, AuthMode
from core.exceptions import ApplicationError, ConfigurationError, handle_azure_error
from middleware import create_middleware_stack
from utils.logging_config import setup_logging, StructuredLogger
from utils.health_check import HealthChecker, HealthHandler
from utils.resilience import ResilientClient, RetryConfig, CircuitBreakerConfig, with_timeout


class ProductionApp:
    """Production-ready application wrapper with enhanced error handling and monitoring."""

    def __init__(self, config: ApplicationConfig):
        self.config = config
        self.logger = StructuredLogger("app")
        self.health_checker = HealthChecker(config)
        self.health_handler = HealthHandler(self.health_checker)
        
        # Initialize clients that will be set later
        self._search_client: Optional[SearchClient] = None
        self._index_client: Optional[SearchIndexClient] = None
        self._openai_client: Optional[AsyncAzureOpenAI] = None
        self._blob_service_client: Optional[BlobServiceClient] = None

    async def initialize_azure_clients(self) -> tuple:
        """Initialize Azure service clients with proper error handling and resilience."""
        try:
            # Auto-detect auth mode from existing configured API keys to avoid new env vars
            if self.config.azure_openai.api_key or self.config.search_service.api_key or self.config.document_intelligence.key:
                auth_mode = AuthMode.API_KEY
            else:
                auth_mode = AuthMode.MANAGED_IDENTITY

            # Use a default application-level session id
            session_id = "app_startup"

            # Clear any cached client bundles created on other event loops to avoid
            # "Future attached to a different loop" errors when using aio credentials.
            # This ensures credentials are constructed on the current running loop.
            try:
                await ClientFactory.clear_all()
            except Exception:
                self.logger.debug("Failed to clear cached client bundles (ignored)", exc_info=True)

            bundle = await ClientFactory.get_session_clients(session_id, auth_mode)

            # Save clients locally
            # The app previously expected a SearchClient (for a specific index name) and SearchIndexClient
            self._openai_client = bundle.openai_client
            self._blob_service_client = bundle.blob_service_client
            self._search_client = bundle.get_search_client(self.config.search_service.index_name)
            self._index_client = bundle.search_index_client
            token_credential = bundle.credential

            self.logger.info("Azure clients initialized successfully via ClientFactory", extra={"auth_mode": auth_mode.value})

            return (
                self._search_client,
                self._index_client,
                self._openai_client,
                self._blob_service_client,
                token_credential,
                auth_mode,
            )

        except Exception as e:
            self.logger.error(f"Failed to initialize Azure clients: {e}", exc_info=True)
            raise ConfigurationError(f"Azure client initialization failed: {e}", original_error=e)

    async def create_application(self) -> web.Application:
        """Create and configure the web application."""
        try:
            # Initialize Azure clients
            search_client, index_client, openai_client, blob_service_client, token_credential, auth_mode = (
                await self.initialize_azure_clients()
            )

            # Set up health checker with clients
            self.health_checker.set_clients(search_client, blob_service_client, openai_client)

            # Create or align the search index schema
            await self._create_search_index_if_not_exists(
                index_client, 
                self.config.search_service.index_name,
                self.config.knowledge_agent_name
            )

            # Initialize container clients
            artifacts_container_client = blob_service_client.get_container_client(
                self.config.storage.artifacts_container
            )
            samples_container_client = blob_service_client.get_container_client(
                self.config.storage.samples_container
            )

            # Initialize knowledge agent with error handling
            # pass the detected auth_mode so components can log which auth they will use
            knowledge_agent = await self._initialize_knowledge_agent(
                search_client,
                index_client,
                blob_service_client,
                artifacts_container_client,
                samples_container_client,
                token_credential,
                auth_mode,
            )

            # Initialize search grounding
            data_model = DocumentPerChunkDataModel()
            search_grounding = SearchGroundingRetriever(
                search_client,
                openai_client,
                data_model,
                self.config.azure_openai.deployment,
                blob_service_client,
                samples_container_client,
                artifacts_container_client,
                auth_mode=auth_mode,
            )
            self.logger.info('SearchGroundingRetriever created with auth_mode', extra={'auth_mode': auth_mode.value})

            # Create web application with middleware
            middleware_stack = create_middleware_stack(
                security_config=self.config.security,
                enable_request_logging=self.config.logging.enable_request_logging,
                enable_performance_logging=self.config.logging.enable_performance_logging,
                enable_validation=self.config.security.enable_request_validation
            )

            app = web.Application(
                middlewares=middleware_stack,
                client_max_size=self.config.server.max_request_size
            )

            # Initialize feedback handler
            feedback_handler = FeedbackHandler(
                search_index_client=index_client,
                openai_client=openai_client,
                embedding_deployment=self.config.azure_openai.embedding_deployment
            )

            # Initialize multimodal RAG with feedback handler for caching
            mmrag = MultimodalRag(
                knowledge_agent,
                search_grounding,
                openai_client,
                self.config.azure_openai.deployment,
                artifacts_container_client,
                feedback_handler,  # Pass feedback handler for cache checking
            )
            mmrag.attach_to_app(app, "/chat")

            # Initialize handlers
            citation_files_handler = CitationFilesHandler(
                blob_service_client, samples_container_client, artifacts_container_client
            )
            admin_handler = AdminHandler()

            # Add routes
            await self._setup_routes(app, index_client, citation_files_handler, admin_handler, search_client, feedback_handler)

            # Attach health check endpoints
            if self.config.monitoring.enable_health_checks:
                self.health_handler.attach_to_app(app, self.config.monitoring.health_endpoint)

            self.logger.info("Web application created successfully")
            return app

        except Exception as e:
            self.logger.error(f"Failed to create application: {e}", exc_info=True)
            raise

    async def _initialize_knowledge_agent(
        self,
        search_client: SearchClient,
        index_client: SearchIndexClient,
        blob_service_client: BlobServiceClient,
        artifacts_container_client,
        samples_container_client
        , token_credential=None,
        auth_mode: AuthMode = None
    ) -> Optional[KnowledgeAgentGrounding]:
        """Initialize knowledge agent with proper error handling."""
        if not self.config.knowledge_agent_name:
            self.logger.info("Knowledge agent name not configured, skipping initialization")
            return None

        try:
            ka_retrieval_client = KnowledgeAgentRetrievalClient(
                agent_name=self.config.knowledge_agent_name,
                endpoint=self.config.search_service.endpoint,
                credential=(
                    AzureKeyCredential(self.config.search_service.api_key)
                    if self.config.search_service.api_key
                    else (token_credential or DefaultAzureCredential())
                ),
            )

            data_model = DocumentPerChunkDataModel()
            knowledge_agent = KnowledgeAgentGrounding(
                ka_retrieval_client,
                search_client,
                index_client,
                data_model,
                self.config.search_service.index_name,
                self.config.knowledge_agent_name,
                self.config.azure_openai.endpoint,
                self.config.azure_openai.deployment,
                self.config.azure_openai.model_name,
                blob_service_client,
                samples_container_client,
                artifacts_container_client,
                auth_mode=auth_mode,
            )

            # Create the agent after object initialization to avoid event loop issues
            await knowledge_agent._ensure_retrieval_agent(
                self.config.knowledge_agent_name,
                self.config.azure_openai.endpoint,
                self.config.azure_openai.deployment,
                self.config.azure_openai.model_name,
            )

            self.logger.info("Knowledge agent initialized successfully")
            return knowledge_agent

        except Exception as e:
            self.logger.warning(f"Knowledge agent initialization failed: {e}")
            self.logger.info("Continuing without knowledge agent...")
            return None

    async def _create_search_index_if_not_exists(
        self, 
        index_client: SearchIndexClient, 
        index_name: str, 
        agent_name: Optional[str]
    ) -> None:
        """Create search index if it doesn't exist or update schema if needed."""
        await create_search_index_if_not_exists(index_client, index_name, agent_name)

    async def _setup_routes(
        self,
        app: web.Application,
        index_client: SearchIndexClient,
        citation_files_handler: CitationFilesHandler,
        admin_handler: AdminHandler,
        search_client: SearchClient,
        feedback_handler: FeedbackHandler
    ) -> None:
        """Setup application routes with proper error handling."""
        try:
            current_directory = Path(__file__).parent
            
            # Add main routes
            app.add_routes([
                web.get("/", lambda _: web.FileResponse(current_directory / "static/index.html")),
                web.get("/api/runtime-config", self._runtime_config_handler),
                web.get("/list_indexes", lambda _: self._list_indexes(index_client)),
                web.post("/delete_index", lambda request: self._delete_index(request, index_client)),
                web.post("/api/delete_index", lambda request: self._delete_index(request, index_client)),
                web.post("/get_citation_doc", citation_files_handler.handle),
                # Upload endpoints
                web.post("/upload", upload_handler.handle_upload),
                web.post("/extract_metadata", upload_handler.handle_extract_metadata),
                web.get("/get_document_types", upload_handler.handle_get_document_types),
                web.post("/process_document", upload_handler.handle_process_document),
                web.get("/upload_status", upload_handler.handle_status),
            ])
            
            # Attach admin routes
            admin_handler.attach_to_app(app)
            
            # Attach feedback routes
            feedback_handler.attach_to_app(app)
            
            # Add static file serving
            app.router.add_static("/", path=current_directory / "static", name="static")
            
            self.logger.info("Routes configured successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to setup routes: {e}", exc_info=True)
            raise

    async def _runtime_config_handler(self, request: web.Request) -> web.Response:
        """Return a small JSON blob with runtime flags for the current session.

        This endpoint is authoritative for the UI; it reads server-side env vars
        or (optionally) user/session identity to compute values like isAdmin.
        """
        try:
            # Log request for diagnostics
            try:
                self.logger.info("runtime-config requested", extra={"path": request.path, "remote": request.remote})
            except Exception:
                pass

            # Default to env var; replace with per-user logic if you have auth
            is_admin = os.environ.get('IS_ADMIN', 'false').lower() == 'true'
            headers = {
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            }
            return web.json_response({"isAdmin": bool(is_admin)}, headers=headers)
        except Exception as e:
            self.logger.warning(f"Failed to compute runtime config: {e}")
            return web.json_response({"isAdmin": False})

    async def _list_indexes(self, index_client: SearchIndexClient) -> web.Response:
        """List available search indexes."""
        try:
            indexes = []
            async for index in index_client.list_indexes():
                indexes.append({"name": index.name})
            
            return web.json_response([index["name"] for index in indexes])
            
        except Exception as e:
            self.logger.error(f"Failed to list indexes: {e}", exc_info=True)
            raise handle_azure_error(e, "Azure Search", "list_indexes")

    async def _delete_index(self, request: web.Request, index_client: SearchIndexClient) -> web.Response:
        """Delete a search index with optional knowledge agent cascade deletion."""
        try:
            # Parse request body safely
            try:
                body = await request.json()
            except Exception:
                body = {}

            index_name = body.get("index_name") or self.config.search_service.index_name
            cascade = body.get("cascade", True)
            agent_name = body.get("agent_name") or self.config.knowledge_agent_name

            if not index_name:
                raise ApplicationError("Missing index_name", status_code=400)

            async def try_delete_index():
                await index_client.delete_index(index_name)

            # Optionally delete the agent first
            if cascade and agent_name:
                try:
                    await index_client.delete_agent(agent_name)
                except Exception as e:
                    self.logger.warning(f"Failed to delete agent {agent_name}: {e}")

            try:
                await try_delete_index()
                return web.json_response({
                    "deleted": index_name, 
                    "agent_deleted": bool(cascade and agent_name)
                })
                
            except Exception as e:
                # If deletion failed due to agent reference and we haven't tried cascading yet
                msg = str(e)
                needs_agent_delete = "Cannot delete index" in msg and "referencing" in msg
                
                if needs_agent_delete and not (cascade and agent_name):
                    if agent_name:
                        try:
                            await index_client.delete_agent(agent_name)
                            await try_delete_index()
                            return web.json_response({
                                "deleted": index_name, 
                                "agent_deleted": True
                            })
                        except Exception as inner:
                            raise handle_azure_error(inner, "Azure Search", "delete_index")
                    else:
                        raise ApplicationError(
                            f"{msg}; provide agent_name or set cascade true",
                            status_code=409
                        )
                
                raise handle_azure_error(e, "Azure Search", "delete_index")

        except ApplicationError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to delete index: {e}", exc_info=True)
            raise handle_azure_error(e, "Azure Search", "delete_index")


async def create_search_index_if_not_exists(index_client: SearchIndexClient, index_name: str, agent_name: str | None):
    """Ensure the search index exists with the expected schema; recreate if mismatched."""
    # Schema aligned with data_model.py and indexer_img_verbalize_strategy.py
    fields = [
        SearchableField(name="content_id", type=SearchFieldDataType.String, key=True, analyzer_name="keyword"),
        SimpleField(name="text_document_id", type=SearchFieldDataType.String, searchable=False, filterable=True, hidden=False, sortable=False, facetable=False),
        SimpleField(name="image_document_id", type=SearchFieldDataType.String, searchable=False, filterable=True, hidden=False, sortable=False, facetable=False),
        SearchableField(name="document_title", type=SearchFieldDataType.String, searchable=True, filterable=True, hidden=False, sortable=True, facetable=True),
        SearchableField(name="content_text", type=SearchFieldDataType.String, searchable=True, filterable=True, hidden=False, sortable=True, facetable=True),
        SearchField(name="content_embedding", type=SearchFieldDataType.Collection(SearchFieldDataType.Single), vector_search_dimensions=1536, searchable=True, vector_search_profile_name="hnsw"),
        SimpleField(name="content_path", type=SearchFieldDataType.String, searchable=False, filterable=True, hidden=False, sortable=False, facetable=False),
        # Field to link text content to source figures/images
        SimpleField(name="source_figure_id", type=SearchFieldDataType.String, searchable=False, filterable=True, hidden=False, sortable=False, facetable=False),
        SimpleField(name="related_image_path", type=SearchFieldDataType.String, searchable=False, filterable=True, hidden=False, sortable=False, facetable=False),
        # New metadata fields
        SimpleField(name="published_date", type=SearchFieldDataType.DateTimeOffset, searchable=False, filterable=True, sortable=True, facetable=True),
        SimpleField(name="expiry_date", type=SearchFieldDataType.DateTimeOffset, searchable=False, filterable=True, sortable=True, facetable=True),
        SearchableField(name="document_type", type=SearchFieldDataType.String, searchable=True, filterable=True, sortable=True, facetable=True),
        ComplexField(name="locationMetadata", fields=[
            SimpleField(name="pageNumber", type=SearchFieldDataType.Int32, searchable=False, filterable=True, hidden=False, sortable=True, facetable=True),
            SimpleField(name="boundingPolygons", type=SearchFieldDataType.String, searchable=False, hidden=False, filterable=False, sortable=False, facetable=False)
        ])
    ]

    vector_search = VectorSearch(
        profiles=[
            VectorSearchProfile(name="hnsw", algorithm_configuration_name="hnsw-config", vectorizer_name="openai-vectorizer")
        ],
        algorithms=[
            HnswAlgorithmConfiguration(
                name="hnsw-config",
                kind=VectorSearchAlgorithmKind.HNSW,
                parameters={"m": 4, "efConstruction": 400, "efSearch": 500, "metric": "cosine"}
            )
        ],
        vectorizers=[
            AzureOpenAIVectorizer(
                vectorizer_name="openai-vectorizer",
                parameters=AzureOpenAIVectorizerParameters(
                    resource_url=os.environ.get("AZURE_OPENAI_ENDPOINT"),
                    deployment_name=os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT"),
                    model_name=os.environ.get("AZURE_OPENAI_EMBEDDING_MODEL_NAME", "text-embedding-ada-002"),
                    api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
                )
            )
        ]
    )

    semantic_search = SemanticSearch(
        default_configuration_name="semantic-config",
        configurations=[
            SemanticConfiguration(
                name="semantic-config",
                prioritized_fields=SemanticPrioritizedFields(
                    content_fields=[SemanticField(field_name="content_text")],
                    keywords_fields=[SemanticField(field_name="document_title")]
                )
            )
        ]
    )

    # Create scoring profiles for better search relevance
    scoring_profiles = [
        # Profile 1: Boost recent documents (freshness only, no tag parameters)
        ScoringProfile(
            name="freshness_and_type_boost",
            text_weights=TextWeights(weights={
                "document_title": 3.0,  # Boost title matches
                "content_text": 1.0,   # Standard content weight
                "document_type": 2.0   # Boost document type matches
            }),
            functions=[
                # Boost newer documents (documents published in last 365 days get boost)
                FreshnessScoringFunction(
                    field_name="published_date",
                    boost=2.0,
                    parameters=FreshnessScoringParameters(
                        boosting_duration="P365D"  # ISO 8601 duration: 365 days
                    ),
                    interpolation="linear"
                )
            ],
            function_aggregation="sum"
        ),
        # Profile 2: Focus on content relevance with moderate recency bias
        ScoringProfile(
            name="content_relevance_boost",
            text_weights=TextWeights(weights={
                "document_title": 4.0,  # Higher title boost for content relevance
                "content_text": 2.0,   # Higher content weight
                "document_type": 1.0   # Lower document type weight
            }),
            functions=[
                # Moderate boost for recent documents
                FreshnessScoringFunction(
                    field_name="published_date",
                    boost=1.3,
                    parameters=FreshnessScoringParameters(
                        boosting_duration="P180D"  # 180 days
                    ),
                    interpolation="linear"
                )
            ],
            function_aggregation="sum"
        )
    ]

    desired = SearchIndex(
        name=index_name, 
        fields=fields, 
        vector_search=vector_search, 
        semantic_search=semantic_search,
        scoring_profiles=scoring_profiles,
        default_scoring_profile="freshness_and_type_boost"  # Set default scoring profile
    )

    try:
        existing = await index_client.get_index(index_name)
        existing_fields = {f.name for f in (existing.fields or [])}
        desired_fields = {f.name for f in (desired.fields or [])}
        if not desired_fields.issubset(existing_fields):
            # Remove referencing agent first (best-effort), then recreate index
            if agent_name:
                try:
                    await index_client.delete_agent(agent_name)
                except Exception:
                    pass
            try:
                await index_client.delete_index(index_name)
            except Exception:
                pass
            await index_client.create_index(desired)
            print(f"Index '{index_name}' recreated with expected schema")
        else:
            await index_client.create_or_update_index(desired)
            print(f"Index '{index_name}' updated with expected schema")
    except Exception as e:
        if "ResourceNameAlreadyInUse" in str(e) or "CannotCreateExistingIndex" in str(e):
            print(f"Index '{index_name}' already exists, skipping creation")
        else:
            # Not found or fetch failed; create fresh
            try:
                await index_client.create_index(desired)
                print(f"Index '{index_name}' created with expected schema")
            except Exception as create_error:
                print(f"Failed to create index: {create_error}")
                raise



async def create_search_index_if_not_exists(index_client: SearchIndexClient, index_name: str, agent_name: str | None):
    """Ensure the search index exists with the expected schema; recreate if mismatched."""
    # Schema aligned with data_model.py and indexer_img_verbalize_strategy.py
    fields = [
        SearchableField(name="content_id", type=SearchFieldDataType.String, key=True, analyzer_name="keyword"),
        SimpleField(name="text_document_id", type=SearchFieldDataType.String, searchable=False, filterable=True, hidden=False, sortable=False, facetable=False),
        SimpleField(name="image_document_id", type=SearchFieldDataType.String, searchable=False, filterable=True, hidden=False, sortable=False, facetable=False),
        SearchableField(name="document_title", type=SearchFieldDataType.String, searchable=True, filterable=True, hidden=False, sortable=True, facetable=True),
        SearchableField(name="content_text", type=SearchFieldDataType.String, searchable=True, filterable=True, hidden=False, sortable=True, facetable=True),
        SearchField(name="content_embedding", type=SearchFieldDataType.Collection(SearchFieldDataType.Single), vector_search_dimensions=1536, searchable=True, vector_search_profile_name="hnsw"),
        SimpleField(name="content_path", type=SearchFieldDataType.String, searchable=False, filterable=True, hidden=False, sortable=False, facetable=False),
        # Field to link text content to source figures/images
        SimpleField(name="source_figure_id", type=SearchFieldDataType.String, searchable=False, filterable=True, hidden=False, sortable=False, facetable=False),
        SimpleField(name="related_image_path", type=SearchFieldDataType.String, searchable=False, filterable=True, hidden=False, sortable=False, facetable=False),
        # New metadata fields
        SimpleField(name="published_date", type=SearchFieldDataType.DateTimeOffset, searchable=False, filterable=True, sortable=True, facetable=True),
        SimpleField(name="expiry_date", type=SearchFieldDataType.DateTimeOffset, searchable=False, filterable=True, sortable=True, facetable=True),
        SearchableField(name="document_type", type=SearchFieldDataType.String, searchable=True, filterable=True, sortable=True, facetable=True),
        ComplexField(name="locationMetadata", fields=[
            SimpleField(name="pageNumber", type=SearchFieldDataType.Int32, searchable=False, filterable=True, hidden=False, sortable=True, facetable=True),
            SimpleField(name="boundingPolygons", type=SearchFieldDataType.String, searchable=False, hidden=False, filterable=False, sortable=False, facetable=False)
        ])
    ]

    # Get configuration for vectorizer
    config = get_config()
    
    vector_search = VectorSearch(
        profiles=[
            VectorSearchProfile(name="hnsw", algorithm_configuration_name="hnsw-config", vectorizer_name="openai-vectorizer")
        ],
        algorithms=[
            HnswAlgorithmConfiguration(
                name="hnsw-config",
                kind=VectorSearchAlgorithmKind.HNSW,
                parameters={"m": 4, "efConstruction": 400, "efSearch": 500, "metric": "cosine"}
            )
        ],
        vectorizers=[
            AzureOpenAIVectorizer(
                vectorizer_name="openai-vectorizer",
                parameters=AzureOpenAIVectorizerParameters(
                    resource_url=config.azure_openai.endpoint,
                    deployment_name=config.azure_openai.embedding_deployment,
                    model_name=config.azure_openai.embedding_model_name,
                    api_key=config.azure_openai.api_key,
                )
            )
        ]
    )

    semantic_search = SemanticSearch(
        default_configuration_name="semantic-config",
        configurations=[
            SemanticConfiguration(
                name="semantic-config",
                prioritized_fields=SemanticPrioritizedFields(
                    content_fields=[SemanticField(field_name="content_text")],
                    keywords_fields=[SemanticField(field_name="document_title")]
                )
            )
        ]
    )

    # Create scoring profiles for better search relevance
    scoring_profiles = [
        # Profile 1: Boost recent documents (freshness only, no tag parameters)
        ScoringProfile(
            name="freshness_and_type_boost",
            text_weights=TextWeights(weights={
                "document_title": 3.0,  # Boost title matches
                "content_text": 1.0,   # Standard content weight
                "document_type": 2.0   # Boost document type matches
            }),
            functions=[
                # Boost newer documents (documents published in last 365 days get boost)
                FreshnessScoringFunction(
                    field_name="published_date",
                    boost=2.0,
                    parameters=FreshnessScoringParameters(
                        boosting_duration="P365D"  # ISO 8601 duration: 365 days
                    ),
                    interpolation="linear"
                )
            ],
            function_aggregation="sum"
        ),
        # Profile 2: Focus on content relevance with moderate recency bias
        ScoringProfile(
            name="content_relevance_boost",
            text_weights=TextWeights(weights={
                "document_title": 4.0,  # Higher title boost for content relevance
                "content_text": 2.0,   # Higher content weight
                "document_type": 1.0   # Lower document type weight
            }),
            functions=[
                # Moderate boost for recent documents
                FreshnessScoringFunction(
                    field_name="published_date",
                    boost=1.3,
                    parameters=FreshnessScoringParameters(
                        boosting_duration="P180D"  # 180 days
                    ),
                    interpolation="linear"
                )
            ],
            function_aggregation="sum"
        )
    ]

    desired = SearchIndex(
        name=index_name, 
        fields=fields, 
        vector_search=vector_search, 
        semantic_search=semantic_search,
        scoring_profiles=scoring_profiles,
        default_scoring_profile="freshness_and_type_boost"  # Set default scoring profile
    )

    logger = StructuredLogger("search_index")
    
    try:
        existing = await index_client.get_index(index_name)
        existing_fields = {f.name for f in (existing.fields or [])}
        desired_fields = {f.name for f in (desired.fields or [])}
        if not desired_fields.issubset(existing_fields):
            # Remove referencing agent first (best-effort), then recreate index
            if agent_name:
                try:
                    await index_client.delete_agent(agent_name)
                except Exception:
                    pass
            try:
                await index_client.delete_index(index_name)
            except Exception:
                pass
            await index_client.create_index(desired)
            logger.info(f"Index '{index_name}' recreated with expected schema")
        else:
            await index_client.create_or_update_index(desired)
            logger.info(f"Index '{index_name}' updated with expected schema")
    except Exception as e:
        if "ResourceNameAlreadyInUse" in str(e) or "CannotCreateExistingIndex" in str(e):
            logger.info(f"Index '{index_name}' already exists, skipping creation")
        else:
            # Not found or fetch failed; create fresh
            try:
                await index_client.create_index(desired)
                logger.info(f"Index '{index_name}' created with expected schema")
            except Exception as create_error:
                logger.error(f"Failed to create index: {create_error}")
                raise


async def create_app() -> web.Application:
    """Create the application with production-ready configuration."""
    # Initialize configuration
    config = get_config()
    
    # Setup logging
    setup_logging(config.logging)
    
    # Create production app wrapper
    prod_app = ProductionApp(config)
    
    # Create the web application
    app = await prod_app.create_application()
    
    return app


if __name__ == "__main__":
    try:
        # Get configuration and setup logging
        config = get_config()
        setup_logging(config.logging)
        
        # Create application
        async def create_app_instance():
            return await create_app()
        
        # Create event loop and run app - Windows-specific handling
        if sys.platform == 'win32':
            # For Windows, use SelectorEventLoop to avoid aiodns issues
            try:
                loop = asyncio.SelectorEventLoop()
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            except AttributeError:
                # Fallback for older Python versions
                loop = asyncio.new_event_loop()
        else:
            loop = asyncio.new_event_loop()
            
        asyncio.set_event_loop(loop)
        
        # Initialize logger early for better error handling
        logger = StructuredLogger("main")
        
        try:
            app = loop.run_until_complete(create_app_instance())

            # Create and run application on the same event loop to avoid cross-loop
            # credential creation issues. Using AppRunner/TCPSite prevents
            # web.run_app from creating or switching to a different loop.
            logger.info(
                f"Starting server on {config.server.host}:{config.server.port}",
                host=config.server.host,
                port=config.server.port,
                environment=config.environment
            )

            runner = web.AppRunner(app)
            loop.run_until_complete(runner.setup())
            site = web.TCPSite(runner, host=config.server.host, port=config.server.port)
            loop.run_until_complete(site.start())

            try:
                loop.run_forever()
            finally:
                # Clean up the runner explicitly on shutdown
                loop.run_until_complete(runner.cleanup())
        except KeyboardInterrupt:
            logger.info("Application stopped by user")
        except Exception as e:
            logger.error(f"Application startup failed: {e}")
            raise
        finally:
            try:
                # Cancel all running tasks
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                
                # Wait for tasks to complete cancellation
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception as cleanup_error:
                logger.warning(f"Error during cleanup: {cleanup_error}")
            finally:
                loop.close()
            
    except Exception as e:
        # Use basic logging if structured logging fails
        import logging
        logging.error(f"Failed to start application: {e}", exc_info=True)
        raise
