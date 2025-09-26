import asyncio
import json
import logging
import uuid
from os import path
from aiohttp import web
from azure.search.documents.aio import SearchClient
from azure.search.documents.agent import KnowledgeAgentRetrievalClient
from azure.storage.blob import ContainerClient
from openai import AsyncAzureOpenAI
from typing import List, Optional, TYPE_CHECKING
from dataclasses import asdict

if TYPE_CHECKING:
    from handlers.feedback_handler import FeedbackHandler
from retrieval.grounding_retriever import GroundingRetriever
from retrieval.knowledge_agent import KnowledgeAgentGrounding
from utils.helpers import get_blob_as_base64
from retrieval.search_grounding import SearchGroundingRetriever
from core.rag_base import RagBase
from core.data_model import DataModel
from utils.prompts import (
    SYSTEM_PROMPT_NO_META_DATA,
)
from core.processing_step import ProcessingStep
from core.models import GroundingResult, Message, SearchConfig, GroundingResults

logger = logging.getLogger("multimodalrag")


class MultimodalRag(RagBase):
    """Handles multimodal RAG with AI Search, streaming responses with SSE."""

    def __init__(
        self,
        knowledge_agent: KnowledgeAgentGrounding | None,
        search_grounding: SearchGroundingRetriever,
        openai_client: AsyncAzureOpenAI,
        chatcompletions_model_name: str,
        container_client: ContainerClient,
        feedback_handler: Optional['FeedbackHandler'] = None,
    ):
        super().__init__(
            openai_client,
            chatcompletions_model_name,
        )
        self.container_client = container_client
        self.blob_service_client = container_client._get_blob_service_client()
        self.knowledge_agent = knowledge_agent
        self.search_grounding = search_grounding
        self.feedback_handler = feedback_handler
        # Log auth_mode if available on provided clients
        try:
            auth_mode = getattr(knowledge_agent, 'auth_mode', None) or getattr(search_grounding, 'auth_mode', None)
            logger.info("MultimodalRag initialized", extra={"auth_mode": auth_mode.value if getattr(auth_mode, 'value', None) else None})
        except Exception:
            logger.debug("Could not determine auth_mode for MultimodalRag", exc_info=True)

    async def _process_request(
        self,
        request_id: str,
        response: web.StreamResponse,
        user_message: str,
        chat_thread: list,
        search_config: SearchConfig,
        request: web.Request = None,
    ):
        """Processes a chat request through the RAG pipeline."""
        await self._send_processing_step_message(
            request_id,
            response,
            ProcessingStep(title="Search config", type="code", content=search_config),
        )

        # Add processing step to show chat history mode
        history_mode = "enabled" if search_config.get("use_chat_history", False) else "disabled"
        await self._send_processing_step_message(
            request_id,
            response,
            ProcessingStep(
                title="Chat History Mode",
                type="info",
                description=f"Chat history context is {history_mode}",
                content={
                    "use_chat_history": search_config.get("use_chat_history", False),
                    "chat_thread_length": len(chat_thread) if chat_thread else 0,
                    "mode_description": "Using conversation history for context-aware responses" if search_config.get("use_chat_history", False) else "Using only current question for search"
                }
            ),
        )

        grounding_results = None
        grounding_retriever = None
        messages = None
        
        # Cache checking step - check for similar questions first
        cached_response = None
        if self.feedback_handler and search_config.get("use_cache", True):
            try:
                await self._send_processing_step_message(
                    request_id,
                    response,
                    ProcessingStep(
                        title="Checking cache for similar questions",
                        type="info",
                        description="Searching for previously answered similar questions",
                        content={"user_message": user_message[:100] + "..." if len(user_message) > 100 else user_message}
                    ),
                )
                
                cached_response = await self.feedback_handler.check_cache_for_similar_question(
                    question=user_message,
                    request=request,
                    similarity_threshold=search_config.get("cache_similarity_threshold", 0.85),  # High threshold for quality
                    max_results=search_config.get("cache_max_results", 5)
                )
                
                if cached_response:
                    logger.info("Cache hit - returning cached response", extra={
                        "request_id": request_id,
                        "cached_question": cached_response.question[:100] + "...",
                        "cache_timestamp": cached_response.timestamp
                    })
                    
                    await self._send_processing_step_message(
                        request_id,
                        response,
                        ProcessingStep(
                            title="✅ Cache hit - Similar question found",
                            type="info",
                            description=f"Found similar question from {cached_response.timestamp}",
                            content={
                                "cached_question": cached_response.question,
                                "similarity_used": "High similarity match found in reviewed responses",
                                "cache_source": "feedback_cache",
                                "original_timestamp": cached_response.timestamp
                            }
                        ),
                    )
                    
                    # Return the cached response with cache indicator
                    msg_id = str(uuid.uuid4())
                    

                    
                    # Send cached response as single message (escape any problematic characters)
                    content_to_send = cached_response.response_text or ""
                    logger.info(f"Sending cached response, length: {len(content_to_send)}")
                    
                    # Clean the content to avoid JSON issues
                    clean_content = content_to_send.replace('\r\n', '\n').replace('\r', '\n')
                    
                    await self._send_answer_message(
                        request_id, response, msg_id, clean_content
                    )
                    
                    # Send cached citations
                    await self._send_citation_message(
                        request_id,
                        response,
                        msg_id,
                        [asdict(citation) for citation in cached_response.text_citations],
                        [asdict(citation) for citation in cached_response.image_citations],
                    )
                    
                    await self._send_processing_step_message(
                        request_id,
                        response,
                        ProcessingStep(
                            title="🎯 Response served from cache",
                            type="info",
                            description="Response retrieved from high-quality cached answers",
                            content={
                                "cache_indicator": True,
                                "performance": "Instant response - no search or LLM processing needed",
                                "quality": "Previously reviewed and approved response"
                            }
                        ),
                    )
                    
                    # Small delay to ensure frontend processes the answer before ending
                    await asyncio.sleep(0.1)
                    
                    return  # Exit early with cached response
                else:
                    await self._send_processing_step_message(
                        request_id,
                        response,
                        ProcessingStep(
                            title="Cache miss - No similar questions found",
                            type="info", 
                            description="Proceeding with full search and LLM processing",
                            content={
                                "cache_checked": True,
                                "similarity_threshold": search_config.get("cache_similarity_threshold", 0.85),
                                "next_step": "Full RAG pipeline processing"
                            }
                        ),
                    )
                    
            except Exception as cache_error:
                logger.error("Cache check failed, proceeding with normal flow", extra={
                    "request_id": request_id,
                    "error": str(cache_error)
                }, exc_info=True)
                await self._send_processing_step_message(
                    request_id,
                    response,
                    ProcessingStep(
                        title="Cache check failed - Proceeding with normal processing",
                        type="info",
                        description="Cache unavailable, using full search pipeline",
                        content={"cache_error": str(cache_error)}
                    ),
                )
        
        try:
            await self._send_processing_step_message(
                request_id,
                response,
                ProcessingStep(
                    title="Grounding the user message",
                    type="code",
                    content={"user_message": user_message, "chat_thread": chat_thread},
                ),
            )

            grounding_retriever = self._get_grounding_retriever(search_config)

            # Determine the appropriate title based on which retriever is being used
            retriever_title = "Knowledge Agent Progress" if search_config["use_knowledge_agent"] else "Search Progress"

            # Create a processing step callback to forward messages from the retriever
            async def processing_step_callback(message: str):
                await self._send_processing_step_message(
                    request_id,
                    response,
                    ProcessingStep(
                        title=retriever_title,
                        type="info", 
                        description=message,
                        content={"message": message},
                    ),
                )

            # Propagate per-request auth_mode (if middleware attached it) to the retriever
            try:
                # Prefer the original request attached to the response by RagBase
                req_auth_mode = None
                orig_req = getattr(response, '_orig_request', None)
                if orig_req is not None:
                    req_auth_mode = orig_req.get('auth_mode') if hasattr(orig_req, 'get') else None

                # Fallback: try to read from grounding_retriever or multimodal instance
                if req_auth_mode is None:
                    req_auth_mode = getattr(grounding_retriever, 'auth_mode', None) or getattr(self, 'auth_mode', None)

                if req_auth_mode is not None:
                    try:
                        grounding_retriever.auth_mode = req_auth_mode
                    except Exception:
                        logger.debug("Could not set auth_mode on grounding_retriever", exc_info=True)
            except Exception:
                logger.debug("Error while propagating auth_mode to retriever", exc_info=True)

            grounding_results = await grounding_retriever.retrieve(
                user_message, chat_thread, search_config, processing_step_callback
            )

            references_count = len(grounding_results['references'])
            
            # Show search configuration details when using search grounding (not Knowledge Agent)
            if not search_config["use_knowledge_agent"]:
                search_strategy_info = self._get_search_strategy_info(search_config)
                await self._send_processing_step_message(
                    request_id,
                    response,
                    ProcessingStep(
                        title="Search Strategy Configuration",
                        type="code",
                        description="Advanced search features being used",
                        content=search_strategy_info,
                    ),
                )
            
            # Create a meaningful summary of what was retrieved
            if references_count > 0:
                # Show preview of actual retrieved content
                content_preview = []
                for i, ref in enumerate(grounding_results['references'][:3]):  # First 3 references
                    content_text = ref.get('content', '')
                    preview = content_text[:100] + "..." if len(content_text) > 100 else content_text
                    content_preview.append({
                        "ref_id": ref.get('ref_id'),
                        "content_type": ref.get('content_type'),
                        "preview": preview,
                        "length": len(content_text)
                    })
                
                description = f"Retrieved {references_count} document references"
                if len(grounding_results['references']) > 3:
                    description += f" (showing first 3)"
                
                # Enhanced content for search grounding results
                result_content = {
                    "total_references": references_count,
                    "content_preview": content_preview,
                    "search_queries": grounding_results.get('search_queries', []),
                }
                
                # Add search quality information if using search grounding
                if not search_config["use_knowledge_agent"]:
                    result_content["search_method"] = "Direct Search Index"
                    result_content["features_used"] = self._get_features_used_summary(search_config)
                else:
                    result_content["search_method"] = "Knowledge Agent"
                    result_content["full_results"] = grounding_results  # Include full results for debugging
                    
                await self._send_processing_step_message(
                    request_id,
                    response,
                    ProcessingStep(
                        title="Document References Retrieved",
                        type="code",
                        description=description,
                        content=result_content,
                    ),
                )
            else:
                # Enhanced "no documents found" message for search grounding
                no_docs_content = grounding_results.copy()
                if not search_config["use_knowledge_agent"]:
                    no_docs_content["search_strategy"] = self._get_search_strategy_info(search_config)
                    no_docs_content["suggestions"] = [
                        "Try adjusting vector weight if using hybrid search",
                        "Consider enabling query rewriting for better recall",
                        "Check if semantic ranker is properly configured",
                        "Verify that documents exist in the search index"
                    ]
                
                await self._send_processing_step_message(
                    request_id,
                    response,
                    ProcessingStep(
                        title="No documents found",
                        type="info",
                        description="No documents matched the search criteria",
                        content=no_docs_content,
                    ),
                )

        except Exception as e:
            await self._send_processing_step_message(
                request_id,
                response,
                ProcessingStep(
                    title="Grounding failed",
                    type="code",
                    description=f"Error during grounding: {str(e)}",
                    content={"error": str(e), "user_message": user_message}
                ),
            )
            await self._send_error_message(
                request_id, response, "Grounding failed: " + str(e)
            )
            return

        try:
            messages = await self.prepare_llm_messages(
                grounding_results, chat_thread, user_message, search_config
            )

            await self._formulate_response(
                request_id,
                response,
                messages,
                grounding_retriever,
                grounding_results,
                search_config,
            )
            
        except Exception as e:
            # Even if LLM formulation fails, send processing steps to show what happened
            await self._send_processing_step_message(
                request_id,
                response,
                ProcessingStep(
                    title="LLM processing failed",
                    type="code",
                    description=f"Error during LLM response generation: {str(e)}",
                    content={
                        "error": str(e), 
                        "messages_sent_to_llm": messages,
                        "grounding_results_count": len(grounding_results.get('references', [])) if grounding_results else 0
                    }
                ),
            )
            await self._send_error_message(
                request_id, response, "LLM processing failed: " + str(e)
            )
            return

    def _get_grounding_retriever(self, search_config) -> GroundingRetriever:
        # Use knowledge agent only if it's available and explicitly requested
        if search_config["use_knowledge_agent"] and self.knowledge_agent is not None:
            logger.info("Using knowledge agent for grounding")
            return self.knowledge_agent
        else:
            logger.info("Using search index for grounding")
            return self.search_grounding

    def _get_search_strategy_info(self, search_config: SearchConfig) -> dict:
        """Generate detailed information about the search strategy being used."""
        strategy_info = {
            "search_type": "Advanced Search Index",
            "features_enabled": [],
            "configuration": {},
            "performance_settings": {}
        }
        
        # Check which features are enabled
        if search_config.get("use_hybrid_search", False):
            strategy_info["features_enabled"].append("Hybrid Search (Text + Vector with RRF)")
            strategy_info["configuration"]["vector_weight"] = search_config.get("vector_weight", 0.5)
            strategy_info["performance_settings"]["max_text_recall_size"] = search_config.get("max_text_recall_size", 1000)
            
            if search_config.get("enable_vector_filters", False):
                strategy_info["features_enabled"].append(f"Vector Filtering ({search_config.get('vector_filter_mode', 'preFilter')})")
                
        if search_config.get("use_semantic_ranker", False):
            strategy_info["features_enabled"].append("Semantic Ranking")
            
        if search_config.get("use_scoring_profile", False):
            strategy_info["features_enabled"].append("Scoring Profile Boost")
            strategy_info["configuration"]["scoring_profile"] = search_config.get("scoring_profile_name", "")
            
        if search_config.get("use_query_rewriting", False):
            strategy_info["features_enabled"].append("AI Query Rewriting")
            strategy_info["configuration"]["query_rewrite_count"] = search_config.get("query_rewrite_count", 3)
            
        # Set search type based on enabled features
        if not strategy_info["features_enabled"]:
            strategy_info["search_type"] = "Simple Text Search"
        elif "Hybrid Search" in str(strategy_info["features_enabled"]):
            strategy_info["search_type"] = "Hybrid Search with RRF"
        elif "Semantic Ranking" in str(strategy_info["features_enabled"]):
            strategy_info["search_type"] = "Semantic Text Search"
            
        strategy_info["configuration"]["chunk_count"] = search_config["chunk_count"]
        
        return strategy_info

    def _get_features_used_summary(self, search_config: SearchConfig) -> list:
        """Get a summary of which advanced search features were actually used."""
        features = []
        
        if search_config.get("use_hybrid_search", False):
            features.append(f"Hybrid Search (weight: {search_config.get('vector_weight', 0.5)})")
            
        if search_config.get("use_semantic_ranker", False):
            features.append("Semantic Ranking")
            
        if search_config.get("use_scoring_profile", False):
            profile_name = search_config.get("scoring_profile_name", "default")
            features.append(f"Scoring Profile ({profile_name})")
            
        if search_config.get("use_query_rewriting", False):
            count = search_config.get("query_rewrite_count", 3)
            features.append(f"Query Rewriting ({count} variants)")
            
        if search_config.get("enable_vector_filters", False):
            mode = search_config.get("vector_filter_mode", "preFilter")
            features.append(f"Vector Filtering ({mode})")
            
        if not features:
            features.append("Simple text search")
            
        return features

    async def prepare_llm_messages(
        self,
        grounding_results: GroundingResults,
        chat_thread: List[Message],
        search_text: str,
        search_config: Optional[dict] = None,
    ):
        logger.info("Preparing LLM messages")
        try:
            collected_documents = []
            for doc in grounding_results["references"]:
                if doc["content_type"] == "text":
                    # Format text documents as JSON objects with ref_id as expected by the system prompt
                    text_doc = {
                        "ref_id": doc["ref_id"],
                        "content": doc["content"] if isinstance(doc["content"], str) else str(doc["content"])
                    }
                    collected_documents.append(
                        {
                            "type": "text",
                            "text": json.dumps(text_doc),
                        }
                    )
                elif doc["content_type"] == "image":
                    collected_documents.append(
                        {
                            "type": "text",
                            "text": f"IMAGE REFERENCE with ID [{doc['ref_id']}]: The following image contains relevant information.",
                        }
                    )
                    # blob path differs if index was created through self script in repo or from the portal mulitmodal RAG wizard
                    blob_client = self.container_client.get_blob_client(doc["content"])
                    image_base64 = await get_blob_as_base64(blob_client)
                    if image_base64 is None:
                        content_path = doc["content"]
                        path_split = content_path.split("/")
                        content_container = path_split[0]
                        content_blob = "/".join(path_split[1:])
                        ks_container_client = (
                            self.blob_service_client.get_container_client(
                                content_container
                            )
                        )
                        blob_client = ks_container_client.get_blob_client(content_blob)
                        image_base64 = await get_blob_as_base64(blob_client)

                    collected_documents.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_base64}"
                            },
                        }
                    )

            # Use custom system prompt if provided, otherwise use default
            system_prompt = search_config.get("custom_system_prompt") if search_config else None
            if not system_prompt:
                system_prompt = SYSTEM_PROMPT_NO_META_DATA

            return [
                {
                    "role": "system",
                    "content": [{"text": system_prompt, "type": "text"}],
                },
                *chat_thread,
                {"role": "user", "content": [{"text": search_text, "type": "text"}]},
                {
                    "role": "user",
                    "content": collected_documents,
                },
            ]
        except Exception as e:
            logger.error(f"Error preparing LLM messages: {e}")
            raise e

    async def extract_citations(
        self,
        grounding_retriever: GroundingRetriever,
        grounding_results: List[GroundingResult],
        text_citation_ids: list,
        image_citation_ids: list,
    ) -> dict:
        """Extracts both text and image citations from search results."""
        return {
            "text_citations": await grounding_retriever._get_text_citations(
                text_citation_ids, grounding_results
            ),
            "image_citations": await grounding_retriever._get_image_citations(
                image_citation_ids, grounding_results
            ),
        }
