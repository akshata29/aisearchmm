import logging
from typing import List, Dict, TypedDict, Optional, Callable, Awaitable
from openai import AsyncAzureOpenAI
from core.data_model import DataModel
from utils.prompts import SEARCH_QUERY_SYSTEM_PROMPT
from core.models import Message, SearchConfig, GroundingResults
from azure.search.documents.aio import SearchClient
from retrieval.grounding_retriever import GroundingRetriever

logger = logging.getLogger("groundingapi")


class SearchGroundingRetriever(GroundingRetriever):

    def __init__(
        self,
        search_client: SearchClient,
        openai_client: AsyncAzureOpenAI,
        data_model: DataModel,
        chatcompletions_deployment_name: str,
        blob_service_client=None,
        container_client=None,
        artifacts_container_client=None,
    ):
        self.search_client = search_client
        self.openai_client = openai_client
        self.data_model = data_model
        self.chatcompletions_deployment_name = chatcompletions_deployment_name
        self._blob_service_client = blob_service_client
        self._container_client = container_client
        self._artifacts_container_client = artifacts_container_client

    async def retrieve(
        self,
        user_message: str,
        chat_thread: List[Message],
        options: SearchConfig,
        processing_step_callback: Optional[Callable[[str], Awaitable[None]]] = None
    ) -> GroundingResults:

        if processing_step_callback:
            await processing_step_callback("Generating search query...")
        
        logger.info("Generating search query")
        query = await self._generate_search_query(user_message, chat_thread)
        logger.info(f"Generated search query: {query}")

        if processing_step_callback:
            await processing_step_callback(f"Generated search query: {query}")
            
        # Validate search configuration and show warnings
        validation_warnings = self.data_model.validate_search_configuration(options)
        if validation_warnings and processing_step_callback:
            for warning in validation_warnings:
                await processing_step_callback(f"⚠️ Configuration warning: {warning}")

        try:
            payload = self.data_model.create_search_payload(query, options)

            search_kwargs = {
                "search_text": payload["search"],
                "top": payload["top"],
                "query_type": payload.get("query_type", "simple"),
                "select": payload["select"],
            }
            
            # Add vector queries if present (for hybrid search)
            if "vector_queries" in payload and payload["vector_queries"]:
                search_kwargs["vector_queries"] = payload["vector_queries"]
                
            # Add semantic configuration if present
            if "semantic_configuration_name" in payload and payload["semantic_configuration_name"]:
                search_kwargs["semantic_configuration_name"] = payload["semantic_configuration_name"]
                
            # Add scoring profile if present
            if "scoring_profile" in payload and payload["scoring_profile"]:
                search_kwargs["scoring_profile"] = payload["scoring_profile"]
                
            # Add vector filter mode if present
            if "vector_filter_mode" in payload and payload["vector_filter_mode"]:
                search_kwargs["vector_filter_mode"] = payload["vector_filter_mode"]
                
            # Add filter if present
            if "filter" in payload and payload["filter"]:
                search_kwargs["filter"] = payload["filter"]

            if processing_step_callback:
                search_type = "Hybrid" if "vector_queries" in search_kwargs else "Text-only"
                semantic_info = " with Semantic Ranker" if "semantic_configuration_name" in search_kwargs else ""
                scoring_info = f" using scoring profile '{search_kwargs.get('scoring_profile', '')}'" if "scoring_profile" in search_kwargs else ""
                filter_info = f" (vector filter: {search_kwargs.get('vector_filter_mode', 'none')})" if "vector_filter_mode" in search_kwargs else ""
                
                await processing_step_callback(
                    f"Executing {search_type} Azure AI Search{semantic_info}{scoring_info}{filter_info}..."
                )
                
            search_results = await self.search_client.search(**search_kwargs)
        except Exception as e:
            error_msg = str(e).lower()
            
            # Provide specific error messages for common issues
            if "vector" in error_msg and "field" in error_msg:
                raise Exception(f"Vector field not found in index. Ensure your index has a vector field named 'content_vector' or update the field name in the configuration. Original error: {str(e)}")
            elif "semantic" in error_msg and "configuration" in error_msg:
                raise Exception(f"Semantic configuration 'semantic-config' not found in index. Create a semantic configuration or disable semantic ranking. Original error: {str(e)}")
            elif "scoring" in error_msg and "profile" in error_msg:
                raise Exception(f"Scoring profile not found in index. Check the scoring profile name or disable scoring profiles. Original error: {str(e)}")
            elif "query_rewrites" in error_msg or "rewrite" in error_msg:
                raise Exception(f"Query rewriting not supported. This feature requires a recent API version and may not be available in all regions. Original error: {str(e)}")
            else:
                raise Exception(f"Azure AI Search request failed: {str(e)}")

        results_list = []
        async for result in search_results:
            results_list.append(result)

        if processing_step_callback:
            await processing_step_callback(f"Found {len(results_list)} search results")
            
            # Provide detailed information about search results quality
            if len(results_list) > 0:
                # Check for different types of scores
                score_types = []
                semantic_scores = []
                rrf_scores = []
                boosted_scores = []
                
                for result in results_list:
                    # Check for different score types
                    if hasattr(result, '@search.rerankerScore'):
                        semantic_scores.append(getattr(result, '@search.rerankerScore'))
                    if hasattr(result, '@search.score'):
                        rrf_scores.append(getattr(result, '@search.score'))
                    if hasattr(result, '@search.rerankerBoostedScore'):
                        boosted_scores.append(getattr(result, '@search.rerankerBoostedScore'))
                
                # Report on scoring information
                if semantic_scores:
                    avg_semantic = sum(semantic_scores) / len(semantic_scores)
                    max_semantic = max(semantic_scores)
                    score_types.append(f"semantic (avg: {avg_semantic:.2f}, max: {max_semantic:.2f})")
                    
                if rrf_scores and "vector_queries" in search_kwargs:
                    avg_rrf = sum(rrf_scores) / len(rrf_scores)
                    score_types.append(f"RRF fusion (avg: {avg_rrf:.2f})")
                    
                if boosted_scores:
                    avg_boosted = sum(boosted_scores) / len(boosted_scores)
                    score_types.append(f"scoring profile boosted (avg: {avg_boosted:.2f})")
                    
                if score_types:
                    await processing_step_callback(f"Scores available: {', '.join(score_types)}")

        references = await self.data_model.collect_grounding_results(results_list)

        if processing_step_callback:
            await processing_step_callback(f"Processed {len(references)} references successfully")
            
            # Provide summary of content types retrieved
            text_count = sum(1 for ref in references if ref.get("content_type") == "text")
            image_count = sum(1 for ref in references if ref.get("content_type") == "image")
            
            content_summary = []
            if text_count > 0:
                content_summary.append(f"{text_count} text chunks")
            if image_count > 0:
                content_summary.append(f"{image_count} images")
                
            if content_summary:
                await processing_step_callback(f"Retrieved: {', '.join(content_summary)}")

        return {
            "references": references,
            "search_queries": [query],
        }

    async def _generate_search_query(
        self, user_message: str, chat_thread: List[Message]
    ) -> str:
        """Generate an optimized search query, with potential enhancements for hybrid search."""
        try:
            messages = [
                {"role": "user", "content": user_message},
                *chat_thread,
            ]

            # Enhanced system prompt for better query generation
            enhanced_system_prompt = SEARCH_QUERY_SYSTEM_PROMPT + """

For hybrid search scenarios, focus on:
- Key concepts and entities rather than stop words
- Technical terms and domain-specific vocabulary
- Synonyms and related terminology that might appear in vector embeddings
- Balance between specific terms (for text search) and conceptual meaning (for vector search)
"""

            response = await self.openai_client.chat.completions.create(
                model=self.chatcompletions_deployment_name,
                messages=[
                    {"role": "system", "content": enhanced_system_prompt},
                    *messages,
                ],
                temperature=0.1,  # Lower temperature for more consistent query generation
                max_tokens=100    # Limit query length
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"Error while calling Azure OpenAI to generate search query, using original query: {str(e)}")
            # Fallback to original user message if query generation fails
            return user_message

    async def _get_image_citations(
        self, ref_ids: List[str], grounding_results: GroundingResults
    ) -> List[dict]:
        """Enhanced image citation extraction with image URL generation."""
        if not ref_ids:
            return []
            
        from handlers.citation_file_handler import CitationFilesHandler
        
        try:
            # Get blob service client for URL generation
            blob_service_client = getattr(self, '_blob_service_client', None)
            container_client = getattr(self, '_container_client', None)
            artifacts_container_client = getattr(self, '_artifacts_container_client', None)
            
            if not blob_service_client or not container_client:
                # Fallback to basic citation extraction without image URLs
                return self._extract_basic_image_citations(ref_ids, grounding_results)
                
            citation_handler = CitationFilesHandler(blob_service_client, container_client, artifacts_container_client)
            
            references = {
                grounding_result["ref_id"]: grounding_result
                for grounding_result in grounding_results["references"]
            }
            
            extracted_citations = []
            for ref_id in ref_ids:
                if ref_id in references:
                    ref = references[ref_id]
                    # Only process image citations
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
                        
            return extracted_citations
            
        except Exception as e:
            logger.error(f"Error in enhanced image citation extraction: {e}")
            # Fallback to basic extraction
            return self._extract_basic_image_citations(ref_ids, grounding_results)
            
    def _extract_basic_image_citations(self, ref_ids: List[str], grounding_results: GroundingResults) -> List[dict]:
        """Basic image citation extraction without image URLs."""
        return self._extract_citations(ref_ids, grounding_results)

    async def _get_text_citations(
        self, ref_ids: List[str], grounding_results: GroundingResults
    ) -> List[dict]:
        return self._extract_citations(ref_ids, grounding_results)

    def _extract_citations(
        self, ref_ids: List[str], grounding_results: GroundingResults
    ) -> List[dict]:
        if not ref_ids:
            return []

        references = {
            grounding_result["ref_id"]: grounding_result
            for grounding_result in grounding_results
        }
        extracted_citations = []
        for ref_id in ref_ids:
            if ref_id in references:
                ref = references[ref_id]
                extracted_citations.append(self.data_model.extract_citation(ref))
        return extracted_citations
