from abc import ABC, abstractmethod
from typing import List
from core.models import (
    SearchRequestParameters,
    SearchConfig,
    GroundingResult,
    GroundingResults,
)


class DataModel(ABC):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @abstractmethod
    def create_search_payload(
        self, query: str, search_config: SearchConfig
    ) -> SearchRequestParameters:
        """Creates the search request payload."""
        pass

    @abstractmethod
    def extract_citation(
        self,
        document: dict,
    ) -> dict:
        """Extracts citations from search results."""
        pass

    @abstractmethod
    async def collect_grounding_results(self, search_results: List[dict]) -> list:
        """Collects and formats documents from search results."""
        pass


class DocumentPerChunkDataModel(DataModel):
    def create_search_payload(
        self, query: str, search_config: SearchConfig
    ) -> SearchRequestParameters:
        """Creates the search request payload with hybrid search, RRF, semantic ranker, and scoring profiles."""

        # Determine if we're using Knowledge Agent or advanced search features
        use_knowledge_agent = search_config.get("use_knowledge_agent", False)
        
        # When not using Knowledge Agent, we can implement advanced search features
        if not use_knowledge_agent:
            return self._create_advanced_search_payload(query, search_config)
        else:
            return self._create_simple_search_payload(query, search_config)

    def _create_simple_search_payload(
        self, query: str, search_config: SearchConfig
    ) -> SearchRequestParameters:
        """Creates a simple search payload for Knowledge Agent scenarios."""
        
        # Use semantic query type only if semantic ranker is enabled
        query_type = "semantic" if search_config.get("use_semantic_ranker", False) else "simple"
        
        payload = {
            "search": query,
            "top": search_config["chunk_count"],
            "select": "content_id, content_text, document_title, text_document_id, image_document_id, locationMetadata, content_path, published_date, expiry_date, document_type",
            "query_type": query_type,
        }

        # Add semantic configuration if using semantic ranker
        if search_config.get("use_semantic_ranker", False):
            # Use the semantic configuration name that matches the index setup
            payload["semantic_configuration_name"] = "semantic-config"

        # Add recency filter if specified (similar to Knowledge Agent)
        recency_days = search_config.get("recency_preference_days")
        filters = []
        
        if recency_days and recency_days < 1095:  # Only filter if less than 3 years (1095 days)
            from datetime import datetime, timedelta
            cutoff_date = datetime.utcnow() - timedelta(days=recency_days)
            cutoff_date_str = cutoff_date.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            recency_filter = f"published_date ge {cutoff_date_str}"
            filters.append(recency_filter)
        
        # Add document type preferences with default ordering
        preferred_doc_types = search_config.get("preferred_document_types", [])
        
        # If no document types specified, default to the core 3 in order
        if not preferred_doc_types:
            preferred_doc_types = ["book", "Nyp, Nl", "cr"]
        else:
            # Ensure proper ordering: book, Nyp, Nl, cr first, then others
            preferred_doc_types = self._order_document_types(preferred_doc_types)
        
        if preferred_doc_types:
            type_filters = [f"document_type eq '{doc_type}'" for doc_type in preferred_doc_types]
            if len(type_filters) == 1:
                filters.append(type_filters[0])
            else:
                filters.append(f"({' or '.join(type_filters)})")
        
        # Add any additional filters
        additional_filters = search_config.get("additional_filters", [])
        if additional_filters:
            filters.extend(additional_filters)
            
        if filters:
            # Combine multiple filters with 'and'
            filter_string = " and ".join(filters)
            payload["filter"] = filter_string

        return payload

    def _create_advanced_search_payload(
        self, query: str, search_config: SearchConfig
    ) -> SearchRequestParameters:
        """
        Creates an advanced search payload with hybrid search, RRF, and semantic features.
        
        This implementation follows Azure AI Search best practices for:
        1. Hybrid Search: Combines text and vector search using RRF for optimal relevance
        2. Semantic Ranker: Applied after RRF to further improve results
        3. Scoring Profiles: Applied after semantic ranking when configured with "boostedReRankerScore"
        4. Query Rewriting: Uses AI to generate alternative query formulations
        5. Vector Filtering: Optimizes performance with large datasets
        
        The search flow is: Text Search + Vector Search → RRF → Semantic Ranker → Scoring Profile
        """
        
        # Base payload
        payload = {
            "search": query,
            "top": search_config["chunk_count"],
            "select": "content_id, content_text, document_title, text_document_id, image_document_id, locationMetadata, content_path, published_date, expiry_date, document_type",
        }

        # Check if hybrid search is enabled
        use_hybrid_search = search_config.get("use_hybrid_search", False)
        use_semantic_ranker = search_config.get("use_semantic_ranker", False)
        
        if use_hybrid_search:
            # Set up hybrid search with vector queries
            payload["query_type"] = "semantic" if use_semantic_ranker else "simple"
            
            # Add vector queries for hybrid search
            # Note: Azure AI Search will automatically apply RRF when both text and vector queries are present
            vector_weight = search_config.get("vector_weight", 0.5)
            
            # Determine the vector field name - this should match your index schema
            # From app.py: SearchField(name="content_embedding", ...)
            vector_field_name = "content_embedding"
            
            payload["vector_queries"] = [
                {
                    "kind": "text",  # Use integrated vectorization if available
                    "text": query,
                    "k": min(search_config["chunk_count"] * 2, 50),  # Request more for better RRF
                    "fields": vector_field_name,
                    "weight": vector_weight,
                    "exhaustive": True  # For better recall in hybrid scenarios
                }
            ]
            
            # Set vector filter mode if enabled
            if search_config.get("enable_vector_filters", False):
                payload["vector_filter_mode"] = search_config.get("vector_filter_mode", "preFilter")
            
            # Note: max_text_recall_size is not a valid Azure AI Search parameter
            # RRF will automatically handle text recall sizing based on the 'k' parameter in vector queries
                
        elif use_semantic_ranker:
            # Pure semantic search without hybrid
            payload["query_type"] = "semantic"
        else:
            # Simple text search
            payload["query_type"] = "simple"

        # Add semantic configuration if using semantic features
        if use_semantic_ranker or use_hybrid_search:
            payload["semantic_configuration_name"] = "semantic-config"

        # Add scoring profile for freshness/type boosts
        # Important: With API version 2025-05-01-preview and newer, scoring profiles
        # are applied AFTER semantic ranking when using "boostedReRankerScore" in semantic config
        if search_config.get("use_scoring_profile", False):
            scoring_profile_name = search_config.get("scoring_profile_name", "freshness_and_type_boost")
            if scoring_profile_name:
                payload["scoring_profile"] = scoring_profile_name

        # Add query rewriting if enabled (Note: This may require specific API version)
        # Commenting out for now due to potential compatibility issues
        # if search_config.get("use_query_rewriting", False):
        #     query_rewrite_count = search_config.get("query_rewrite_count", 3)
        #     payload["query_rewrites"] = f"generative|count-{query_rewrite_count}"
        #     payload["query_language"] = "en-US"  # Default to English, could be configurable

        # Add recency filter if specified (similar to Knowledge Agent)
        recency_days = search_config.get("recency_preference_days")
        filters = []
        
        if recency_days and recency_days < 1095:  # Only filter if less than 3 years (1095 days)
            from datetime import datetime, timedelta
            cutoff_date = datetime.utcnow() - timedelta(days=recency_days)
            cutoff_date_str = cutoff_date.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            recency_filter = f"published_date ge {cutoff_date_str}"
            filters.append(recency_filter)
        
        # Add document type preferences with default ordering
        preferred_doc_types = search_config.get("preferred_document_types", [])
        
        # If no document types specified, default to the core 3 in order
        if not preferred_doc_types:
            preferred_doc_types = ["book", "Nyp, Nl", "cr"]
        else:
            # Ensure proper ordering: book, Nyp, Nl, cr first, then others
            preferred_doc_types = self._order_document_types(preferred_doc_types)
        
        if preferred_doc_types:
            type_filters = [f"document_type eq '{doc_type}'" for doc_type in preferred_doc_types]
            if len(type_filters) == 1:
                filters.append(type_filters[0])
            else:
                filters.append(f"({' or '.join(type_filters)})")
        
        # Add any additional filters
        additional_filters = search_config.get("additional_filters", [])
        if additional_filters:
            filters.extend(additional_filters)
            
        if filters:
            # Combine multiple filters with 'and'
            filter_string = " and ".join(filters)
            payload["filter"] = filter_string

        return payload

    def _order_document_types(self, doc_types: List[str]) -> List[str]:
        """Ensure document types follow the preferred order: book, Nyp, Nl, cr, then others."""
        priority_order = ["book", "Nyp, Nl", "cr"]
        ordered_types = []
        
        # Add priority types first if they exist in the list
        for priority_type in priority_order:
            if priority_type in doc_types:
                ordered_types.append(priority_type)
        
        # Add remaining types that are not in priority list
        for doc_type in doc_types:
            if doc_type not in priority_order and doc_type not in ordered_types:
                ordered_types.append(doc_type)
        
        return ordered_types

    def validate_search_configuration(self, search_config: SearchConfig) -> List[str]:
        """
        Validates the search configuration and returns any warnings or recommendations.
        Returns a list of validation messages.
        """
        warnings = []
        
        # Check hybrid search configuration
        if search_config.get("use_hybrid_search", False):
            if not search_config.get("use_semantic_ranker", False):
                warnings.append("Hybrid search works best with semantic ranker enabled")
                
            vector_weight = search_config.get("vector_weight", 0.5)
            if vector_weight < 0.1 or vector_weight > 1.0:
                warnings.append("Vector weight should be between 0.1 and 1.0")
                
        # Check scoring profile configuration
        if search_config.get("use_scoring_profile", False):
            if not search_config.get("use_semantic_ranker", False):
                warnings.append("Scoring profiles work best with semantic ranker enabled")
                
            profile_name = search_config.get("scoring_profile_name", "")
            if not profile_name or profile_name.strip() == "":
                warnings.append("Scoring profile name is required when scoring profiles are enabled")
                
        # Check query rewriting configuration
        if search_config.get("use_query_rewriting", False):
            rewrite_count = search_config.get("query_rewrite_count", 3)
            if rewrite_count > 5:
                warnings.append("High query rewrite count may impact response time")
                
        # Check vector filter configuration
        if search_config.get("enable_vector_filters", False):
            if not search_config.get("use_hybrid_search", False):
                warnings.append("Vector filters are only useful with hybrid search enabled")
        
        # Check recency preference configuration
        recency_days = search_config.get("recency_preference_days")
        if recency_days:
            if recency_days < 30:
                warnings.append("Very short recency preference may exclude relevant content")
            elif recency_days < 1095:  # Less than 3 years
                warnings.append(f"Recency filter active: only documents from last {recency_days} days will be included")
                
        return warnings

    def extract_citation(self, document):
        # Ensure locationMetadata has the expected structure
        location_metadata = document.get("locationMetadata")
        if not location_metadata or not isinstance(location_metadata, dict):
            location_metadata = {"pageNumber": 1}  # Default fallback
        elif "pageNumber" not in location_metadata:
            location_metadata["pageNumber"] = 1  # Ensure pageNumber exists
            
        citation = {
            "locationMetadata": location_metadata,
            "text": document["content"] if isinstance(document.get("content"), str) else document.get("content_text", ""),
            "title": document.get("document_title") or document.get("metadata", {}).get("document_title", ""),
            "content_id": document.get("content_id") or document.get("id") or document.get("ref_id"),
            "docId": (
                document.get("text_document_id")
                if document.get("text_document_id") is not None
                else document.get("image_document_id") or document.get("ref_id")
            ),
        }
        
        # Add content type and path information for images
        if document.get("content_type") == "image" or document.get("image_document_id") is not None:
            citation["content_type"] = "image"
            citation["content_path"] = document.get("content_path") or document.get("content")
            citation["is_image"] = True
        else:
            citation["content_type"] = "text"
            citation["is_image"] = False
            
            # Check for linked image information - handle both Knowledge Agent and direct search results
            has_linked_image = (
                document.get("has_linked_image") or
                document.get("source_figure_id") is not None or 
                document.get("related_image_path") is not None or
                document.get("metadata", {}).get("has_linked_image")
            )
            
            if has_linked_image:
                # Get image path from various possible locations
                linked_image_path = (
                    document.get("related_image_path") or 
                    document.get("linked_image_path") or
                    document.get("metadata", {}).get("related_image_path")
                )
                
                # Get figure ID from various possible locations  
                source_figure_id = (
                    document.get("source_figure_id") or
                    document.get("metadata", {}).get("source_figure_id")
                )
                
                # Get image URL if available (from Knowledge Agent processing)
                linked_image_url = document.get("linked_image_url")
                
                if linked_image_path or source_figure_id or linked_image_url:
                    citation["linked_image_path"] = linked_image_path
                    citation["source_figure_id"] = source_figure_id
                    citation["linked_image_url"] = linked_image_url
                    citation["show_image"] = True
                else:
                    citation["show_image"] = False
            else:
                citation["show_image"] = False
            
        return citation

    async def collect_grounding_results(
        self, search_results: List[dict]
    ) -> List[GroundingResult]:
        collected_documents = []
        for result in search_results:
            is_image = result.get("image_document_id") is not None
            is_text = result.get("text_document_id") is not None
            
            # Check if this text content is linked to a figure/image
            has_linked_image = (
                result.get("source_figure_id") is not None or 
                result.get("related_image_path") is not None
            )

            if is_text and result["content_text"] is not None:
                text_doc = {
                    "ref_id": result.get("content_id") or result.get("id"),
                    "content": {
                        "ref_id": result.get("content_id") or result.get("id"),
                        "text": result["content_text"],
                    },
                    "content_type": "text",
                    **result,
                }
                
                # If this text content is linked to an image, add image citation info
                if has_linked_image:
                    text_doc["linked_image_path"] = result.get("related_image_path")
                    text_doc["source_figure_id"] = result.get("source_figure_id")
                    text_doc["has_linked_image"] = True
                
                collected_documents.append(text_doc)
                    
            elif is_image and result["content_path"] is not None:
                collected_documents.append(
                    {
                        "ref_id": result.get("content_id") or result.get("id"),
                        "content": result["content_path"],
                        "content_type": "image",
                        **result,
                    }
                )
            else:
                raise ValueError(
                    f"Values for both image_chunk_document_id and text_chunk_document_id are missing for result: {result}"
                )
        return collected_documents
