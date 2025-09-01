import asyncio
import json
import logging
import os
import aiohttp
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Callable, Awaitable
from core.data_model import DataModel
from core.models import Message, GroundingResults, GroundingResult
from core.processing_step import ProcessingStep
from azure.search.documents.agent.aio import KnowledgeAgentRetrievalClient
from azure.search.documents.agent.models import (
    KnowledgeAgentRetrievalResponse,
    KnowledgeAgentRetrievalRequest,
    KnowledgeAgentIndexParams,
    KnowledgeAgentMessage,
    KnowledgeAgentMessageTextContent
)
from azure.search.documents.indexes.models import (
    KnowledgeAgent as AzureSearchKnowledgeAgent,
    KnowledgeAgentTargetIndex,
    KnowledgeAgentAzureOpenAIModel,
    AzureOpenAIVectorizerParameters,
)
from azure.search.documents.aio import SearchClient
from azure.search.documents.indexes.aio import SearchIndexClient
from retrieval.grounding_retriever import GroundingRetriever

logger = logging.getLogger("grounding")


class KnowledgeAgentGrounding(GroundingRetriever):
    def __init__(
        self,
        retrieval_agent_client: KnowledgeAgentRetrievalClient,
        search_client: SearchClient,
        index_client: SearchIndexClient,
        data_model: DataModel,
        index_name: str,
        agent_name: str,
        azure_openai_endpoint: str,
        azure_openai_searchagent_deployment: str,
        azure_openai_searchagent_model: str,
        blob_service_client=None,
        container_client=None,
        artifacts_container_client=None,
    ):
        self.retrieval_agent_client = retrieval_agent_client
        self.search_client = search_client
        self.index_client = index_client
        self.data_model = data_model
        self.index_name = index_name
        self.agent_name = agent_name
        self._blob_service_client = blob_service_client
        self._container_client = container_client
        self._artifacts_container_client = artifacts_container_client  # For images/figures
        
        # Store parameters for potential agent recreation during retrieval
        self.azure_openai_endpoint = azure_openai_endpoint
        self.azure_openai_searchagent_deployment = azure_openai_searchagent_deployment
        self.azure_openai_searchagent_model = azure_openai_searchagent_model

        self._create_retrieval_agent(
            agent_name,
            azure_openai_endpoint,
            azure_openai_searchagent_deployment,
            azure_openai_searchagent_model,
        )

    def _create_retrieval_agent(
        self,
        agent_name,
        azure_openai_endpoint,
        azure_openai_searchagent_deployment,
        azure_openai_searchagent_model,
    ):
        logger.info(f"Creating retrieval agent for {agent_name}")
        logger.info(f"OpenAI endpoint: {azure_openai_endpoint}")
        logger.info(f"Deployment name: {azure_openai_searchagent_deployment}")
        logger.info(f"Model name: {azure_openai_searchagent_model}")
        try:
            asyncio.create_task(
                self.index_client.create_or_update_agent(
                    agent=AzureSearchKnowledgeAgent(
                        name=agent_name,
                        target_indexes=[
                            KnowledgeAgentTargetIndex(
                                index_name=self.index_name,
                                default_include_reference_source_data=True,
                                # Enhanced defaults for better quality
                                default_reranker_threshold=2.0,  # Lower threshold for more results
                                default_max_docs_for_reranker=100,  # Increase for better coverage
                            )
                        ],
                        models=[
                            KnowledgeAgentAzureOpenAIModel(
                                azure_open_ai_parameters=AzureOpenAIVectorizerParameters(
                                    resource_url=azure_openai_endpoint,
                                    deployment_name=azure_openai_searchagent_deployment,
                                    api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
                                    model_name=azure_openai_searchagent_model,
                                )
                            )
                        ],
                        # Set max output size for better performance (5K tokens as recommended)
                        max_output_size=5000,
                    )
                )
            )
        except Exception as e:
            logger.error(f"Failed to create/update agent {agent_name}: {str(e)}")
            raise

    async def _create_retrieval_agent_async(
        self,
        agent_name,
        azure_openai_endpoint,
        azure_openai_searchagent_deployment,
        azure_openai_searchagent_model,
    ):
        """Async version of agent creation for use during retrieval error handling."""
        logger.info(f"Creating retrieval agent (async) for {agent_name}")
        logger.info(f"OpenAI endpoint: {azure_openai_endpoint}")
        logger.info(f"Deployment name: {azure_openai_searchagent_deployment}")
        logger.info(f"Model name: {azure_openai_searchagent_model}")
        
        try:
            await self.index_client.create_or_update_agent(
                agent=AzureSearchKnowledgeAgent(
                    name=agent_name,
                    target_indexes=[
                        KnowledgeAgentTargetIndex(
                            index_name=self.index_name,
                            default_include_reference_source_data=True,
                            # Enhanced defaults for better quality
                            default_reranker_threshold=2.0,  # Lower threshold for more results
                            default_max_docs_for_reranker=100,  # Increase for better coverage
                        )
                    ],
                    models=[
                        KnowledgeAgentAzureOpenAIModel(
                            azure_open_ai_parameters=AzureOpenAIVectorizerParameters(
                                resource_url=azure_openai_endpoint,
                                deployment_name=azure_openai_searchagent_deployment,
                                api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
                                model_name=azure_openai_searchagent_model,
                            )
                        )
                    ],
                    # Set max output size for better performance (5K tokens as recommended)
                    max_output_size=5000,
                )
            )
            logger.info(f"Successfully created/updated knowledge agent '{agent_name}'")
        except Exception as e:
            logger.error(f"Failed to create/update agent {agent_name}: {str(e)}")
            raise

    def _build_enhanced_filter(self, options: dict) -> Optional[str]:
        """Build OData filter based on prioritization strategy and user options."""
        filters = []
        
        # Priority 1: Recent documents filter (boost recent published dates)
        recency_days = options.get("recency_preference_days", 365)  # Default to 1 year
        if recency_days > 0:
            cutoff_date = datetime.utcnow() - timedelta(days=recency_days)
            # Note: We don't add this as a hard filter, but use it for boosting in scoring profiles
            logger.info(f"Prioritizing documents published after {cutoff_date.isoformat()}")
        
        # Priority 2: Document type preferences
        preferred_doc_types = options.get("preferred_document_types", [])
        if preferred_doc_types:
            type_filters = [f"document_type eq '{doc_type}'" for doc_type in preferred_doc_types]
            if len(type_filters) == 1:
                filters.append(type_filters[0])
            else:
                filters.append(f"({' or '.join(type_filters)})")
        
        # Additional filters from options
        additional_filters = options.get("additional_filters", [])
        filters.extend(additional_filters)
        
        return " and ".join(filters) if filters else None

    def _determine_reranker_params(self, options: dict) -> Dict[str, Any]:
        """Determine semantic reranker parameters based on query complexity and options."""
        query_complexity = options.get("query_complexity", "medium")  # low, medium, high
        chunk_count = options.get("chunk_count", 10)  # Get the chunk count from frontend
        
        # Base multipliers for different complexity levels
        if query_complexity == "high":
            base_multiplier = 15  # More comprehensive retrieval
            threshold = 2.0  # Balanced threshold for complex queries
        elif query_complexity == "low":
            base_multiplier = 5   # More focused retrieval
            threshold = 1.5  # Lower threshold for simple queries (more lenient)
        else:  # medium (default)
            base_multiplier = 10  # Balanced retrieval
            threshold = 1.8  # Balanced threshold
        
        # Calculate max_docs_for_reranker based on chunk_count
        # Ensure we retrieve more documents than the final chunk count for better reranking
        max_docs = max(chunk_count * base_multiplier, chunk_count + 20)  # At least 20 more than chunk_count
        max_docs = min(max_docs, 500)  # Cap at 500 to avoid performance issues
        max_docs = max(max_docs, 100)  # Ensure minimum of 100 as required by Azure AI Search
        
        return {
            "reranker_threshold": threshold,
            "max_docs_for_reranker": max_docs,
        }

    async def retrieve(
        self,
        user_message: str,
        chat_thread: List[Message],
        options: dict,
        processing_step_callback: Optional[Callable[[str], Awaitable[None]]] = None
    ) -> GroundingResults:
        """
        Enhanced retrieve method implementing prioritization logic:
        1. Recent published_date boosting
        2. Document type ranking  
        3. Semantic + keyword search combination
        """
        try:
            if processing_step_callback:
                # Combined setup and configuration message
                setup_msg = "🔎 Knowledge Agent Setup & Configuration\n"
                setup_msg += "• Building retrieval request with chat history\n"
                
                # Build enhanced filter for prioritization
                filter_expression = self._build_enhanced_filter(options)
                setup_msg += f"• Filter: {filter_expression or 'None'}\n"
                
                # Determine reranker parameters based on query complexity
                reranker_params = self._determine_reranker_params(options)
                setup_msg += f"• Reranker: threshold={reranker_params['reranker_threshold']}, max_docs={reranker_params['max_docs_for_reranker']}\n"
                setup_msg += f"• Target chunk count: {options.get('chunk_count', 10)}\n"
                setup_msg += "• Ready to execute retrieval..."
                
                await processing_step_callback(setup_msg)
            else:
                # Build enhanced filter for prioritization (still need these for the actual logic)
                filter_expression = self._build_enhanced_filter(options)
                # Determine reranker parameters based on query complexity
                reranker_params = self._determine_reranker_params(options)
                
            # Build messages in the correct format for agentic retrieval
            messages = []
            
            # Add chat history (limit to last 10 messages for performance)
            for msg in chat_thread[-10:]:
                messages.append(
                    KnowledgeAgentMessage(
                        role=msg["role"],
                        content=[KnowledgeAgentMessageTextContent(text=msg["content"])]
                    )
                )
            
            # Add current user message
            messages.append(
                KnowledgeAgentMessage(
                    role="user",
                    content=[KnowledgeAgentMessageTextContent(text=user_message)]
                )
            )
            
            # Prepare target index parameters with enhanced configuration
            target_index_params = KnowledgeAgentIndexParams(
                index_name=self.index_name,
                include_reference_source_data=True,
                filter_add_on=filter_expression,
                **reranker_params
            )
            
            logger.info(f"Knowledge Agent retrieval with filter: {filter_expression}")
            logger.info(f"Reranker params: {reranker_params}")
            logger.info(f"Target chunk count: {options.get('chunk_count', 10)}")

            # Execute agentic retrieval with enhanced parameters
            try:
                result = await self.retrieval_agent_client.retrieve(
                    retrieval_request=KnowledgeAgentRetrievalRequest(
                        messages=messages,
                        target_index_params=[target_index_params]
                    )
                )
            except Exception as retrieval_error:
                # Check if the error is due to missing agent
                error_str = str(retrieval_error).lower()
                if "no agent with the name" in error_str or "agent with the name" in error_str:
                    logger.warning(f"Knowledge agent '{self.agent_name}' not found. Creating agent...")
                    
                    if processing_step_callback:
                        await processing_step_callback(f"Creating missing knowledge agent '{self.agent_name}'...")
                    
                    # Create the agent and retry
                    try:
                        await self._create_retrieval_agent_async(
                            self.agent_name,
                            self.azure_openai_endpoint,
                            self.azure_openai_searchagent_deployment,
                            self.azure_openai_searchagent_model,
                        )
                        
                        logger.info(f"Successfully created knowledge agent '{self.agent_name}'. Retrying retrieval...")
                        
                        if processing_step_callback:
                            await processing_step_callback(f"Agent created successfully. Retrying retrieval...")
                        
                        # Retry the retrieval request
                        result = await self.retrieval_agent_client.retrieve(
                            retrieval_request=KnowledgeAgentRetrievalRequest(
                                messages=messages,
                                target_index_params=[target_index_params]
                            )
                        )
                        
                    except Exception as create_error:
                        logger.error(f"Failed to create knowledge agent '{self.agent_name}': {str(create_error)}")
                        raise Exception(f"Knowledge agent '{self.agent_name}' not found and could not be created: {str(create_error)}") from retrieval_error
                else:
                    # Re-raise the original error if it's not agent-related
                    raise retrieval_error
            
            # Debug the response structure
            self._debug_retrieval_response(result)

            # Process results with enhanced citation extraction
            references = await self._process_enhanced_results(result, options, processing_step_callback)
            
            if processing_step_callback:
                # Final summary of the entire Knowledge Agent process
                summary_msg = f"✅ Knowledge Agent Complete: {len(references)} references found"
                await processing_step_callback(summary_msg)
            
            return {
                "references": references,
                "search_queries": self._get_search_queries(result),
                "retrieval_metadata": {
                    "filter_applied": filter_expression,
                    "reranker_threshold": reranker_params["reranker_threshold"],
                    "max_docs_processed": reranker_params["max_docs_for_reranker"],
                    "total_references": len(references)
                }
            }
            
        except aiohttp.ClientError as e:
            logger.error(f"Error calling Azure AI Search Retrieval Agent: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in knowledge agent retrieval: {str(e)}")
            raise

    async def _process_enhanced_results(
        self, 
        result: KnowledgeAgentRetrievalResponse, 
        options: dict,
        processing_step_callback: Optional[Callable[[str], Awaitable[None]]] = None
    ) -> List[GroundingResult]:
        """Process and enhance retrieval results with additional metadata."""
        references: List[GroundingResult] = []
        
        try:
            result_dict = result.as_dict()
            response_items = result_dict.get('response', [])
            
            # Show detailed retrieval results instead of just counts
            if processing_step_callback:
                # Create detailed summary of what was retrieved - combine multiple messages into one
                retrieval_summary = f"📊 Knowledge Agent Retrieval Results\n"
                retrieval_summary += f"• Retrieved {len(response_items)} response items from index\n"
                
                # Add detailed breakdown
                if response_items:
                    retrieval_summary += "• Items breakdown:\n"
                    for i, item in enumerate(response_items):
                        item_sections = len(item.get("content", []))
                        retrieval_summary += f"  - Item {i + 1}: {item_sections} content sections\n"
                else:
                    retrieval_summary += "• No response items returned from Knowledge Agent\n"
                
                await processing_step_callback(retrieval_summary)
            
            logger.info(f"Processing {len(response_items)} response items")
            
            for ref in response_items:
                for content in ref.get("content", []):
                    content_text_str = content.get("text", "{}")
                    logger.debug(f"Processing content text: {content_text_str[:200]}...")
                    
                    try:
                        content_text = json.loads(content_text_str)
                        if not isinstance(content_text, list):
                            content_text = [content_text] if content_text else []
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse content as JSON: {e}")
                        content_text = []
                    
                    for reference in content_text:
                        if not isinstance(reference, dict) or "ref_id" not in reference:
                            logger.warning(f"Invalid reference format: {reference}")
                            continue
                            
                        # Try to get the document ID
                        try:
                            doc_id = self._get_document_id(reference["ref_id"], result)
                            logger.debug(f"Mapped ref_id {reference['ref_id']} to doc_id {doc_id}")
                        except Exception as e:
                            logger.warning(f"Could not map ref_id {reference['ref_id']}: {e}")
                            # Use the ref_id directly as fallback
                            doc_id = str(reference["ref_id"])
                        
                        # Enhance reference with prioritization metadata
                        # Create a clean content structure matching the system prompt expectations
                        enhanced_reference = {
                            "ref_id": doc_id,
                            "content": reference.get("content", ""),
                            "content_type": "text",  # Knowledge agent currently only returns text
                        }
                        
                        # Try to add document metadata if available
                        enhanced_reference["metadata"] = await self._fetch_document_metadata(doc_id, reference)
                        
                        # If this reference has linked images, add the image information to the main reference
                        if enhanced_reference["metadata"].get("has_linked_image"):
                            enhanced_reference["source_figure_id"] = enhanced_reference["metadata"].get("source_figure_id")
                            enhanced_reference["related_image_path"] = enhanced_reference["metadata"].get("related_image_path")
                            enhanced_reference["has_linked_image"] = True
                            
                            # Generate the image URL if we have the path
                            if enhanced_reference["metadata"].get("related_image_path"):
                                enhanced_reference["linked_image_url"] = await self._generate_image_url(
                                    enhanced_reference["metadata"]["related_image_path"]
                                )
                        else:
                            enhanced_reference["has_linked_image"] = False
                        
                        references.append(enhanced_reference)
            
            if processing_step_callback:
                # Show actual processed references content
                if references:
                    summary_msg = f"✔️ Processed {len(references)} references from search results"
                    await processing_step_callback(summary_msg)
                else:
                    await processing_step_callback("✔️ Processed 0 references - no content extracted from response items")
            
            logger.info(f"Processed {len(references)} references successfully")
            
            # Apply post-processing prioritization if needed
            pre_prioritization_count = len(references)
            references = self._apply_post_processing_prioritization(references, options)
            
            if processing_step_callback:
                # Show post-processing results  
                prioritization_msg = f"🎯 Post-processing: {pre_prioritization_count} → {len(references)} references"
                await processing_step_callback(prioritization_msg)
            
            # Limit results to the requested chunk_count
            chunk_count = options.get("chunk_count", 10)
            pre_limit_count = len(references)
            if len(references) > chunk_count:
                references = references[:chunk_count]
                if processing_step_callback:
                    final_msg = f"📏 Applied chunk limit: {pre_limit_count} → {chunk_count} references"
                    await processing_step_callback(final_msg)
                logger.info(f"Limited results to {chunk_count} references based on chunk_count setting")
            elif processing_step_callback and len(references) > 0:
                final_msg = f"✅ Final {len(references)} references ready for LLM"
                await processing_step_callback(final_msg)
            
        except Exception as e:
            logger.error(f"Error processing enhanced results: {str(e)}")
            # Return whatever references we managed to process
            if not references:
                raise
            
        return references

    async def _fetch_document_metadata(self, doc_id: str, reference: dict) -> dict:
        """Safely fetch document metadata with fallbacks."""
        metadata = {
            "published_date": None,
            "document_type": None,
            "document_title": None,
            "relevance_score": reference.get("score", 0),
            # Initialize figure-related fields
            "source_figure_id": None,
            "related_image_path": None,
            "has_linked_image": False
        }
        
        try:
            # Try to fetch the full document
            document = await self.search_client.get_document(doc_id)
            metadata.update({
                "published_date": document.get("published_date"),
                "document_type": document.get("document_type"),
                "document_title": document.get("document_title"),
                # Extract figure-related fields
                "source_figure_id": document.get("source_figure_id"),
                "related_image_path": document.get("related_image_path")
            })
            
            # Check if this content has linked images
            has_linked_image = (
                document.get("source_figure_id") is not None or 
                document.get("related_image_path") is not None
            )
            metadata["has_linked_image"] = has_linked_image
            
            logger.debug(f"Successfully fetched metadata for document {doc_id}, has_linked_image: {has_linked_image}")
            
        except Exception as e:
            logger.warning(f"Could not fetch metadata for document {doc_id}: {e}")
            
            # Try to extract metadata from the reference content itself
            try:
                if isinstance(reference, dict):
                    # Check if metadata is embedded in the reference
                    if "title" in reference:
                        metadata["document_title"] = reference["title"]
                    if "document_type" in reference:
                        metadata["document_type"] = reference["document_type"]
                    if "published_date" in reference:
                        metadata["published_date"] = reference["published_date"]
                    # Extract figure-related fields from reference
                    if "source_figure_id" in reference:
                        metadata["source_figure_id"] = reference["source_figure_id"]
                    if "related_image_path" in reference:
                        metadata["related_image_path"] = reference["related_image_path"]
                    
                    # Check if this content has linked images based on fallback data
                    has_linked_image = (
                        reference.get("source_figure_id") is not None or 
                        reference.get("related_image_path") is not None
                    )
                    metadata["has_linked_image"] = has_linked_image
                        
                logger.debug(f"Using fallback metadata for document {doc_id}, has_linked_image: {metadata['has_linked_image']}")
            except Exception as fallback_error:
                logger.debug(f"Could not extract fallback metadata: {fallback_error}")
        
        return metadata

    def _debug_retrieval_response(self, result: KnowledgeAgentRetrievalResponse):
        """Debug method to understand the structure of the agentic retrieval response."""
        try:
            result_dict = result.as_dict()
            logger.debug("=== AGENTIC RETRIEVAL RESPONSE DEBUG ===")
            logger.debug(f"Response keys: {list(result_dict.keys())}")
            
            # Debug response structure
            response_items = result_dict.get("response", [])
            logger.debug(f"Response items count: {len(response_items)}")
            
            for i, item in enumerate(response_items[:2]):  # Limit to first 2 items
                logger.debug(f"Response item {i}: {list(item.keys())}")
                contents = item.get("content", [])
                logger.debug(f"  Content items: {len(contents)}")
                for j, content in enumerate(contents[:1]):  # Limit to first content
                    text_sample = content.get("text", "")[:200]
                    logger.debug(f"  Content {j} text sample: {text_sample}")
            
            # Debug references structure
            if hasattr(result, 'references') and result.references:
                logger.debug(f"References count: {len(result.references)}")
                for i, ref in enumerate(result.references[:3]):  # Limit to first 3
                    ref_dict = ref.as_dict()
                    logger.debug(f"Reference {i}: id={ref_dict.get('id')}, doc_key={ref_dict.get('doc_key')}")
            else:
                logger.debug("No references found in response")
                
            # Debug activity structure
            if hasattr(result, 'activity') and result.activity:
                logger.debug(f"Activity items count: {len(result.activity)}")
                for i, activity in enumerate(result.activity[:2]):  # Limit to first 2
                    activity_dict = activity.as_dict()
                    logger.debug(f"Activity {i}: type={activity_dict.get('type')}")
            else:
                logger.debug("No activity found in response")
                
            logger.debug("=== END DEBUG ===")
            
        except Exception as debug_error:
            logger.warning(f"Error in debug method: {debug_error}")

    def _apply_post_processing_prioritization(
        self, 
        references: List[GroundingResult], 
        options: dict
    ) -> List[GroundingResult]:
        """Apply additional prioritization logic after retrieval."""
        if not options.get("enable_post_processing_boost", True):
            return references
            
        def priority_score(ref: GroundingResult) -> float:
            """Calculate priority score based on our ranking criteria."""
            score = 0.0
            metadata = ref.get("metadata", {})
            
            # Factor 1: Recency boost (highest priority)
            published_date = metadata.get("published_date")
            if published_date:
                try:
                    pub_date = datetime.fromisoformat(published_date.replace('Z', '+00:00'))
                    days_old = (datetime.now(pub_date.tzinfo) - pub_date).days
                    
                    # Exponential decay for recency (newer = higher score)
                    if days_old <= 30:
                        score += 3.0  # Very recent
                    elif days_old <= 90:
                        score += 2.0  # Recent
                    elif days_old <= 365:
                        score += 1.0  # Moderately recent
                    # Older documents get no recency boost
                        
                except (ValueError, TypeError):
                    pass  # Invalid date format
            
            # Factor 2: Document type priority (medium priority)
            doc_type = metadata.get("document_type", "").lower()
            preferred_types = [t.lower() for t in options.get("preferred_document_types", [])]
            
            if doc_type in preferred_types:
                type_index = preferred_types.index(doc_type)
                score += 2.0 - (type_index * 0.2)  # First preferred type gets highest boost
            
            # Factor 3: Original relevance score (semantic + keyword)
            original_score = metadata.get("relevance_score", 0)
            score += original_score * 0.5  # Weight original score appropriately
            
            return score
        
        # Sort by priority score (descending)
        try:
            references.sort(key=priority_score, reverse=True)
            logger.info(f"Applied post-processing prioritization to {len(references)} references")
        except Exception as e:
            logger.warning(f"Error in post-processing prioritization: {e}")
            
        return references

    async def _get_text_citations(
        self, ref_ids: List[str], grounding_results: GroundingResults
    ) -> List[dict]:
        """Enhanced text citation extraction with metadata and linked image URL generation."""
        try:
            citations = []
            for ref_id in ref_ids:
                try:
                    document = await self.search_client.get_document(ref_id)
                    citation = self.data_model.extract_citation(document)
                    
                    # Add enhanced metadata to citations
                    citation.update({
                        "published_date": document.get("published_date"),
                        "document_type": document.get("document_type"),
                        "enhanced_metadata": True
                    })
                    
                    # If this citation has a linked image, generate the image URL
                    if citation.get("show_image") and citation.get("linked_image_path"):
                        try:
                            image_url = await self._generate_image_url(citation["linked_image_path"])
                            citation["image_url"] = image_url
                        except Exception as img_error:
                            logger.warning(f"Could not generate image URL for {citation['linked_image_path']}: {img_error}")
                    
                    citations.append(citation)
                    
                except Exception as doc_error:
                    logger.warning(f"Could not fetch document {ref_id} for citation: {doc_error}")
                    
                    # Create a minimal citation from available data
                    minimal_citation = {
                        "ref_id": ref_id,
                        "text": f"Reference {ref_id}",
                        "title": f"Document {ref_id}",
                        "content_id": ref_id,
                        "docId": ref_id,
                        "locationMetadata": {"pageNumber": 1},  # Default page number
                        "published_date": None,
                        "document_type": None,
                        "enhanced_metadata": False,
                        "show_image": False
                    }
                    
                    # Try to extract info from grounding results
                    try:
                        for ref in grounding_results.get("references", []):
                            if ref.get("ref_id") == ref_id:
                                ref_metadata = ref.get("metadata", {})
                                minimal_citation.update({
                                    "published_date": ref_metadata.get("published_date"),
                                    "document_type": ref_metadata.get("document_type"),
                                    "title": ref_metadata.get("document_title", f"Document {ref_id}"),
                                })
                                if ref.get("content", {}).get("text"):
                                    minimal_citation["text"] = ref["content"]["text"][:200] + "..."
                                break
                    except Exception as fallback_error:
                        logger.debug(f"Could not extract fallback citation data: {fallback_error}")
                    
                    citations.append(minimal_citation)
                    
            return citations
            
        except Exception as e:
            logger.error(f"Error creating enhanced text citations: {str(e)}")
            # Return empty list rather than raising to allow the response to continue
            return []

    async def _get_image_citations(
        self, ref_ids: List[str], grounding_results: GroundingResults
    ) -> List[dict]:
        """Enhanced image citation extraction with support for linked images from text content."""
        if not ref_ids:
            return []
        
        # Debug log to understand the data structure
        logger.debug(f"_get_image_citations: ref_ids={ref_ids}, grounding_results type={type(grounding_results)}")
        logger.debug(f"grounding_results keys: {grounding_results.keys() if isinstance(grounding_results, dict) else 'not a dict'}")
            
        from handlers.citation_file_handler import CitationFilesHandler
        from azure.storage.blob.aio import BlobServiceClient
        
        # Get blob service client for URL generation
        # This assumes the container client is available in the data model or retriever
        try:
            # Try to get blob service from the search client's credential context
            # This is a simplified approach - in production, you'd want to inject this dependency
            blob_service_client = getattr(self, '_blob_service_client', None)
            container_client = getattr(self, '_container_client', None)
            artifacts_container_client = getattr(self, '_artifacts_container_client', None)
            
            if not blob_service_client or not container_client:
                # Fallback to basic citation extraction without image URLs
                return self._extract_basic_image_citations(ref_ids, grounding_results)
                
            citation_handler = CitationFilesHandler(blob_service_client, container_client, artifacts_container_client)
            
            try:
                # Handle both dictionary and list formats for grounding_results
                if isinstance(grounding_results, dict) and "references" in grounding_results:
                    references_list = grounding_results["references"]
                elif isinstance(grounding_results, list):
                    # grounding_results is directly a list of references
                    references_list = grounding_results
                else:
                    logger.error(f"Unexpected grounding_results format: {type(grounding_results)}")
                    return []
                
                references = {
                    grounding_result["ref_id"]: grounding_result
                    for grounding_result in references_list
                }
            except Exception as e:
                logger.error(f"Error creating references dict: {e}")
                logger.error(f"grounding_results structure: {grounding_results}")
                return []
            
            extracted_citations = []
            for ref_id in ref_ids:
                if ref_id in references:
                    ref = references[ref_id]
                    
                    # Process actual image citations
                    if ref.get("content_type") == "image":
                        citation = self.data_model.extract_citation(ref)
                        
                        # Generate image URL for this citation
                        try:
                            content_path = ref.get("content_path") or ref.get("content")
                            if content_path:
                                image_url = await citation_handler._get_file_url(content_path)
                                citation["image_url"] = image_url
                                citation["is_image"] = True
                        except Exception as e:
                            logger.warning(f"Could not generate image URL for {ref_id}: {e}")
                            citation["is_image"] = True  # Still mark as image even if URL generation fails
                            
                        extracted_citations.append(citation)
                    
                    # Process text citations that have linked images
                    elif ref.get("content_type") == "text" and ref.get("has_linked_image"):
                        citation = self.data_model.extract_citation(ref)
                        
                        # The citation already has the linked image URL from our processing
                        if citation.get("show_image") and citation.get("linked_image_url"):
                            # Create an image citation entry for the linked figure
                            # Ensure locationMetadata has a complete structure
                            original_location = citation.get("locationMetadata", {})
                            safe_location_metadata = {
                                "pageNumber": original_location.get("pageNumber", 1) if original_location else 1,
                                "boundingPolygons": original_location.get("boundingPolygons", "") if original_location else ""
                            }
                            
                            image_citation = {
                                "ref_id": ref_id,
                                "content_id": citation.get("content_id"),
                                "title": citation.get("title"),
                                "source_figure_id": citation.get("source_figure_id"),
                                "image_url": citation.get("linked_image_url"),
                                "is_image": True,
                                "is_linked_from_text": True,  # Flag to indicate this came from text
                                "text_ref_id": ref_id,  # Reference back to the text citation
                                # Ensure locationMetadata is included for frontend compatibility
                                "locationMetadata": safe_location_metadata,
                                "docId": citation.get("docId")
                            }
                            extracted_citations.append(image_citation)
                        
            return extracted_citations
            
        except Exception as e:
            logger.error(f"Error in enhanced image citation extraction: {e}")
            # Fallback to basic extraction
            return self._extract_basic_image_citations(ref_ids, grounding_results)
            
    def _extract_basic_image_citations(self, ref_ids: List[str], grounding_results: GroundingResults) -> List[dict]:
        """Basic image citation extraction without image URLs, supports both direct images and linked images."""
        if not ref_ids:
            return []
        
        try:
            # Handle both dictionary and list formats for grounding_results
            if isinstance(grounding_results, dict) and "references" in grounding_results:
                references_list = grounding_results["references"]
            elif isinstance(grounding_results, list):
                # grounding_results is directly a list of references
                references_list = grounding_results
            else:
                logger.error(f"Unexpected grounding_results format in basic extraction: {type(grounding_results)}")
                return []
            
            references = {
                grounding_result["ref_id"]: grounding_result
                for grounding_result in references_list
            }
        except Exception as e:
            logger.error(f"Error creating references dict in basic extraction: {e}")
            logger.error(f"grounding_results structure: {grounding_results}")
            return []
        
        extracted_citations = []
        for ref_id in ref_ids:
            if ref_id in references:
                ref = references[ref_id]
                
                # Process actual image citations
                if ref.get("content_type") == "image":
                    citation = self.data_model.extract_citation(ref)
                    citation["is_image"] = True
                    extracted_citations.append(citation)
                
                # Process text citations that have linked images (basic version without URL generation)
                elif ref.get("content_type") == "text" and ref.get("has_linked_image"):
                    citation = self.data_model.extract_citation(ref)
                    
                    if citation.get("show_image"):
                        # Create a basic image citation entry for the linked figure
                        image_citation = {
                            "ref_id": ref_id,
                            "content_id": citation.get("content_id"),
                            "title": citation.get("title"),
                            "source_figure_id": citation.get("source_figure_id"),
                            "linked_image_path": citation.get("linked_image_path"),
                            "is_image": True,
                            "is_linked_from_text": True,
                            "text_ref_id": ref_id
                        }
                        # Note: No image_url in basic version - frontend will need to handle path-to-URL conversion
                        extracted_citations.append(image_citation)
                    
        return extracted_citations

    def _get_search_queries(self, response: KnowledgeAgentRetrievalResponse) -> List[str]:
        """Extract search queries from the agentic retrieval response."""
        try:
            queries = []
            for activity in response.activity:
                activity_dict = activity.as_dict()
                if activity_dict.get("type") == "AzureSearchQuery":
                    query_info = activity_dict.get("query", {})
                    if isinstance(query_info, dict):
                        search_text = query_info.get("search", "")
                        if search_text:
                            queries.append(search_text)
                    elif isinstance(query_info, str):
                        queries.append(query_info)
            return queries
        except Exception as e:
            logger.warning(f"Error extracting search queries: {e}")
            return []

    def _get_document_id(
        self, ref_id: str, response: KnowledgeAgentRetrievalResponse
    ) -> str:
        """Extract document ID from reference ID in the response."""
        try:
            logger.debug(f"Looking for document ID for ref_id: {ref_id}")
            
            if not hasattr(response, 'references') or not response.references:
                logger.warning("No references found in response")
                return str(ref_id)  # Fallback to using ref_id as doc_id
            
            for i, ref in enumerate(response.references):
                try:
                    ref_dict = ref.as_dict()
                    ref_dict_id = str(ref_dict.get("id", ""))
                    doc_key = ref_dict.get("doc_key", "")
                    
                    logger.debug(f"Reference {i}: id={ref_dict_id}, doc_key={doc_key}")
                    
                    if ref_dict_id == str(ref_id):
                        if doc_key:
                            logger.debug(f"Found mapping: ref_id {ref_id} -> doc_key {doc_key}")
                            return doc_key
                        else:
                            logger.warning(f"Found reference {ref_id} but no doc_key")
                            return str(ref_id)
                            
                except Exception as ref_error:
                    logger.warning(f"Error processing reference {i}: {ref_error}")
                    continue
            
            logger.warning(f"Reference ID {ref_id} not found in {len(response.references)} references")
            return str(ref_id)  # Fallback to using ref_id as doc_id
            
        except Exception as e:
            logger.error(f"Error finding document ID for ref_id {ref_id}: {e}")
            return str(ref_id)  # Fallback to using ref_id as doc_id

    async def _generate_image_url(self, blob_path: str) -> str:
        """Generate a signed URL for an image blob path."""
        try:
            if not self._blob_service_client or not self._artifacts_container_client:
                logger.warning("Blob service client or artifacts container client not available for image URL generation")
                return ""
                
            # Clean up the blob path
            clean_blob_path = blob_path.replace("\\", "/")
            
            # Get blob client from artifacts container (where images are stored)
            blob_client = self._artifacts_container_client.get_blob_client(clean_blob_path)
            
            # Generate SAS token for the blob
            start_time = datetime.utcnow()
            expiry_time = start_time + timedelta(hours=1)
            
            # Create user delegation key
            user_delegation_key = await self._blob_service_client.get_user_delegation_key(
                key_start_time=start_time, 
                key_expiry_time=expiry_time
            )
            
            # Generate SAS token for artifacts container
            from azure.storage.blob import generate_blob_sas, BlobSasPermissions
            sas_token = generate_blob_sas(
                account_name=blob_client.account_name or "",
                container_name=self._artifacts_container_client.container_name,  # Use artifacts container
                blob_name=clean_blob_path,
                user_delegation_key=user_delegation_key,
                permission=BlobSasPermissions(read=True),
                expiry=datetime.utcnow() + timedelta(minutes=60),
            )
            
            signed_url = f"{blob_client.url}?{sas_token}"
            logger.debug(f"Generated image URL for {blob_path}: {signed_url[:100]}...")
            return signed_url
            
        except Exception as e:
            logger.error(f"Error generating image URL for {blob_path}: {str(e)}")
            return ""

    def get_retrieval_strategy_info(self) -> Dict[str, Any]:
        """Return information about the current retrieval strategy configuration."""
        return {
            "strategy_type": "enhanced_knowledge_agent",
            "agent_name": self.agent_name,
            "index_name": self.index_name,
            "prioritization_logic": {
                "primary": "recent_published_date_boost",
                "secondary": "document_type_ranking", 
                "tertiary": "semantic_keyword_hybrid"
            },
            "features": [
                "agentic_retrieval",
                "semantic_ranking",
                "freshness_boosting",
                "document_type_prioritization",
                "enhanced_filtering",
                "post_processing_prioritization"
            ],
            "recommended_options": {
                "chunk_count": 10,  # Number of final results to return
                "recency_preference_days": 365,
                "query_complexity": "medium",
                "preferred_document_types": ["research_paper", "technical_document", "report"],
                "enable_post_processing_boost": True,
                "additional_filters": []
            }
        }
