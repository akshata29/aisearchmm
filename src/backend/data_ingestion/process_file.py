import asyncio
import datetime
import os
import json
import uuid
from azure.ai.documentintelligence.aio import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import (
    AnalyzeResult,
    AnalyzeOutputOption,
    AnalyzeDocumentRequest,
    DocumentParagraph,
    DocumentContentFormat,
)
from azure.ai.inference.aio import EmbeddingsClient, ImageEmbeddingsClient
from azure.ai.inference.models import ImageEmbeddingInput
from azure.core.exceptions import ResourceNotFoundError, HttpResponseError
from instructor import AsyncInstructor
from azure.search.documents.aio import SearchClient
from azure.search.documents.indexes.aio import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SimpleField,
    SearchableField,
    ComplexField,
    SearchFieldDataType,
    CorsOptions,
    VectorSearch,
    VectorSearchProfile,
    HnswAlgorithmConfiguration,
    VectorSearchAlgorithmKind,
    SemanticSearch,
    SemanticConfiguration,
    SemanticPrioritizedFields,
    SemanticField,
    AzureMachineLearningVectorizer,
    AzureMachineLearningParameters,
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
from azure.storage.blob.aio import BlobServiceClient
from utils.helpers import get_blob_as_base64
from collections import defaultdict


class ProcessFile:
    def __init__(
        self,
        document_client: DocumentIntelligenceClient,
        text_model: EmbeddingsClient,
        image_model: ImageEmbeddingsClient,
        search_client: SearchClient,
        index_client: SearchIndexClient,
        instructor_openai_client: AsyncInstructor,
        blob_service_client: BlobServiceClient,
        chatcompletions_model_name: str,
        progress_callback=None,
    ) -> None:
        # Core clients
        self.document_client = document_client
        self.text_model = text_model
        self.image_model = image_model
        self.search_client = search_client
        self.index_client = index_client
        self.instructor_openai_client = instructor_openai_client
        self.blob_service_client = blob_service_client

        # Settings
        self.chatcompletions_model_name = chatcompletions_model_name
        self.progress_cb = progress_callback

        # Storage containers
        self.container_client = self.blob_service_client.get_container_client(
            os.environ["ARTIFACTS_STORAGE_CONTAINER"]
        )
        self.sample_container_client = self.blob_service_client.get_container_client(
            os.environ["SAMPLES_STORAGE_CONTAINER"]
        )

    def _prepare_metadata(self, published_date: str = None, document_type: str = None):
        """Prepare metadata for document indexing with validation and defaults."""
        metadata = {}
        
        # Handle published_date
        if published_date:
            try:
                # Try to parse as ISO format first
                if 'T' in published_date:
                    parsed_date = datetime.datetime.fromisoformat(published_date.replace('Z', '+00:00'))
                else:
                    # Try parsing as date only (YYYY-MM-DD)
                    parsed_date = datetime.datetime.strptime(published_date, '%Y-%m-%d')
                metadata["published_date"] = parsed_date.isoformat() + 'Z'
            except (ValueError, TypeError) as e:
                print(f"Warning: Invalid published_date format '{published_date}', using current date. Error: {e}")
                metadata["published_date"] = datetime.datetime.utcnow().isoformat() + 'Z'
        else:
            # Default to current date if not provided
            metadata["published_date"] = datetime.datetime.utcnow().isoformat() + 'Z'
        
        # Handle document_type with validation
        if document_type:
            # Normalize and validate document type
            valid_types = {
                "quarterly report", "newsletter", "articles", "annual report", 
                "financial statement", "presentation", "whitepaper", "research report", 
                "policy document", "manual", "guide", "other"
            }
            normalized_type = document_type.lower().strip()
            if normalized_type in valid_types:
                metadata["document_type"] = normalized_type
            else:
                print(f"Warning: Unknown document_type '{document_type}', using 'other'")
                metadata["document_type"] = "other"
        else:
            # Default to 'other' if not provided
            print("Warning: document_type not provided, using 'other'")
            metadata["document_type"] = "other"
            
        return metadata

    async def process_file(
        self,
        file_bytes: bytes,
        file_name: str,
        index_name: str,
        published_date: str = None,
        document_type: str = None,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        output_format: str = "markdown",  # "markdown" or "text"
    ):
        # Prepare and validate metadata
        document_metadata = self._prepare_metadata(published_date, document_type)
        print(f"Processing file '{file_name}' with metadata: {document_metadata}")
        print(f"Chunking settings: size={chunk_size}, overlap={chunk_overlap}, format={output_format}")
        
        try:
            await self.sample_container_client.create_container()
        except Exception as e:
            print(f"Error creating samples container: {e}")
        try:
            await self.container_client.create_container()
        except Exception as e:
            print(f"Error creating knowledgeStore container: {e}")
        
        try:
            # Schema aligned with data_model.py and indexer_img_verbalize_strategy.py
            fields = [
                SearchableField(name="content_id", type=SearchFieldDataType.String, key=True, analyzer_name="keyword"),
                SimpleField(name="text_document_id", type=SearchFieldDataType.String, searchable=False, filterable=True, hidden=False, sortable=False, facetable=False),
                SimpleField(name="image_document_id", type=SearchFieldDataType.String, searchable=False, filterable=True, hidden=False, sortable=False, facetable=False),
                SearchableField(name="document_title", type=SearchFieldDataType.String, searchable=True, filterable=True, hidden=False, sortable=True, facetable=True),
                SearchableField(name="content_text", type=SearchFieldDataType.String, searchable=True, filterable=True, hidden=False, sortable=True, facetable=True),
                SearchField(name="content_embedding", type=SearchFieldDataType.Collection(SearchFieldDataType.Single), vector_search_dimensions=1536, searchable=True, vector_search_profile_name="hnsw"),
                SimpleField(name="content_path", type=SearchFieldDataType.String, searchable=False, filterable=True, hidden=False, sortable=False, facetable=False),
                # New metadata fields
                SimpleField(name="published_date", type=SearchFieldDataType.DateTimeOffset, searchable=False, filterable=True, sortable=True, facetable=True),
                SearchableField(name="document_type", type=SearchFieldDataType.String, searchable=True, filterable=True, sortable=True, facetable=True),
                ComplexField(name="locationMetadata", fields=[
                    SimpleField(name="pageNumber", type=SearchFieldDataType.Int32, searchable=False, filterable=True, hidden=False, sortable=True, facetable=True),
                    SimpleField(name="boundingPolygons", type=SearchFieldDataType.String, searchable=False, hidden=False, filterable=False, sortable=False, facetable=False)
                ])
            ]

            vector_search = VectorSearch(
                algorithms=[
                    HnswAlgorithmConfiguration(
                        name="hnsw-config",
                        kind="hnsw",
                        parameters={"m": 4, "efConstruction": 400, "metric": "cosine"},
                    )
                ],
                profiles=[
                    VectorSearchProfile(
                        name="hnsw",
                        algorithm_configuration_name="hnsw-config",
                    )
                ],
            )

            semantic_search = SemanticSearch(
                default_configuration_name="semantic-config",
                configurations=[
                    SemanticConfiguration(
                        name="semantic-config",
                        prioritized_fields=SemanticPrioritizedFields(
                            title_field=SemanticField(field_name="document_title"),
                            content_fields=[SemanticField(field_name="content_text")],
                        ),
                    )
                ],
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

            cors_options = CorsOptions(allowed_origins=["*"], max_age_in_seconds=60)
            search_index = SearchIndex(
                name=index_name, 
                fields=fields, 
                cors_options=cors_options, 
                vector_search=vector_search, 
                semantic_search=semantic_search,
                scoring_profiles=scoring_profiles,
                default_scoring_profile="freshness_and_type_boost"  # Set default scoring profile
            )

            # Ensure index schema exists and is up to date
            await self._ensure_index_exists(index_name, search_index)
        except Exception as e:
            print(f"Error creating index: {e}")
        ext = file_name.split(".")[-1].lower()
        if ext == "pdf":
            await self._process_pdf(file_bytes, file_name, index_name, published_date, document_type, chunk_size, chunk_overlap, output_format)
        else:
            print(f"Unsupported file type: {file_name}")

    async def _process_pdf(self, file_bytes: bytes, file_name: str, index_name: str, published_date: str = None, document_type: str = None, chunk_size: int = 500, chunk_overlap: int = 50, output_format: str = "markdown"):
        """Processes PDF documents for text, layout, and image embeddings."""
        
        # Prepare and validate metadata for this document
        document_metadata = self._prepare_metadata(published_date, document_type)
        print(f"Processing PDF '{file_name}' with metadata: {document_metadata}")

        await self.sample_container_client.upload_blob(file_name, file_bytes, overwrite=True)

        paragraphs, images, formatted_content = await self.analyze_document(file_bytes, file_name, output_format)

        documents = []

        page_dict = defaultdict(list)
        for paragraph in paragraphs:
            for region in paragraph.bounding_regions:
                page_dict[region["pageNumber"]].append(paragraph)

        # Report total pages available
        if self.progress_cb:
            try:
                total_pages = len(page_dict.keys())
                self.progress_cb(
                    step="content_extraction",
                    message=f"Starting content extraction across {total_pages} pages...",
                    progress=None,
                    increments={"total_pages": total_pages},
                )
            except Exception:
                pass

        # Process formatted content once for entire document or fall back to page-by-page processing
        if formatted_content:
            print(f"Processing entire document with native Document Intelligence formatting.")
            # Process the entire formatted content at once with document-level chunking
            all_text_chunks, all_text_metadata = self._chunk_document_formatted_content(
                formatted_content, paragraphs, chunk_size, chunk_overlap, output_format
            )
            
            if all_text_chunks:
                print(f"Extracted {len(all_text_chunks)} text chunks from formatted content.")
                text_embeddings_response = await self.text_model.embed(input=all_text_chunks)
                text_embeddings = text_embeddings_response.data

                for idx, chunk in enumerate(all_text_chunks):
                    document_id = str(uuid.uuid4())
                    chunk_metadata = all_text_metadata[idx] if idx < len(all_text_metadata) else {}
                    
                    documents.append({
                        "content_id": document_id,
                        "text_document_id": str(uuid.uuid4()),
                        "content_text": chunk,
                        "text_vector": text_embeddings[idx].embedding,
                        "document_title": file_name,
                        "content_path": f"{file_name}#page{chunk_metadata.get('pageNumber', 1)}",
                        "published_date": document_metadata.get("published_date"),
                        "document_type": document_metadata.get("document_type"),
                        "locationMetadata": chunk_metadata
                    })
        else:
            # Fallback to page-by-page processing using paragraphs
            print(f"Using fallback page-by-page processing.")
            for page_number, paras in list(page_dict.items()):
                print(f"Processing page {page_number} of {file_name}.")
                
                text_chunks, text_metadata = self._chunk_text_with_metadata(
                    page_number, paras, chunk_size, chunk_overlap, output_format
                )

                print(f"Extracted {len(text_chunks)} text chunks from page {page_number}.")
                if text_chunks:
                    text_embeddings_response = await self.text_model.embed(input=text_chunks)
                    text_embeddings = text_embeddings_response.data

                    for idx, chunk in enumerate(text_chunks):
                        document_id = str(uuid.uuid4())
                        chunk_metadata = text_metadata[idx] if idx < len(text_metadata) else {}
                        
                        documents.append({
                            "content_id": str(uuid.uuid4()),
                            "text_document_id": document_id,
                            "image_document_id": None,
                            "document_title": file_name,
                            "content_text": chunk,
                            "text_vector": text_embeddings[idx].embedding,
                            "content_path": f"{file_name}#page{page_number}",
                            "published_date": document_metadata["published_date"],
                            "document_type": document_metadata["document_type"],
                            "locationMetadata": chunk_metadata
                        })

                # Progress tick
                if self.progress_cb:
                    try:
                        self.progress_cb(
                            step="content_extraction",
                            message=f"Processed {len(text_chunks) if text_chunks else 0} text chunks on page {page_number}.",
                            progress=None,
                            increments={"pages_processed": 1, "chunks_created": len(text_chunks) if text_chunks else 0},
                        )
                    except Exception:
                        pass

        # Process images for all pages (works for both formatted and paragraph-based processing)
        for page_number, paras in list(page_dict.items()):

            associated_images = [img for img in images if img.get("page_number") == page_number]

            for img in associated_images:
                print(f"Processing image {img['blob_name']} on page {page_number}.")

                blob_name = img["blob_name"]
                blob_client = self.container_client.get_blob_client(blob_name)
                image_base64 = await get_blob_as_base64(blob_client)
                
                # Generate content embedding for the image description
                image_description = f"Image from page {img['page_number']} of {file_name}"
                try:
                    img_text_embedding_response = await self.text_model.embed(input=[image_description])
                    image_content_embedding = img_text_embedding_response.data[0].embedding
                except Exception as e:
                    print(f"Failed to generate embedding for image description: {e}")
                    continue
                
                # Omit image_vector to avoid dimension mismatch unless configured properly
                documents.append({
                    "content_id": str(uuid.uuid4()),
                    "text_document_id": None,
                    "image_document_id": document_id,
                    "document_title": file_name,
                    "content_text": image_description,
                    "text_vector": image_content_embedding,
                    "content_path": blob_name,
                    "published_date": document_metadata["published_date"],
                    "document_type": document_metadata["document_type"],
                    "locationMetadata": {
                        "pageNumber": img["page_number"],
                        "boundingPolygons": json.dumps([img["boundingPolygons"]]),
                    }
                })
                await self._check_and_index_documents(documents, file_name, index_name)

            # Report image/figure counts for this page
            if associated_images and self.progress_cb:
                try:
                    self.progress_cb(
                        step="image_processing",
                        message=f"Processed {len(associated_images)} images on page {page_number}.",
                        progress=None,
                        increments={"images_extracted": len(associated_images), "figures_processed": len(associated_images)},
                    )
                except Exception:
                    pass

        if documents:
            print(f"Indexing remaining documents for {file_name} with {len(documents)} documents.")
            await self._index_documents(index_name, documents)
            documents.clear()

        # Final progress tick
        if self.progress_cb:
            try:
                self.progress_cb(step="indexing_complete", message="Indexing complete.", progress=100, increments={})
            except Exception:
                pass

    async def analyze_document(self, file_bytes, file_name, output_format: str = "markdown"):
        print(f"Analyzing document {file_name} with output format: {output_format}.")

        # Map our output format to Document Intelligence enum
        content_format = DocumentContentFormat.MARKDOWN if output_format.lower() == "markdown" else DocumentContentFormat.TEXT

        try:
            poller = await self.document_client.begin_analyze_document(
                "prebuilt-layout",
                body=AnalyzeDocumentRequest(bytes_source=file_bytes),
                output=[AnalyzeOutputOption.FIGURES],
                output_content_format=content_format,  # Use native Document Intelligence content format
            )

        except HttpResponseError as e:
            print(f"Error analyzing document {file_name}: {e}")
            return [], [], None

        result: AnalyzeResult = await poller.result()

        print(f"Extracting text and images from {file_name}.")

        images = await self._extract_figures(
            file_name, result, poller.details["operation_id"]
        )

        # Emit initial progress for analysis
        if self.progress_cb:
            try:
                self.progress_cb(
                    step="document_analysis",
                    message=f"Detected {len(result.paragraphs or [])} paragraphs and {len(images)} figures. Content format: {content_format}",
                    progress=None,
                    increments={}
                )
            except Exception:
                pass
        return result.paragraphs or [], images, result.content

    async def _check_and_index_documents(self, documents, file_name, index_name):
        """Checks if documents collection has reached 100 elements and indexes if needed."""
        if len(documents) == 10:
            print(f"Indexing document {file_name} with {len(documents)} chunks.")
            await self._index_documents(index_name, documents)
            documents.clear()

    async def _extract_figures(self, file_name, result, result_id):
        """Extracts figures and their metadata from the analyzed result."""

        blob_folder = os.path.join(
            os.environ["SEARCH_INDEX_NAME"],
            datetime.datetime.now().strftime("%Y%m%d%H%M%S"),
        )

        images_info = []
        total_figures = len(result.figures or [])
        for i, figure in enumerate(result.figures or [], 1):
            print(f"Processing figure {i} of {total_figures}")
            try:
                response = await self.document_client.get_analyze_result_figure(
                    model_id=result.model_id, result_id=result_id, figure_id=figure.id
                )
                file_name = f"figure_{figure.id}.png"
                blob_name = f"{blob_folder}/{file_name}"

                image_data = b""
                async for chunk in response:
                    image_data += chunk

                await self.container_client.upload_blob(
                    name=blob_name, data=image_data, overwrite=True
                )

                info = {
                    "blob_name": blob_name,
                    "page_number": figure.bounding_regions[0].page_number,
                    "boundingPolygons": self._format_polygon(
                        figure.bounding_regions[0].polygon
                    ),
                }

                print(f"Processed image {blob_name}")
                images_info.append(info)
            except ResourceNotFoundError as e:
                print(f"Figure {figure.id} not found: {e}")
                continue
        return images_info

    async def _get_image_embedding(self, image_base64: str):
        """Generates image embeddings."""
        # Note: Azure OpenAI text embedding models don't support image inputs
        # For now, we'll create a dummy embedding or skip image embeddings
        # In a real implementation, you'd use a proper image embedding model
        response = await self.image_model.embed(
            input=[f"Image content from document figure"]  # Placeholder text
        )
        return response.data[0].embedding

    def _chunk_document_formatted_content(
        self, formatted_content: str, all_paragraphs: list[DocumentParagraph], 
        max_tokens: int = 500, overlap: int = 50, output_format: str = "markdown"
    ):
        """Chunks the entire document's native Document Intelligence formatted content."""
        
        chunks, metadata = [], []
        
        # Split formatted content into tokens for chunking
        all_tokens = formatted_content.split()
        
        i = 0
        while i < len(all_tokens):
            chunk_tokens = []
            
            # Build chunk up to max_tokens
            while i < len(all_tokens) and len(chunk_tokens) < max_tokens:
                chunk_tokens.append(all_tokens[i])
                i += 1
            
            # If we're not at the end, backtrack for overlap
            if i < len(all_tokens):
                overlap_start = max(0, len(chunk_tokens) - overlap)
                i -= (len(chunk_tokens) - overlap_start)
            
            # Join tokens back to text
            chunk_text = " ".join(chunk_tokens)
            
            if chunk_text.strip():
                # Determine the most likely page for this chunk based on content
                page_number = self._estimate_page_for_chunk(chunk_text, all_paragraphs)
                
                # Collect bounding regions for this chunk (approximate mapping)
                chunk_bounding_regions = []
                relevant_paragraphs = self._get_relevant_paragraphs_for_chunk(all_paragraphs, chunk_text)
                for para in relevant_paragraphs:
                    if para.bounding_regions:
                        for region in para.bounding_regions:
                            chunk_bounding_regions.append(self._format_polygon(region.polygon))
                
                chunks.append(chunk_text.strip())
                metadata.append({
                    "pageNumber": page_number,
                    "boundingPolygons": json.dumps(chunk_bounding_regions)
                })

        return chunks, metadata

    def _estimate_page_for_chunk(self, chunk_text: str, all_paragraphs: list[DocumentParagraph]) -> int:
        """Estimate which page a chunk belongs to based on paragraph content matching."""
        chunk_words = set(chunk_text.lower().split())
        page_scores = {}
        
        for para in all_paragraphs:
            if para.bounding_regions:
                for region in para.bounding_regions:
                    page_num = region.get("pageNumber", 1)
                    if page_num not in page_scores:
                        page_scores[page_num] = 0
                    
                    # Score based on word overlap
                    para_words = set(para.content.lower().split())
                    overlap = len(chunk_words.intersection(para_words))
                    page_scores[page_num] += overlap
        
        # Return the page with the highest score, default to 1 if no matches
        return max(page_scores.items(), key=lambda x: x[1])[0] if page_scores else 1

    def _get_relevant_paragraphs_for_chunk(self, paragraphs: list[DocumentParagraph], chunk_text: str):
        """Find paragraphs that are most relevant to a given chunk of text."""
        relevant_paragraphs = []
        
        # Simple approach: find paragraphs that share content with the chunk
        chunk_words = set(chunk_text.lower().split())
        
        for para in paragraphs:
            para_words = set(para.content.lower().split())
            # If there's significant word overlap, consider this paragraph relevant
            overlap = len(chunk_words.intersection(para_words))
            if overlap > min(3, len(para_words) // 2):  # At least 3 words or half the paragraph
                relevant_paragraphs.append(para)
        
        return relevant_paragraphs[:5]  # Limit to most relevant paragraphs

    def _chunk_formatted_content_with_metadata(
        self, page_number, formatted_content: str, paragraphs: list[DocumentParagraph], 
        max_tokens: int = 500, overlap: int = 50, output_format: str = "markdown"
    ):
        """Chunks the native Document Intelligence formatted content with metadata."""
        
        chunks, metadata = [], []
        
        # Split formatted content into tokens for chunking
        all_tokens = formatted_content.split()
        
        i = 0
        while i < len(all_tokens):
            chunk_tokens = []
            
            # Build chunk up to max_tokens
            while i < len(all_tokens) and len(chunk_tokens) < max_tokens:
                chunk_tokens.append(all_tokens[i])
                i += 1
            
            # If we're not at the end, backtrack for overlap
            if i < len(all_tokens):
                overlap_start = max(0, len(chunk_tokens) - overlap)
                i -= (len(chunk_tokens) - overlap_start)
            
            # Join tokens back to text
            chunk_text = " ".join(chunk_tokens)
            
            if chunk_text.strip():
                # Collect bounding regions for this chunk (approximate mapping)
                chunk_bounding_regions = []
                relevant_paragraphs = self._get_relevant_paragraphs_for_chunk(paragraphs, chunk_text)
                for para in relevant_paragraphs:
                    if para.bounding_regions:
                        for region in para.bounding_regions:
                            chunk_bounding_regions.append(self._format_polygon(region.polygon))
                
                chunks.append(chunk_text.strip())
                metadata.append({
                    "pageNumber": page_number,
                    "boundingPolygons": json.dumps(chunk_bounding_regions)
                })

        return chunks, metadata

    def _chunk_text_with_metadata(
        self, page_number, paragraphs: list[DocumentParagraph], max_tokens: int = 500, overlap: int = 50, output_format: str = "markdown"
    ):
        """Fallback chunking method using paragraph-based processing."""

        chunks, metadata = [], []
        
        # Convert paragraphs to structured content based on output format preference
        if output_format.lower() == "markdown":
            structured_content = self._convert_to_markdown(paragraphs)
        else:
            structured_content = self._convert_to_text(paragraphs)

        # Split structured content into tokens for chunking
        all_tokens = structured_content.split()
        
        i = 0
        while i < len(all_tokens):
            chunk_tokens = []
            
            # Build chunk up to max_tokens
            while i < len(all_tokens) and len(chunk_tokens) < max_tokens:
                chunk_tokens.append(all_tokens[i])
                i += 1
            
            # If we're not at the end, backtrack for overlap
            if i < len(all_tokens):
                overlap_start = max(0, len(chunk_tokens) - overlap)
                i -= (len(chunk_tokens) - overlap_start)
            
            # Join tokens back to text
            chunk_text = " ".join(chunk_tokens)
            
            if chunk_text.strip():
                # Collect bounding regions for this chunk
                relevant_paragraphs = self._get_relevant_paragraphs_for_chunk(paragraphs, chunk_text)
                chunk_bounding_regions = []
                for para in relevant_paragraphs:
                    if para.bounding_regions:
                        for region in para.bounding_regions:
                            chunk_bounding_regions.append(self._format_polygon(region.polygon))
                
                chunks.append(chunk_text.strip())
                metadata.append({
                    "pageNumber": page_number,
                    "boundingPolygons": json.dumps(chunk_bounding_regions)
                })

        return chunks, metadata

    def _convert_to_structured_content(self, paragraphs: list[DocumentParagraph], output_format: str) -> str:
        """Convert Document Intelligence paragraphs to structured content (markdown or text)."""
        if output_format.lower() == "markdown":
            return self._convert_to_markdown(paragraphs)
        else:
            return self._convert_to_text(paragraphs)
    
    def _convert_to_markdown(self, paragraphs: list[DocumentParagraph]) -> str:
        """Convert paragraphs to markdown format using Document Intelligence role detection."""
        markdown_content = []
        
        for paragraph in paragraphs or []:
            content = paragraph.content.strip()
            if not content:
                continue
                
            # Use Document Intelligence role detection for better markdown formatting
            role = getattr(paragraph, 'role', None)
            
            if role == "title":
                # Main title
                markdown_content.append(f"# {content}\n")
            elif role == "sectionHeading":
                # Section heading
                markdown_content.append(f"## {content}\n")
            elif role == "footnote":
                # Footnote
                markdown_content.append(f"> {content}\n")
            elif role == "pageNumber":
                # Skip page numbers in content
                continue
            elif role == "pageHeader" or role == "pageFooter":
                # Headers/footers as italic
                markdown_content.append(f"*{content}*\n")
            else:
                # Regular paragraph content
                # Detect if it looks like a list item
                if content.startswith(('•', '-', '*', '1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.')):
                    markdown_content.append(f"- {content.lstrip('•-* ')}\n")
                else:
                    markdown_content.append(f"{content}\n\n")
        
        return "".join(markdown_content).strip()
    
    def _convert_to_text(self, paragraphs: list[DocumentParagraph]) -> str:
        """Convert paragraphs to plain text format."""
        text_content = []
        
        for paragraph in paragraphs or []:
            content = paragraph.content.strip()
            if content:
                # Skip page numbers and headers/footers for cleaner text
                role = getattr(paragraph, 'role', None)
                if role not in ["pageNumber", "pageHeader", "pageFooter"]:
                    text_content.append(content)
        
        return " ".join(text_content)
    
    def _get_relevant_paragraphs_for_chunk(self, paragraphs: list[DocumentParagraph], chunk_text: str) -> list[DocumentParagraph]:
        """Find paragraphs that are most relevant to the current chunk (simplified approach)."""
        relevant = []
        chunk_words = set(chunk_text.lower().split())
        
        for paragraph in paragraphs or []:
            para_words = set(paragraph.content.lower().split())
            # If there's significant overlap, consider it relevant
            overlap = len(chunk_words.intersection(para_words))
            if overlap > min(3, len(para_words) * 0.3):  # At least 3 words or 30% overlap
                relevant.append(paragraph)
        
        return relevant

    def _format_polygon(self, polygon):
        """Formats polygon coordinates."""
        return [
            {"x": polygon[i], "y": polygon[i + 1]} for i in range(0, len(polygon), 2)
        ]

    async def _index_documents(self, index_name, documents):
        """Indexes documents into Azure Cognitive Search."""
        try:
            # Fetch current index fields and drop unknown properties to avoid 400s
            try:
                current_index = await self.index_client.get_index(index_name)
                allowed_fields = {f.name for f in (current_index.fields or [])}
                filtered = []
                for doc in documents:
                    unknown = set(doc.keys()) - allowed_fields
                    if unknown:
                        # Keep nested complex objects if root name exists (e.g., locationMetadata)
                        safe_doc = {k: v for k, v in doc.items() if k in allowed_fields}
                        filtered.append(safe_doc)
                        print(f"Dropping unknown fields for index '{index_name}': {sorted(list(unknown))}")
                    else:
                        filtered.append(doc)
                documents = filtered
            except Exception as e:
                # If index is missing, ensure and continue
                missing = isinstance(e, ResourceNotFoundError) or (hasattr(e, 'message') and 'not found' in str(e).lower())
                if missing:
                    # Rebuild the desired schema and ensure index exists
                    desired = await self._build_index_schema(index_name)
                    await self._ensure_index_exists(index_name, desired)
                else:
                    print(f"Warning: could not fetch index schema before indexing: {e}")

            # Validate JSON before sending
            try:
                json.dumps(documents)
            except json.JSONDecodeError as e:
                print(f"Invalid JSON in documents: {e}")
                return

            try:
                await self.search_client.upload_documents(documents=documents)
                print(f"Indexed {len(documents)} documents.")
            except Exception as e:
                # Retry once if index missing
                missing = isinstance(e, ResourceNotFoundError) or (hasattr(e, 'message') and 'not found' in str(e).lower())
                if missing:
                    desired = await self._build_index_schema(index_name)
                    await self._ensure_index_exists(index_name, desired)
                    await self.search_client.upload_documents(documents=documents)
                    print(f"Indexed {len(documents)} documents after recreating index.")
                else:
                    raise
        except Exception as e:
            print(f"Error indexing documents: {e}")

    async def _build_index_schema(self, index_name: str) -> SearchIndex:
        """Rebuilds the desired SearchIndex schema matching data_model.py and indexer strategy."""
        fields = [
            SearchableField(name="content_id", type=SearchFieldDataType.String, key=True, analyzer_name="keyword"),
            SimpleField(name="text_document_id", type=SearchFieldDataType.String, searchable=False, filterable=True, hidden=False, sortable=False, facetable=False),
            SimpleField(name="image_document_id", type=SearchFieldDataType.String, searchable=False, filterable=True, hidden=False, sortable=False, facetable=False),
            SearchableField(name="document_title", type=SearchFieldDataType.String, searchable=True, filterable=True, hidden=False, sortable=True, facetable=True),
            SearchableField(name="content_text", type=SearchFieldDataType.String, searchable=True, filterable=True, hidden=False, sortable=True, facetable=True),
            SearchField(name="content_embedding", type=SearchFieldDataType.Collection(SearchFieldDataType.Single), vector_search_dimensions=1536, searchable=True, vector_search_profile_name="hnsw"),
            SimpleField(name="content_path", type=SearchFieldDataType.String, searchable=False, filterable=True, hidden=False, sortable=False, facetable=False),
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
                VectorSearchProfile(name="hnsw", algorithm_configuration_name="hnsw-config")
            ],
            algorithms=[
                HnswAlgorithmConfiguration(
                    name="hnsw-config",
                    kind=VectorSearchAlgorithmKind.HNSW,
                    parameters={"m": 4, "efConstruction": 400, "efSearch": 500, "metric": "cosine"}
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
            ],
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

        cors_options = CorsOptions(allowed_origins=["*"], max_age_in_seconds=60)
        return SearchIndex(
            name=index_name,
            fields=fields,
            cors_options=cors_options,
            vector_search=vector_search,
            semantic_search=semantic_search,
            scoring_profiles=scoring_profiles,
            default_scoring_profile="freshness_and_type_boost"  # Set default scoring profile
        )

    async def _ensure_index_exists(self, index_name: str, desired: SearchIndex):
        """Ensures the index exists with the desired schema; recreates if fields are missing."""
        try:
            existing = await self.index_client.get_index(index_name)
            existing_fields = {f.name for f in existing.fields or []}
            desired_fields = {f.name for f in desired.fields or []}
            # If any desired field is missing, recreate index to avoid schema mismatch
            if not desired_fields.issubset(existing_fields):
                try:
                    await self.index_client.delete_index(index_name)
                except Exception:
                    pass
                await self.index_client.create_index(desired)
                print(f"Index {index_name} recreated with expected schema")
            else:
                await self.index_client.create_or_update_index(desired)
                print(f"Index {index_name} updated (no missing fields)")
        except Exception:
            # Not found or fetch failed; create fresh
            await self.index_client.create_index(desired)
            print(f"Index {index_name} created with expected schema")
