import logging
import os
import asyncio
import sys
from pathlib import Path
from dotenv import load_dotenv
from aiohttp import web
from rich.logging import RichHandler

# Fix for Windows event loop issue with aiodns
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from openai import AsyncAzureOpenAI
from azure.identity.aio import (
    DefaultAzureCredential,
    get_bearer_token_provider,
)
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.aio import SearchClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    VectorSearch,
    VectorSearchProfile,
    VectorSearchAlgorithmConfiguration,
    HnswAlgorithmConfiguration,
    VectorSearchAlgorithmKind,
    SemanticConfiguration,
    SemanticPrioritizedFields,
    SemanticField,
    SemanticSearch,
    SimpleField,
    SearchableField,
    ComplexField,
    AzureOpenAIVectorizer,
    AzureOpenAIVectorizerParameters,
    ScoringProfile,
    ScoringFunction,
    FreshnessScoringFunction,
    FreshnessScoringParameters,
    TagScoringFunction,
    TagScoringParameters,
    TextWeights,
)
from azure.search.documents.indexes.aio import SearchIndexClient
from azure.search.documents.agent.aio import KnowledgeAgentRetrievalClient
from azure.core.pipeline.policies import UserAgentPolicy

from azure.storage.blob.aio import BlobServiceClient
from admin.admin_handler import AdminHandler

from retrieval.search_grounding import SearchGroundingRetriever
from retrieval.knowledge_agent import KnowledgeAgentGrounding
from constants import USER_AGENT
from retrieval.multimodal_rag import MultimodalRag
from core.data_model import DocumentPerChunkDataModel
from handlers.citation_file_handler import CitationFilesHandler
from handlers.upload_handler import upload_handler

# Load environment variables from .env file
load_dotenv(dotenv_path=Path(__file__).parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)],
)

# Simple CORS middleware
@web.middleware
async def cors_middleware(request, handler):
    if request.method == "OPTIONS":
        # Handle preflight requests
        response = web.Response()
    else:
        response = await handler(request)
    
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response

async def list_indexes(index_client: SearchIndexClient):
    indexes = []
    async for index in index_client.list_indexes():
        indexes.append({"name": index.name})
    return web.json_response([index["name"] for index in indexes])

async def delete_index(request, index_client: SearchIndexClient):
    # Deletes the knowledge agent (if requested) before deleting the index to avoid OperationNotAllowed
    try:
        body = await request.json()
    except Exception:
        body = {}

    index_name = body.get("index_name") or os.environ.get("SEARCH_INDEX_NAME")
    cascade = body.get("cascade", True)
    agent_name = body.get("agent_name") or os.environ.get("KNOWLEDGE_AGENT_NAME")

    if not index_name:
        return web.json_response({"error": "Missing index_name"}, status=400)

    async def try_delete_index():
        await index_client.delete_index(index_name)

    # Optionally delete the agent first
    if cascade and agent_name:
        try:
            await index_client.delete_agent(agent_name)
        except Exception as e:
            # Ignore not found; propagate other issues only when index deletion also fails
            pass

    try:
        await try_delete_index()
        return web.json_response({"deleted": index_name, "agent_deleted": bool(cascade and agent_name)})
    except Exception as e:
        # If deletion failed due to agent reference and we haven't tried cascading yet, try now
        msg = str(e)
        needs_agent_delete = "Cannot delete index" in msg and "referencing" in msg
        if needs_agent_delete and not (cascade and agent_name):
            if agent_name:
                try:
                    await index_client.delete_agent(agent_name)
                    await try_delete_index()
                    return web.json_response({"deleted": index_name, "agent_deleted": True})
                except Exception as inner:
                    return web.json_response({"error": str(inner)}, status=500)
            else:
                return web.json_response({"error": msg + "; provide agent_name or set cascade true"}, status=409)
        return web.json_response({"error": msg}, status=500)


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


