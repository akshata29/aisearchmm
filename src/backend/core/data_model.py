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
            "select": "content_id, content_text, document_title, text_document_id, image_document_id, locationMetadata, content_path, published_date, document_type",
            "query_type": query_type,
        }

        # Add semantic configuration if using semantic ranker
        if search_config.get("use_semantic_ranker", False):
            # Use the semantic configuration name that matches the index setup
            payload["semantic_configuration_name"] = "semantic-config"

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
            "select": "content_id, content_text, document_title, text_document_id, image_document_id, locationMetadata, content_path, published_date, document_type",
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

        # Add any additional filters
        additional_filters = search_config.get("additional_filters", [])
        if additional_filters:
            # Combine multiple filters with 'and'
            filter_string = " and ".join(additional_filters)
            payload["filter"] = filter_string

        return payload

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
                
        return warnings

    def extract_citation(self, document):
        # Ensure locationMetadata has the expected structure
        location_metadata = document.get("locationMetadata")
        if not location_metadata or not isinstance(location_metadata, dict):
            location_metadata = {"pageNumber": 1}  # Default fallback
        elif "pageNumber" not in location_metadata:
            location_metadata["pageNumber"] = 1  # Ensure pageNumber exists
            
        return {
            "locationMetadata": location_metadata,
            "text": document["content_text"],
            "title": document["document_title"],
            "content_id": document.get("content_id") or document.get("id"),
            "docId": (
                document["text_document_id"]
                if document["text_document_id"] is not None
                else document["image_document_id"]
            ),
        }

    async def collect_grounding_results(
        self, search_results: List[dict]
    ) -> List[GroundingResult]:
        collected_documents = []
        for result in search_results:
            is_image = result.get("image_document_id") is not None
            is_text = result.get("text_document_id") is not None

            if is_text and result["content_text"] is not None:
                collected_documents.append(
                    {
                        "ref_id": result.get("content_id") or result.get("id"),
                        "content": {
                            "ref_id": result.get("content_id") or result.get("id"),
                            "text": result["content_text"],
                        },
                        "content_type": "text",
                        **result,
                    }
                )
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
