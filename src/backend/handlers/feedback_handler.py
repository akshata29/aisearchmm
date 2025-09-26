"""
Feedback handler for capturing and managing user feedback on AI responses.
Handles feedback storage, retrieval, and management for the multimodal AI search system.
"""

import json
import time
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from aiohttp import web
from azure.search.documents.aio import SearchClient
from azure.search.documents.indexes.aio import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex, SearchField, SearchFieldDataType, VectorSearch, VectorSearchProfile,
    VectorSearchAlgorithmConfiguration, HnswAlgorithmConfiguration, VectorSearchAlgorithmKind,
    SimpleField, SearchableField, ComplexField, AzureOpenAIVectorizer,
    AzureOpenAIVectorizerParameters
)
from azure.search.documents.models import IndexAction, VectorizedQuery
from azure.core.exceptions import AzureError, ResourceNotFoundError
from openai import AsyncAzureOpenAI

from utils.logging_config import StructuredLogger
from core.exceptions import ApplicationError, ValidationError
from core.config import get_config

logger = StructuredLogger(__name__)


@dataclass
class CitationData:
    """Citation information for feedback storage."""
    doc_id: str
    content_id: str
    title: str
    text: Optional[str] = None
    page_number: Optional[int] = None
    bounding_polygons: Optional[str] = None
    content_type: Optional[str] = None
    is_image: bool = False
    image_url: Optional[str] = None
    linked_image_path: Optional[str] = None
    source_figure_id: Optional[str] = None


@dataclass
class ProcessingStepData:
    """Processing step information for feedback storage."""
    step_id: str
    step_type: str
    title: str
    description: Optional[str] = None
    status: str = "completed"
    duration_ms: Optional[int] = None
    details: Optional[Dict[str, Any]] = None


@dataclass
class FeedbackEntry:
    """Complete feedback entry with all context information."""
    # Core identifiers
    feedback_id: str
    request_id: str
    session_id: str
    timestamp: str
    
    # User interaction
    feedback_type: str  # "thumbs_up" or "thumbs_down"
    
    # Question and response data
    question: str
    question_vector: List[float]  # Embedded question for similarity search
    response_text: str
    
    # Citations
    text_citations: List[CitationData]
    image_citations: List[CitationData]
    
    # Processing context
    processing_steps: List[ProcessingStepData]
    
    # Configuration used
    search_config: Dict[str, Any]
    
    # Metadata
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None
    
    # Admin fields (for editing)
    admin_notes: Optional[str] = None
    is_reviewed: bool = False
    last_modified: Optional[str] = None
    modified_by: Optional[str] = None
    
    def to_search_document(self) -> Dict[str, Any]:
        """Convert to Azure Search document format."""
        return {
            "id": self.feedback_id,
            "request_id": self.request_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "feedback_type": self.feedback_type,
            "question": self.question,
            "question_vector": self.question_vector,
            "response_text": self.response_text,
            "text_citations": [asdict(citation) for citation in self.text_citations],
            "image_citations": [asdict(citation) for citation in self.image_citations],
            "processing_steps": [
                {
                    **asdict(step),
                    "details": json.dumps(step.details) if step.details else "{}"
                } for step in self.processing_steps
            ],
            "search_config": json.dumps(self.search_config) if self.search_config else "{}",
            "user_agent": self.user_agent,
            "ip_address": self.ip_address,
            "admin_notes": self.admin_notes,
            "is_reviewed": self.is_reviewed,
            "last_modified": self.last_modified or self.timestamp,
            "modified_by": self.modified_by,
            # Searchable text for admin queries
            "searchable_content": f"{self.question} {self.response_text} {self.admin_notes or ''}",
            # Citation count for statistics
            "text_citations_count": len(self.text_citations),
            "image_citations_count": len(self.image_citations)
        }
    
    @classmethod
    def from_search_document(cls, doc: Dict[str, Any]) -> "FeedbackEntry":
        """Create from Azure Search document."""
        return cls(
            feedback_id=doc["id"],
            request_id=doc["request_id"],
            session_id=doc["session_id"],
            timestamp=doc["timestamp"],
            feedback_type=doc["feedback_type"],
            question=doc["question"],
            question_vector=doc.get("question_vector", []),
            response_text=doc["response_text"],
            text_citations=[CitationData(**c) for c in doc.get("text_citations", [])],
            image_citations=[CitationData(**c) for c in doc.get("image_citations", [])],
            processing_steps=[
                ProcessingStepData(
                    **{
                        **s,
                        "details": json.loads(s["details"]) if s.get("details") else {}
                    }
                ) for s in doc.get("processing_steps", [])
            ],
            search_config=json.loads(doc["search_config"]) if doc.get("search_config") else {},
            user_agent=doc.get("user_agent"),
            ip_address=doc.get("ip_address"),
            admin_notes=doc.get("admin_notes"),
            is_reviewed=doc.get("is_reviewed", False),
            last_modified=doc.get("last_modified"),
            modified_by=doc.get("modified_by")
        )


