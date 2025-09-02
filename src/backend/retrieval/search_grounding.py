import logging
import asyncio
import sys
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
            # Log document type filtering information
            preferred_doc_types = options.get("preferred_document_types", [])
            if not preferred_doc_types:
                logger.info("Search grounding: Using default document types: otq, nyp_columns, client_reviews")
                if processing_step_callback:
                    await processing_step_callback("📋 Using default document types: Only Three Questions, NYP Columns, Client Reviews")
            else:
                # Ensure proper ordering
                ordered_doc_types = self._order_document_types(preferred_doc_types)
                if ordered_doc_types != preferred_doc_types:
                    # Update the options to use the properly ordered types
                    options = {**options, "preferred_document_types": ordered_doc_types}
                    logger.info(f"Search grounding: Reordered document types: {ordered_doc_types}")
                else:
                    logger.info(f"Search grounding: Filtering by document types: {preferred_doc_types}")
                
                if processing_step_callback:
                    type_names = []
                    for doc_type in ordered_doc_types:
                        if doc_type == "otq":
                            type_names.append("Only Three Questions")
                        elif doc_type == "nyp_columns":
                            type_names.append("NYP Columns")
                        elif doc_type == "client_reviews":
                            type_names.append("Client Reviews")
                        else:
                            type_names.append(doc_type.replace("_", " ").title())
                    await processing_step_callback(f"📋 Filtering document types: {', '.join(type_names)}")

            # Recreate payload with potentially updated options
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
                
                # Add information about document type filtering
                filter_applied = search_kwargs.get("filter", "")
                doc_type_info = ""
                if filter_applied and "document_type eq" in filter_applied:
                    doc_type_info = " with document type filtering"
                
                await processing_step_callback(
                    f"Executing {search_type} Azure AI Search{semantic_info}{scoring_info}{filter_info}{doc_type_info}..."
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

        # Enhance references with additional metadata, similar to knowledge agent
        enhanced_references = []
        for reference in references:
            if reference.get("content_type") == "text":
                # Try to get enhanced metadata for text references
                try:
                    ref_id = reference.get("ref_id")
                    if ref_id:
                        metadata = await self._fetch_document_metadata(ref_id, reference)
                        
                        # Update the reference with enhanced metadata
                        reference["metadata"] = metadata
                        
                        # If this reference has linked images, add the image information to the main reference
                        if metadata.get("has_linked_image"):
                            reference["source_figure_id"] = metadata.get("source_figure_id")
                            reference["related_image_path"] = metadata.get("related_image_path")
                            reference["has_linked_image"] = True
                            
                            # Generate the image URL if we have the path
                            if metadata.get("related_image_path"):
                                try:
                                    reference["linked_image_url"] = await self._generate_image_url(
                                        metadata["related_image_path"]
                                    )
                                except Exception as url_error:
                                    logger.warning(f"Could not generate image URL for {metadata['related_image_path']}: {url_error}")
                        else:
                            reference["has_linked_image"] = False
                            
                except Exception as e:
                    logger.warning(f"Could not enhance metadata for reference {reference.get('ref_id')}: {e}")
                    # Set default values if enhancement fails
                    reference["has_linked_image"] = False
            
            enhanced_references.append(reference)

        if processing_step_callback:
            await processing_step_callback(f"Processed {len(enhanced_references)} references successfully")
            
            # Provide summary of content types retrieved
            text_count = sum(1 for ref in enhanced_references if ref.get("content_type") == "text")
            image_count = sum(1 for ref in enhanced_references if ref.get("content_type") == "image")
            linked_image_count = sum(1 for ref in enhanced_references if ref.get("has_linked_image"))
            
            content_summary = []
            if text_count > 0:
                content_summary.append(f"{text_count} text chunks")
            if image_count > 0:
                content_summary.append(f"{image_count} images")
            if linked_image_count > 0:
                content_summary.append(f"{linked_image_count} with linked images")
                
            if content_summary:
                await processing_step_callback(f"Retrieved: {', '.join(content_summary)}")

        return {
            "references": enhanced_references,
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
        """Enhanced image citation extraction with support for linked images from text content."""
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
                        
                        # Check if this text citation has a linked image and generate the URL if needed
                        if citation.get("show_image"):
                            linked_image_url = citation.get("linked_image_url")
                            
                            # If we don't have the URL yet, generate it from the path
                            if not linked_image_url and citation.get("linked_image_path"):
                                try:
                                    linked_image_url = await self._generate_image_url(citation["linked_image_path"])
                                except Exception as url_error:
                                    logger.warning(f"Could not generate image URL for {citation['linked_image_path']}: {url_error}")
                                    linked_image_url = None
                            
                            # Create an image citation entry for the linked figure if we have a URL
                            if linked_image_url:
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
                                    "image_url": linked_image_url,
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
                            "linked_image_path": citation.get("linked_image_path"),
                            "is_image": True,
                            "is_linked_from_text": True,
                            "text_ref_id": ref_id,
                            # Ensure locationMetadata is included for frontend compatibility
                            "locationMetadata": safe_location_metadata,
                            "docId": citation.get("docId")
                        }
                        # Note: No image_url in basic version - frontend will need to handle path-to-URL conversion
                        extracted_citations.append(image_citation)
                    
        return extracted_citations

    async def _generate_image_url(self, blob_path: str) -> str:
        """Generate a signed URL for an image blob path."""
        from handlers.citation_file_handler import CitationFilesHandler
        
        # Get blob service client for URL generation
        blob_service_client = getattr(self, '_blob_service_client', None)
        container_client = getattr(self, '_container_client', None)
        artifacts_container_client = getattr(self, '_artifacts_container_client', None)
        
        if not blob_service_client or not artifacts_container_client:
            raise Exception("Blob service client or artifacts container client not available for image URL generation")
        
        citation_handler = CitationFilesHandler(blob_service_client, container_client, artifacts_container_client)
        return await citation_handler._get_file_url(blob_path)

    async def _fetch_document_metadata(self, doc_id: str, reference: dict) -> dict:
        """Safely fetch document metadata with fallbacks, including linked image information."""
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
            logger.debug(f"Could not fetch metadata for document {doc_id}: {e}")
            
            # Try to extract metadata from the reference content itself
            try:
                if isinstance(reference, dict):
                    content = reference.get("content", {})
                    if isinstance(content, dict):
                        has_linked_image = (
                            content.get("source_figure_id") is not None or 
                            content.get("related_image_path") is not None
                        )
                        metadata["has_linked_image"] = has_linked_image
                        metadata.update({
                            "source_figure_id": content.get("source_figure_id"),
                            "related_image_path": content.get("related_image_path")
                        })
                        
                logger.debug(f"Using fallback metadata for document {doc_id}, has_linked_image: {metadata['has_linked_image']}")
                        
            except Exception as fallback_error:
                logger.debug(f"Could not extract fallback metadata: {fallback_error}")
        
        return metadata

    async def _get_document_with_retry(self, ref_id: str, max_retries: int = 2) -> Optional[dict]:
        """Get document with simple retry logic."""
        for attempt in range(max_retries + 1):
            try:
                return await self.search_client.get_document(ref_id)
            except Exception as e:
                if attempt < max_retries:
                    await asyncio.sleep(0.1)
                    continue
                else:
                    # Log at debug level to reduce noise
                    logger.debug(f"Failed to fetch document {ref_id}: {e}")
                    return None
        return None

    async def _get_text_citations(
        self, ref_ids: List[str], grounding_results: GroundingResults
    ) -> List[dict]:
        """Enhanced text citation extraction with metadata and linked image URL generation."""
        try:
            citations = []
            for ref_id in ref_ids:
                try:
                    document = await self._get_document_with_retry(ref_id)
                    
                    if document is None:
                        # Document fetch failed, skip this citation
                        logger.debug(f"Skipping citation for {ref_id} - document fetch failed")
                        continue
                        
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

    def _order_document_types(self, doc_types: List[str]) -> List[str]:
        """Ensure document types follow the preferred order: otq, nyp_columns, client_reviews, then others."""
        priority_order = ["otq", "nyp_columns", "client_reviews"]
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