async def create_app():
    tokenCredential = DefaultAzureCredential()
    tokenProvider = get_bearer_token_provider(
        tokenCredential,
        "https://cognitiveservices.azure.com/.default",
    )

    chatcompletions_model_name = os.environ["AZURE_OPENAI_DEPLOYMENT"]
    openai_endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
    search_endpoint = os.environ["SEARCH_SERVICE_ENDPOINT"]
    search_index_name = os.environ["SEARCH_INDEX_NAME"]
    knowledge_agent_name = os.environ["KNOWLEDGE_AGENT_NAME"]
    openai_deployment_name = os.environ["AZURE_OPENAI_DEPLOYMENT"]
    openai_model_name = os.environ["AZURE_OPENAI_MODEL_NAME"]

    # Use API key for search service if available, otherwise fall back to token credential
    search_api_key = os.environ.get("SEARCH_API_KEY")
    if search_api_key:
        search_credential = AzureKeyCredential(search_api_key)
    else:
        search_credential = tokenCredential

    search_client = SearchClient(
        endpoint=search_endpoint,
        index_name=search_index_name,
        credential=search_credential,
        user_agent_policy=UserAgentPolicy(base_user_agent=USER_AGENT),
    )
    data_model = DocumentPerChunkDataModel()

    index_client = SearchIndexClient(
        endpoint=search_endpoint,
        credential=search_credential,
        user_agent_policy=UserAgentPolicy(base_user_agent=USER_AGENT),
    )

    # Create or align the search index schema before agent creation
    await create_search_index_if_not_exists(index_client, search_index_name, os.environ.get("KNOWLEDGE_AGENT_NAME"))

    # Initialize blob service clients needed for image citation URLs
    blob_service_client = BlobServiceClient(
        account_url=os.environ["ARTIFACTS_STORAGE_ACCOUNT_URL"],
        credential=tokenCredential,
    )
    artifacts_container_client = blob_service_client.get_container_client(
        os.environ["ARTIFACTS_STORAGE_CONTAINER"]
    )
    samples_container_client = blob_service_client.get_container_client(
        os.environ["SAMPLES_STORAGE_CONTAINER"]
    )

    try:
        ka_retrieval_client = KnowledgeAgentRetrievalClient(
            agent_name=knowledge_agent_name,
            endpoint=search_endpoint,
            credential=search_credential,
        )

        knowledge_agent = KnowledgeAgentGrounding(
            ka_retrieval_client,
            search_client,
            index_client,
            data_model,
            search_index_name,
            knowledge_agent_name,
            openai_endpoint,
            openai_deployment_name,
            openai_model_name,
            blob_service_client,
            samples_container_client,
            artifacts_container_client,  # Pass artifacts container for image access
        )
    except Exception as e:
        print(f"Warning: Knowledge agent initialization failed: {e}")
        print("Continuing without knowledge agent...")
        knowledge_agent = None

    # Use API key for OpenAI if available, otherwise fall back to token provider
    openai_api_key = os.environ.get("AZURE_OPENAI_API_KEY")
    if openai_api_key:
        openai_client = AsyncAzureOpenAI(
            api_key=openai_api_key,
            api_version="2024-08-01-preview",
            azure_endpoint=openai_endpoint,
            timeout=30,
        )
    else:
        openai_client = AsyncAzureOpenAI(
            azure_ad_token_provider=tokenProvider,
            api_version="2024-08-01-preview",
            azure_endpoint=openai_endpoint,
            timeout=30,
        )

    search_grounding = SearchGroundingRetriever(
        search_client,
        openai_client,
        data_model,
        openai_deployment_name,
        blob_service_client,
        samples_container_client,
        artifacts_container_client,
    )

    app = web.Application(middlewares=[cors_middleware])

    # Always initialize multimodal RAG, but use search grounding if knowledge agent failed
    mmrag = MultimodalRag(
        knowledge_agent,  # This might be None
        search_grounding,
        openai_client,
        chatcompletions_model_name,
        artifacts_container_client,
    )
    mmrag.attach_to_app(app, "/chat")
    
    if knowledge_agent is None:
        print("Note: Using search grounding instead of knowledge agent due to initialization failure")

    citation_files_handler = CitationFilesHandler(
        blob_service_client, samples_container_client, artifacts_container_client
    )

    # Initialize admin handler
    admin_handler = AdminHandler()

    current_directory = Path(__file__).parent
    app.add_routes(
        [
            web.get(
                "/", lambda _: web.FileResponse(current_directory / "static/index.html")
            ),
            web.get("/list_indexes", lambda _: list_indexes(index_client)),
            web.post("/delete_index", lambda request: delete_index(request, index_client)),
            web.post("/api/delete_index", lambda request: delete_index(request, index_client)),
            web.post("/get_citation_doc", citation_files_handler.handle),
            # Upload endpoints
            web.post("/upload", upload_handler.handle_upload),
            web.post("/process_document", upload_handler.handle_process_document),
            web.get("/upload_status", upload_handler.handle_status),
        ]
    )
    
    # Attach admin routes
    admin_handler.attach_to_app(app, search_client)
    app.router.add_static("/", path=current_directory / "static", name="static")

    return app


if __name__ == "__main__":
    host = os.environ.get("HOST", "localhost")
    port = int(os.environ.get("PORT", 5000))
    web.run_app(create_app(), host=host, port=port)
