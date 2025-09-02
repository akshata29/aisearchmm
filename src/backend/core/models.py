from typing import List, Literal, Optional, Dict, TypedDict
from pydantic import BaseModel


class SearchConfig(TypedDict):
    """Configuration for search parameters."""

    chunk_count: int = 10
    openai_api_mode: Literal["chat_completions"] = "chat_completions"
    use_semantic_ranker: bool = False
    use_streaming: bool = False
    use_knowledge_agent: bool = False
    
    # Enhanced Knowledge Agent options
    recency_preference_days: Optional[int] = 90  # Boost documents within this many days
    query_complexity: Optional[Literal["low", "medium", "high"]] = "medium"
    preferred_document_types: Optional[List[str]] = None  # e.g., ["research_paper", "technical_document"]
    enable_post_processing_boost: Optional[bool] = True
    additional_filters: Optional[List[str]] = None  # Additional OData filters
    
    # Hybrid Search Configuration (when not using Knowledge Agent)
    use_hybrid_search: Optional[bool] = False  # Enable hybrid search (text + vector)
    use_query_rewriting: Optional[bool] = False  # Enable semantic query rewriting
    use_scoring_profile: Optional[bool] = False  # Enable scoring profile for freshness/type boosts
    scoring_profile_name: Optional[str] = None  # Name of the scoring profile to use
    vector_weight: Optional[float] = 0.5  # Weight for vector queries in hybrid search (0.0-1.0)
    rrf_k_parameter: Optional[int] = 60  # RRF k parameter for ranking fusion
    semantic_ranking_threshold: Optional[float] = 2.0  # Minimum semantic score threshold
    enable_vector_filters: Optional[bool] = False  # Enable pre/post filtering for vector queries
    vector_filter_mode: Optional[Literal["preFilter", "postFilter"]] = "preFilter"  # Vector filter mode
    query_rewrite_count: Optional[int] = 3  # Number of query rewrites to generate


class SearchRequestParameters(TypedDict):
    """Structure for search request payload."""

    search: str
    top: int = 10
    query_type: Optional[str] = None
    vector_queries: Optional[List[Dict]] = None
    semantic_configuration_name: Optional[str] = None
    search_fields: Optional[List[str]] = None
    select: Optional[str] = None
    scoring_profile: Optional[str] = None
    vector_filter_mode: Optional[str] = None
    filter: Optional[str] = None


class GroundingResult(TypedDict):
    """Structure for individual grounding results."""

    ref_id: str
    content: dict
    content_type: Literal["text", "image"]


class GroundingResults(TypedDict):
    """Structure for grrounding results with references and queries."""

    references: List[GroundingResult]
    search_queries: List[str]


class AnswerFormat(BaseModel):
    """Format for chat completion responses."""

    answer: str
    text_citations: List[str] = []
    image_citations: List[str] = []


class MessageContent(TypedDict):
    text: str
    type: Literal["text"]


class Message(TypedDict):
    role: Literal["user", "assistant", "system"]
    content: List[MessageContent]