class FeedbackHandler:
    """
    Handler for managing user feedback on AI responses.
    Provides comprehensive feedback capture, storage, and management capabilities.
    """

    FEEDBACK_INDEX_NAME = "mmcache"
    
    def __init__(
        self, 
        search_index_client: SearchIndexClient,
        openai_client: AsyncAzureOpenAI,
        embedding_deployment: str
    ):
        self.search_index_client = search_index_client
        self.openai_client = openai_client
        self.embedding_deployment = embedding_deployment
        self._search_client_cache: Dict[str, SearchClient] = {}
        
    async def initialize_feedback_index(self) -> None:
        """Initialize the feedback index with proper schema."""
        logger.info("Initializing feedback index", extra={"index_name": self.FEEDBACK_INDEX_NAME})
        
        try:
            # Check if index exists
            try:
                existing_index = await self.search_index_client.get_index(self.FEEDBACK_INDEX_NAME)
                logger.info("Feedback index already exists", extra={"index_name": self.FEEDBACK_INDEX_NAME})
                # For development, delete and recreate to ensure schema is up to date
                # TODO: In production, implement proper schema migration
                # logger.info("Deleting existing feedback index for schema update", extra={"index_name": self.FEEDBACK_INDEX_NAME})
                # await self.search_index_client.delete_index(self.FEEDBACK_INDEX_NAME)
                return  # Index exists, no need to create
            except Exception:
                # Index doesn't exist, create it
                logger.info("Feedback index does not exist, creating new index", extra={"index_name": self.FEEDBACK_INDEX_NAME})
            
            config = get_config()
            
            # Define vector search configuration
            vector_search = VectorSearch(
                profiles=[
                    VectorSearchProfile(
                        name="question-vector-profile", 
                        algorithm_configuration_name="hnsw-config", 
                        vectorizer_name="openai-vectorizer"
                    )
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
            
            # Define fields
            fields = [
                SimpleField(name="id", type=SearchFieldDataType.String, key=True),
                SimpleField(name="request_id", type=SearchFieldDataType.String, filterable=True),
                SimpleField(name="session_id", type=SearchFieldDataType.String, filterable=True),
                SimpleField(name="timestamp", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True),
                SimpleField(name="feedback_type", type=SearchFieldDataType.String, filterable=True),
                SearchableField(name="question", type=SearchFieldDataType.String, analyzer_name="standard.lucene"),
                SearchField(
                    name="question_vector", 
                    type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                    vector_search_profile_name="question-vector-profile",
                    vector_search_dimensions=1536
                ),
                SearchableField(name="response_text", type=SearchFieldDataType.String, analyzer_name="standard.lucene"),
                ComplexField(name="text_citations", type=SearchFieldDataType.ComplexType, collection=True, fields=[
                    SimpleField(name="doc_id", type=SearchFieldDataType.String),
                    SimpleField(name="content_id", type=SearchFieldDataType.String),
                    SearchableField(name="title", type=SearchFieldDataType.String),
                    SearchableField(name="text", type=SearchFieldDataType.String),
                    SimpleField(name="page_number", type=SearchFieldDataType.Int32),
                    SimpleField(name="bounding_polygons", type=SearchFieldDataType.String),
                    SimpleField(name="content_type", type=SearchFieldDataType.String),
                    SimpleField(name="is_image", type=SearchFieldDataType.Boolean),
                    SimpleField(name="image_url", type=SearchFieldDataType.String),
                    SimpleField(name="linked_image_path", type=SearchFieldDataType.String),
                    SimpleField(name="source_figure_id", type=SearchFieldDataType.String),
                ]),
                ComplexField(name="image_citations", type=SearchFieldDataType.ComplexType, collection=True, fields=[
                    SimpleField(name="doc_id", type=SearchFieldDataType.String),
                    SimpleField(name="content_id", type=SearchFieldDataType.String),
                    SearchableField(name="title", type=SearchFieldDataType.String),
                    SearchableField(name="text", type=SearchFieldDataType.String),
                    SimpleField(name="page_number", type=SearchFieldDataType.Int32),
                    SimpleField(name="bounding_polygons", type=SearchFieldDataType.String),
                    SimpleField(name="content_type", type=SearchFieldDataType.String),
                    SimpleField(name="is_image", type=SearchFieldDataType.Boolean),
                    SimpleField(name="image_url", type=SearchFieldDataType.String),
                    SimpleField(name="linked_image_path", type=SearchFieldDataType.String),
                    SimpleField(name="source_figure_id", type=SearchFieldDataType.String),
                ]),
                ComplexField(name="processing_steps", type=SearchFieldDataType.ComplexType, collection=True, fields=[
                    SimpleField(name="step_id", type=SearchFieldDataType.String),
                    SimpleField(name="step_type", type=SearchFieldDataType.String),
                    SearchableField(name="title", type=SearchFieldDataType.String),
                    SearchableField(name="description", type=SearchFieldDataType.String),
                    SimpleField(name="status", type=SearchFieldDataType.String),
                    SimpleField(name="duration_ms", type=SearchFieldDataType.Int32),
                    SimpleField(name="details", type=SearchFieldDataType.String),  # JSON string
                ]),
                SimpleField(name="search_config", type=SearchFieldDataType.String),  # JSON string
                SimpleField(name="user_agent", type=SearchFieldDataType.String),
                SimpleField(name="ip_address", type=SearchFieldDataType.String),
                SearchableField(name="admin_notes", type=SearchFieldDataType.String, analyzer_name="standard.lucene"),
                SimpleField(name="is_reviewed", type=SearchFieldDataType.Boolean, filterable=True),
                SimpleField(name="last_modified", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True),
                SimpleField(name="modified_by", type=SearchFieldDataType.String, filterable=True),
                SearchableField(name="searchable_content", type=SearchFieldDataType.String, analyzer_name="standard.lucene"),
                SimpleField(name="text_citations_count", type=SearchFieldDataType.Int32, filterable=True),
                SimpleField(name="image_citations_count", type=SearchFieldDataType.Int32, filterable=True),
            ]
            
            # Create index
            index = SearchIndex(
                name=self.FEEDBACK_INDEX_NAME,
                fields=fields,
                vector_search=vector_search
            )
            
            await self.search_index_client.create_index(index)
            logger.info("Feedback index created successfully", extra={"index_name": self.FEEDBACK_INDEX_NAME})
            
        except Exception as e:
            logger.error("Failed to initialize feedback index", extra={
                "index_name": self.FEEDBACK_INDEX_NAME,
                "error": str(e)
            }, exc_info=True)
            raise ApplicationError(f"Failed to initialize feedback index: {str(e)}")
    
    def _get_search_client(self, request: web.Request = None) -> SearchClient:
        """Get search client for feedback index using session bundle or fallback."""
        # Try to get from session bundle first (handles both Managed Identity and API key)
        if request:
            bundle = request.get("session_bundle")
            if bundle is not None:
                return bundle.get_search_client(self.FEEDBACK_INDEX_NAME)
        
        # Fallback to cached client if session bundle is not available
        if self.FEEDBACK_INDEX_NAME not in self._search_client_cache:
            config = get_config()
            from azure.core.credentials import AzureKeyCredential
            
            credential = AzureKeyCredential(config.search_service.api_key) if config.search_service.api_key else None
            
            self._search_client_cache[self.FEEDBACK_INDEX_NAME] = SearchClient(
                endpoint=config.search_service.endpoint,
                index_name=self.FEEDBACK_INDEX_NAME,
                credential=credential
            )
        
        return self._search_client_cache[self.FEEDBACK_INDEX_NAME]
    
    async def _embed_question(self, question: str) -> List[float]:
        """Generate embeddings for a question."""
        try:
            response = await self.openai_client.embeddings.create(
                model=self.embedding_deployment,
                input=question
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error("Failed to generate question embedding", extra={
                "question": question,
                "error": str(e)
            }, exc_info=True)
            raise ApplicationError(f"Failed to generate question embedding: {str(e)}")
    
    async def submit_feedback(self, request: web.Request) -> web.Response:
        """Handle feedback submission from frontend."""
        request_start = time.time()
        operation_id = f"feedback_submit_{int(time.time())}"
        
        try:
            # Parse request data
            try:
                data = await request.json()
            except Exception as e:
                logger.warning("Invalid JSON in feedback submission", extra={
                    "operation_id": operation_id,
                    "error": str(e)
                })
                raise ValidationError("Invalid JSON in request body")
            
            # Validate required fields
            required_fields = ["request_id", "feedback_type", "question", "response", "session_id"]
            missing_fields = [field for field in required_fields if not data.get(field)]
            if missing_fields:
                raise ValidationError(f"Missing required fields: {', '.join(missing_fields)}")
            
            # Validate feedback type
            if data["feedback_type"] not in ["thumbs_up", "thumbs_down"]:
                raise ValidationError("feedback_type must be 'thumbs_up' or 'thumbs_down'")
            
            logger.info("Processing feedback submission", extra={
                "operation_id": operation_id,
                "request_id": data["request_id"],
                "feedback_type": data["feedback_type"]
            })
            
            # Generate question embedding
            question_vector = await self._embed_question(data["question"])
            
            # Process citations
            text_citations = []
            image_citations = []
            
            for citation_data in data.get("text_citations", []):
                citation = CitationData(
                    doc_id=citation_data.get("docId", ""),
                    content_id=citation_data.get("content_id", ""),
                    title=citation_data.get("title", ""),
                    text=citation_data.get("text"),
                    page_number=citation_data.get("locationMetadata", {}).get("pageNumber"),
                    bounding_polygons=citation_data.get("locationMetadata", {}).get("boundingPolygons"),
                    content_type=citation_data.get("content_type"),
                    is_image=False
                )
                text_citations.append(citation)
            
            for citation_data in data.get("image_citations", []):
                citation = CitationData(
                    doc_id=citation_data.get("docId", ""),
                    content_id=citation_data.get("content_id", ""),
                    title=citation_data.get("title", ""),
                    page_number=citation_data.get("locationMetadata", {}).get("pageNumber"),
                    bounding_polygons=citation_data.get("locationMetadata", {}).get("boundingPolygons"),
                    is_image=True,
                    image_url=citation_data.get("image_url"),
                    linked_image_path=citation_data.get("linked_image_path"),
                    source_figure_id=citation_data.get("source_figure_id")
                )
                image_citations.append(citation)
            
            # Process processing steps
            processing_steps = []
            for step_data in data.get("processing_steps", []):
                step = ProcessingStepData(
                    step_id=step_data.get("step_id", ""),
                    step_type=step_data.get("step_type", ""),
                    title=step_data.get("title", ""),
                    description=step_data.get("description"),
                    status=step_data.get("status", "completed"),
                    duration_ms=step_data.get("duration_ms"),
                    details=step_data.get("details")
                )
                processing_steps.append(step)
            
            # Create feedback entry
            feedback_entry = FeedbackEntry(
                feedback_id=f"feedback_{data['request_id']}_{int(time.time())}",
                request_id=data["request_id"],
                session_id=data["session_id"],
                timestamp=datetime.now(timezone.utc).isoformat(),
                feedback_type=data["feedback_type"],
                question=data["question"],
                question_vector=question_vector,
                response_text=data["response"],
                text_citations=text_citations,
                image_citations=image_citations,
                processing_steps=processing_steps,
                search_config=data.get("search_config", {}),
                user_agent=request.headers.get("User-Agent"),
                ip_address=request.remote
            )
            
            # Ensure index exists
            await self.initialize_feedback_index()
            
            # Store in search index
            search_client = self._get_search_client(request)
            document = feedback_entry.to_search_document()
            
            result = await search_client.upload_documents([document])
            
            if not result or not result[0].succeeded:
                error_msg = result[0].error_message if result else "Unknown error"
                raise ApplicationError(f"Failed to store feedback: {error_msg}")
            
            duration = time.time() - request_start
            logger.info("Feedback submitted successfully", extra={
                "operation_id": operation_id,
                "feedback_id": feedback_entry.feedback_id,
                "duration_seconds": round(duration, 3)
            })
            
            return web.json_response({
                "status": "success",
                "feedback_id": feedback_entry.feedback_id,
                "operation_id": operation_id
            })
            
        except ValidationError as e:
            return web.json_response({
                "status": "error",
                "message": str(e),
                "operation_id": operation_id
            }, status=400)
            
        except ApplicationError as e:
            return web.json_response({
                "status": "error", 
                "message": str(e),
                "operation_id": operation_id
            }, status=500)
            
        except Exception as e:
            logger.error("Unexpected error in feedback submission", extra={
                "operation_id": operation_id,
                "error": str(e)
            }, exc_info=True)
            return web.json_response({
                "status": "error",
                "message": "Internal server error",
                "operation_id": operation_id
            }, status=500)
    
    async def get_feedback_list(self, request: web.Request) -> web.Response:
        """Get paginated list of feedback entries for admin interface."""
        operation_id = f"feedback_list_{int(time.time())}"
        
        try:
            # Parse query parameters
            page = int(request.query.get("page", "1"))
            page_size = min(int(request.query.get("page_size", "20")), 100)  # Max 100 per page
            search_query = request.query.get("search", "").strip()
            feedback_type = request.query.get("feedback_type", "").strip()
            reviewed_filter = request.query.get("reviewed")
            sort_by = request.query.get("sort_by", "timestamp")
            sort_order = request.query.get("sort_order", "desc")
            
            if page < 1:
                page = 1
            if page_size < 1:
                page_size = 20
                
            skip = (page - 1) * page_size
            
            logger.info("Getting feedback list", extra={
                "operation_id": operation_id,
                "page": page,
                "page_size": page_size,
                "search_query": search_query
            })
            
            # Build search parameters
            search_text = search_query if search_query else "*"
            
            # Build filter
            filters = []
            if feedback_type in ["thumbs_up", "thumbs_down"]:
                filters.append(f"feedback_type eq '{feedback_type}'")
            if reviewed_filter is not None:
                is_reviewed = reviewed_filter.lower() == "true"
                filters.append(f"is_reviewed eq {str(is_reviewed).lower()}")
            
            filter_expression = " and ".join(filters) if filters else None
            
            # Build order by
            valid_sort_fields = ["timestamp", "last_modified", "feedback_type", "is_reviewed"]
            if sort_by not in valid_sort_fields:
                sort_by = "timestamp"
            if sort_order not in ["asc", "desc"]:
                sort_order = "desc"
                
            order_by = [f"{sort_by} {sort_order}"]
            
            # Ensure index exists
            await self.initialize_feedback_index()
            
            search_client = self._get_search_client(request)
            
            # Perform search
            results = await search_client.search(
                search_text=search_text,
                filter=filter_expression,
                order_by=order_by,
                skip=skip,
                top=page_size,
                include_total_count=True,
                select=["id", "request_id", "session_id", "timestamp", "feedback_type", 
                       "question", "response_text", "admin_notes", "is_reviewed", 
                       "last_modified", "modified_by", "text_citations_count", "image_citations_count",
                       "processing_steps"]
            )
            
            feedback_items = []
            async for result in results:
                # Handle processing_steps which might be JSON string or array
                processing_steps = result.get("processing_steps", [])
                if isinstance(processing_steps, str):
                    try:
                        import json
                        processing_steps = json.loads(processing_steps)
                    except:
                        processing_steps = []
                elif processing_steps is None:
                    processing_steps = []
                
                feedback_items.append({
                    "feedback_id": result["id"],
                    "request_id": result["request_id"],
                    "session_id": result["session_id"],
                    "timestamp": result["timestamp"],
                    "feedback_type": result["feedback_type"],
                    "question": result["question"],
                    "response_text": result["response_text"],
                    "admin_notes": result.get("admin_notes"),
                    "is_reviewed": result.get("is_reviewed", False),
                    "last_modified": result.get("last_modified"),
                    "modified_by": result.get("modified_by"),
                    "text_citations_count": result.get("text_citations_count", 0),
                    "image_citations_count": result.get("image_citations_count", 0),
                    "processing_steps": processing_steps
                })
            
            # Get total count - this is async in Azure Search SDK
            try:
                total_count = await results.get_count()
            except Exception:
                # Fallback to the number of items we got if get_count fails
                total_count = len(feedback_items)
            
            total_pages = (total_count + page_size - 1) // page_size
            
            return web.json_response({
                "status": "success",
                "data": {
                    "feedback_items": feedback_items,
                    "pagination": {
                        "page": page,
                        "page_size": page_size,
                        "total_count": total_count,
                        "total_pages": total_pages,
                        "has_next": page < total_pages,
                        "has_prev": page > 1
                    }
                },
                "operation_id": operation_id
            })
            
        except Exception as e:
            logger.error("Failed to get feedback list", extra={
                "operation_id": operation_id,
                "error": str(e)
            }, exc_info=True)
            return web.json_response({
                "status": "error",
                "message": "Failed to retrieve feedback list",
                "operation_id": operation_id
            }, status=500)
    
    async def get_feedback_detail(self, request: web.Request) -> web.Response:
        """Get detailed feedback entry for editing."""
        operation_id = f"feedback_detail_{int(time.time())}"
        
        try:
            feedback_id = request.match_info.get("feedback_id")
            if not feedback_id:
                raise ValidationError("Feedback ID is required")
            
            logger.info("Getting feedback detail", extra={
                "operation_id": operation_id,
                "feedback_id": feedback_id
            })
            
            # Ensure index exists
            await self.initialize_feedback_index()
            
            search_client = self._get_search_client(request)
            
            # Get the specific feedback entry by document key
            # Since 'id' is the key field, use get_document instead of search
            try:
                feedback_doc = await search_client.get_document(key=feedback_id)
            except ResourceNotFoundError:
                return web.json_response({
                    "status": "error",
                    "message": "Feedback entry not found",
                    "operation_id": operation_id
                }, status=404)
            
            # Convert to FeedbackEntry object and back to ensure proper format
            feedback_entry = FeedbackEntry.from_search_document(feedback_doc)
            
            return web.json_response({
                "status": "success",
                "data": asdict(feedback_entry),
                "operation_id": operation_id
            })
            
        except ValidationError as e:
            return web.json_response({
                "status": "error",
                "message": str(e),
                "operation_id": operation_id
            }, status=400)
            
        except Exception as e:
            logger.error("Failed to get feedback detail", extra={
                "operation_id": operation_id,
                "error": str(e)
            }, exc_info=True)
            return web.json_response({
                "status": "error",
                "message": "Failed to retrieve feedback detail",
                "operation_id": operation_id
            }, status=500)
    
    async def update_feedback(self, request: web.Request) -> web.Response:
        """Update feedback entry (admin only)."""
        operation_id = f"feedback_update_{int(time.time())}"
        
        try:
            feedback_id = request.match_info.get("feedback_id")
            if not feedback_id:
                raise ValidationError("Feedback ID is required")
            
            # Parse update data
            try:
                update_data = await request.json()
            except Exception as e:
                raise ValidationError("Invalid JSON in request body")
            
            logger.info("Updating feedback entry", extra={
                "operation_id": operation_id,
                "feedback_id": feedback_id
            })
            
            # Ensure index exists
            await self.initialize_feedback_index()
            
            search_client = self._get_search_client(request)
            
            # Get the specific feedback entry by document key
            # Since 'id' is the key field, use get_document instead of search
            try:
                existing_doc = await search_client.get_document(key=feedback_id)
            except ResourceNotFoundError:
                return web.json_response({
                    "status": "error",
                    "message": "Feedback entry not found",
                    "operation_id": operation_id
                }, status=404)
            
            # Update fields
            feedback_entry = FeedbackEntry.from_search_document(existing_doc)
            
            # Allow updating specific fields
            if "admin_notes" in update_data:
                feedback_entry.admin_notes = update_data["admin_notes"]
            if "is_reviewed" in update_data:
                feedback_entry.is_reviewed = bool(update_data["is_reviewed"])
            if "response_text" in update_data:
                feedback_entry.response_text = update_data["response_text"]
            if "feedback_type" in update_data:
                # Only allow changing to thumbs_up, and only if not reviewed
                if update_data["feedback_type"] == "thumbs_up" and not feedback_entry.is_reviewed:
                    feedback_entry.feedback_type = "thumbs_up"
            
            # Update modification tracking
            feedback_entry.last_modified = datetime.now(timezone.utc).isoformat()
            feedback_entry.modified_by = update_data.get("modified_by", "admin")
            
            # Save updated entry
            updated_document = feedback_entry.to_search_document()
            result = await search_client.merge_or_upload_documents([updated_document])
            
            if not result or not result[0].succeeded:
                error_msg = result[0].error_message if result else "Unknown error"
                raise ApplicationError(f"Failed to update feedback: {error_msg}")
            
            logger.info("Feedback entry updated successfully", extra={
                "operation_id": operation_id,
                "feedback_id": feedback_id
            })
            
            return web.json_response({
                "status": "success",
                "data": asdict(feedback_entry),
                "operation_id": operation_id
            })
            
        except ValidationError as e:
            return web.json_response({
                "status": "error",
                "message": str(e),
                "operation_id": operation_id
            }, status=400)
            
        except ApplicationError as e:
            return web.json_response({
                "status": "error",
                "message": str(e),
                "operation_id": operation_id
            }, status=500)
            
        except Exception as e:
            logger.error("Failed to update feedback entry", extra={
                "operation_id": operation_id,
                "error": str(e)
            }, exc_info=True)
            return web.json_response({
                "status": "error",
                "message": "Failed to update feedback entry",
                "operation_id": operation_id
            }, status=500)

    async def check_cache_for_similar_question(
        self, 
        question: str, 
        request: web.Request = None,
        similarity_threshold: float = 0.85,
        max_results: int = 5
    ) -> Optional[FeedbackEntry]:
        """
        Check if we have a similar question in the cache using vector similarity search.
        
        Args:
            question: The user's question to search for
            similarity_threshold: Minimum similarity score (0.0 to 1.0)
            max_results: Maximum number of results to check
            
        Returns:
            FeedbackEntry if a similar question is found, None otherwise
        """
        operation_id = f"cache_check_{int(time.time())}"
        
        try:
            logger.info("=== STARTING CACHE CHECK ===", extra={
                "operation_id": operation_id,
                "question": question[:200] + "..." if len(question) > 200 else question,
                "question_length": len(question),
                "similarity_threshold": similarity_threshold
            })
            
            # First, embed the user's question
            embedding_response = await self.openai_client.embeddings.create(
                input=question,
                model=self.embedding_deployment
            )
            question_vector = embedding_response.data[0].embedding
            
            logger.info("Generated question embedding", extra={
                "operation_id": operation_id,
                "embedding_dimension": len(question_vector)
            })
            
            # Ensure cache index exists
            await self.initialize_feedback_index()
            
            # Get search client using the existing method
            search_client = self._get_search_client(request)
            
            # Perform vector similarity search on cached questions
            # Only search through positive feedback (thumbs_up) that has been reviewed
            logger.info("Starting cache vector search", extra={
                "operation_id": operation_id,
                "vector_dimension": len(question_vector),
                "max_results": max_results
            })
            
            search_results = await search_client.search(
                search_text="*",
                #filter="feedback_type eq 'thumbs_up' and is_reviewed eq true",
                vector_queries=[VectorizedQuery(
                    vector=question_vector,
                    k_nearest_neighbors=max_results,
                    fields="question_vector"
                )],
                select=["id", "request_id", "session_id", "timestamp", "feedback_type", 
                       "question", "response_text", "text_citations", 
                       "image_citations", "processing_steps", "search_config", "admin_notes", 
                       "is_reviewed", "last_modified", "modified_by", "text_citations_count", 
                       "image_citations_count", "user_agent", "ip_address"],
                top=max_results
            )
            
            logger.info("Cache search query executed", extra={
                "operation_id": operation_id
            })
            
            # Check similarity scores and return the best match above threshold
            best_match = None
            best_score = 0.0  # Start with 0.0, only update if above threshold
            
            results_count = 0
            logger.info("=== STARTING RESULT PROCESSING ===")
            async for result in search_results:
                results_count += 1
                
                # Get the similarity score from the search result
                score = result.get('@search.score', 0.0)
                
                # Log detailed result info
                question_text = result.get("question", "N/A") if hasattr(result, 'get') else getattr(result, "question", "N/A")
                timestamp_text = result.get("timestamp", "N/A") if hasattr(result, 'get') else getattr(result, "timestamp", "N/A")
                
                logger.info("=== CACHE RESULT ANALYSIS ===", extra={
                    "operation_id": operation_id,
                    "result_number": results_count,
                    "cached_question": question_text[:100] + "..." if len(str(question_text)) > 100 else str(question_text),
                    "similarity_score": score,
                    "threshold": similarity_threshold,
                    "timestamp": timestamp_text,
                    "score_above_threshold": score >= similarity_threshold,
                    "result_type": type(result).__name__
                })
                
                if score >= similarity_threshold and score > best_score:
                    best_match = result
                    best_score = score
                    logger.info(f"NEW BEST MATCH: score={score}, threshold={similarity_threshold}")
                elif score >= similarity_threshold:
                    logger.info(f"ABOVE THRESHOLD but not better than current best: {score} vs {best_score}")
                else:
                    logger.info(f"BELOW THRESHOLD: {score} < {similarity_threshold}")
            
            logger.info("=== CACHE SEARCH COMPLETED ===", extra={
                "operation_id": operation_id,
                "total_results_found": results_count,
                "best_score_achieved": best_score,
                "similarity_threshold": similarity_threshold,
                "cache_hit": best_match is not None,
                "search_successful": results_count > 0
            })
            
            if best_match:
                logger.info("Cache hit - similar question found", extra={
                    "operation_id": operation_id,
                    "similarity_score": best_score,
                    "cached_question": best_match["question"][:100] + "...",
                    "cache_timestamp": best_match["timestamp"]
                })
                
                # Convert search result back to FeedbackEntry
                cached_entry = FeedbackEntry.from_search_document(best_match)
                return cached_entry
            else:
                logger.info("Cache miss - no similar question found", extra={
                    "operation_id": operation_id,
                    "results_checked": max_results,
                    "similarity_threshold": similarity_threshold
                })
                return None
                
        except Exception as e:
            logger.error("Failed to check cache for similar question", extra={
                "operation_id": operation_id,
                "error": str(e)
            }, exc_info=True)
            # Don't fail the entire request if cache check fails
            return None
    
    def attach_to_app(self, app: web.Application) -> None:
        """Attach feedback routes to the application."""
        logger.info("Attaching feedback routes to application")
        
        try:
            app.add_routes([
                web.post("/api/feedback/submit", self.submit_feedback),
                web.get("/api/feedback/list", self.get_feedback_list),
                web.get("/api/feedback/{feedback_id}", self.get_feedback_detail),
                web.put("/api/feedback/{feedback_id}", self.update_feedback),
            ])
            
            logger.info("Feedback routes successfully attached", extra={
                "routes": [
                    "/api/feedback/submit",
                    "/api/feedback/list", 
                    "/api/feedback/{feedback_id}",
                ]
            })
            
        except Exception as e:
            logger.error("Failed to attach feedback routes", extra={
                "error": str(e)
            }, exc_info=True)
            raise ApplicationError(f"Failed to attach feedback routes: {str(e)}")