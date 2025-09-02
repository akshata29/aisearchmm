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
from openai import AsyncAzureOpenAI
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
        instructor_openai_client: AsyncAzureOpenAI,  # This is actually a regular OpenAI client now
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
                "quarterly_report", "newsletter", "articles", "annual_report", 
                "financial_statement", "presentation", "whitepaper", "research_report", 
                "policy_document", "manual", "guide", "client_reviews", "nyp_columns", 
                "otq", "other"
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
        chunking_strategy: str = "document_layout",  # "document_layout" or "custom"
    ):
        # Prepare and validate metadata
        document_metadata = self._prepare_metadata(published_date, document_type)
        print(f"Processing file '{file_name}' with metadata: {document_metadata}")
        print(f"Chunking strategy: {chunking_strategy}")
        if chunking_strategy == "custom":
            print(f"Custom chunking settings: size={chunk_size}, overlap={chunk_overlap}, format={output_format}")
        else:
            print(f"Document layout chunking: using semantic structure, format={output_format}")
        
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
                algorithms=[
                    HnswAlgorithmConfiguration(
                        name="hnsw-config",
                        kind="hnsw",
                        parameters={"m": 4, "efConstruction": 400, "metric": "cosine"},
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
                ],
                profiles=[
                    VectorSearchProfile(
                        name="hnsw",
                        algorithm_configuration_name="hnsw-config",
                        vectorizer_name="openai-vectorizer"
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
            await self._process_pdf(file_bytes, file_name, index_name, published_date, document_type, chunk_size, chunk_overlap, output_format, chunking_strategy)
        else:
            print(f"Unsupported file type: {file_name}")

    async def _process_pdf(self, file_bytes: bytes, file_name: str, index_name: str, published_date: str = None, document_type: str = None, chunk_size: int = 500, chunk_overlap: int = 50, output_format: str = "markdown", chunking_strategy: str = "document_layout"):
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

        # Choose processing approach based on chunking strategy
        if chunking_strategy == "document_layout":
            # Document Layout approach: Use Document Intelligence's semantic structure
            print(f"Using Document Layout approach for semantic chunking.")
            await self._process_with_document_layout(paragraphs, documents, file_name, document_metadata, page_dict, index_name, images)
        else:
            # Custom approach: Traditional token-based chunking (existing logic)
            print(f"Using Custom chunking approach.")
            await self._process_with_custom_chunking(paragraphs, formatted_content, documents, file_name, document_metadata, page_dict, chunk_size, chunk_overlap, output_format)

        # Process images for all pages (works for both formatted and paragraph-based processing)
        for page_number, paras in list(page_dict.items()):

            associated_images = [img for img in images if img.get("page_number") == page_number]

            # Create context from page content for better image descriptions
            page_context = ""
            if paras:
                # Get text content from this page to provide context for image verbalization
                page_texts = []
                for para in paras[:5]:  # Limit to first 5 paragraphs for context
                    if para.content and para.content.strip():
                        # Skip page numbers and headers/footers
                        role = getattr(para, 'role', None)
                        if role not in ["pageNumber", "pageHeader", "pageFooter"]:
                            page_texts.append(para.content.strip())
                
                page_context = " ".join(page_texts)[:1000]  # Limit context length

            for img in associated_images:
                print(f"Processing image {img['blob_name']} on page {page_number}.")

                blob_name = img["blob_name"]
                blob_client = self.container_client.get_blob_client(blob_name)
                image_base64 = await get_blob_as_base64(blob_client)
                
                # Generate detailed image description using chat completion model
                try:
                    if self.progress_cb:
                        try:
                            self.progress_cb(
                                step="image_verbalization",
                                message=f"Generating description for image on page {page_number}...",
                                progress=None,
                                increments={},
                            )
                        except Exception:
                            pass
                    
                    image_description = await self._verbalize_image(image_base64, page_context)
                    print(f"Generated image description: {image_description[:100]}...")
                except Exception as e:
                    print(f"Failed to generate image description: {e}")
                    image_description = f"Image from page {img['page_number']} of {file_name}"
                
                # Generate embedding for the verbalized description
                try:
                    img_text_embedding_response = await self.text_model.embed(input=[image_description])
                    image_content_embedding = img_text_embedding_response.data[0].embedding
                except Exception as e:
                    print(f"Failed to generate embedding for image description: {e}")
                    continue
                
                # Store both text and image content in the same content_embedding field
                documents.append({
                    "content_id": str(uuid.uuid4()),
                    "text_document_id": None,
                    "image_document_id": str(uuid.uuid4()),  # Fixed: use new UUID for image
                    "document_title": file_name,
                    "content_text": image_description,  # Now contains rich, verbalized description
                    "content_embedding": image_content_embedding,  # Embedding of the detailed description
                    "content_path": blob_name,
                    "source_figure_id": img.get("figure_id"),  # Link back to source figure
                    "related_image_path": blob_name,  # Self-reference for image content
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
                    "figure_id": figure.id,
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

    async def _process_with_document_layout(self, paragraphs, documents, file_name, document_metadata, page_dict, index_name, images=None):
        """
        Process documents using Document Intelligence's semantic structure.
        Each paragraph/section becomes its own searchable unit with precise location data.
        Links text content with related figures when detected.
        """
        total_paragraphs = len(paragraphs)
        processed_count = 0
        
        # Group paragraphs by semantic meaning and process each as a unit
        semantic_chunks = self._create_semantic_chunks(paragraphs)
        
        print(f"Created {len(semantic_chunks)} semantic chunks from {total_paragraphs} paragraphs.")
        
        if semantic_chunks:
            # Extract text content for embedding
            chunk_texts = [chunk["content"] for chunk in semantic_chunks]
            
            # Generate embeddings for all chunks at once
            text_embeddings_response = await self.text_model.embed(input=chunk_texts)
            text_embeddings = text_embeddings_response.data
            
            # Create documents for each semantic chunk
            for idx, chunk in enumerate(semantic_chunks):
                document_id = str(uuid.uuid4())
                
                # Check if this content is figure-related and get linked image info
                figure_info = self._find_related_figure(chunk, images or [])
                
                documents.append({
                    "content_id": document_id,
                    "text_document_id": str(uuid.uuid4()),
                    "image_document_id": None,
                    "document_title": file_name,
                    "content_text": chunk["content"],
                    "content_embedding": text_embeddings[idx].embedding,
                    "content_path": f"{file_name}#page{chunk['page_number']}#{chunk.get('element_type', 'content')}",
                    "source_figure_id": figure_info.get("figure_id") if figure_info else None,
                    "related_image_path": figure_info.get("blob_name") if figure_info else None,
                    "published_date": document_metadata["published_date"],
                    "document_type": document_metadata["document_type"],
                    "locationMetadata": {
                        "pageNumber": chunk["page_number"],
                        "boundingPolygons": json.dumps(chunk["bounding_polygons"])
                    }
                })
                
                processed_count += 1
                
                # Batch index documents
                if len(documents) >= 10:
                    await self._index_documents(index_name, documents)
                    documents.clear()
        
        # Report progress with correct keys for statistics
        if self.progress_cb:
            try:
                # Count unique pages represented in semantic chunks
                unique_pages = set()
                for chunk in semantic_chunks:
                    unique_pages.add(chunk["page_number"])
                
                self.progress_cb(
                    step="content_extraction",
                    message=f"Processed {processed_count} semantic chunks across {len(unique_pages)} pages using document layout structure.",
                    progress=None,
                    increments={"pages_processed": len(unique_pages), "chunks_created": processed_count},
                )
            except Exception:
                pass

    async def _process_with_custom_chunking(self, paragraphs, formatted_content, documents, file_name, document_metadata, page_dict, chunk_size, chunk_overlap, output_format):
        """
        Process documents using traditional token-based chunking (existing approach).
        """
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
                        "image_document_id": None,
                        "content_text": chunk,
                        "content_embedding": text_embeddings[idx].embedding,
                        "document_title": file_name,
                        "content_path": f"{file_name}#page{chunk_metadata.get('pageNumber', 1)}",
                        "source_figure_id": None,  # Not linking figures in custom chunking
                        "related_image_path": None,
                        "published_date": document_metadata.get("published_date"),
                        "document_type": document_metadata.get("document_type"),
                        "locationMetadata": chunk_metadata
                    })

                # Count unique pages for statistics reporting
                unique_pages = set()
                for metadata in all_text_metadata:
                    if metadata and "pageNumber" in metadata:
                        unique_pages.add(metadata["pageNumber"])

                # Report statistics for unified processing
                if self.progress_cb:
                    try:
                        self.progress_cb(
                            step="content_extraction",
                            message=f"Processed {len(all_text_chunks)} text chunks across {len(unique_pages)} pages.",
                            progress=None,
                            increments={"pages_processed": len(unique_pages), "chunks_created": len(all_text_chunks)},
                        )
                    except Exception:
                        pass
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
                            "content_embedding": text_embeddings[idx].embedding,
                            "content_path": f"{file_name}#page{page_number}",
                            "source_figure_id": None,  # Not linking figures in custom chunking
                            "related_image_path": None,
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

    def _create_semantic_chunks(self, paragraphs):
        """
        Create semantic chunks based on Document Intelligence's structure detection.
        Groups related paragraphs and preserves document hierarchy.
        """
        semantic_chunks = []
        current_section = None
        
        for paragraph in paragraphs:
            if not paragraph.content or not paragraph.content.strip():
                continue
                
            role = getattr(paragraph, 'role', None)
            content = paragraph.content.strip()
            
            # Extract bounding regions
            bounding_polygons = []
            page_number = 1
            
            if paragraph.bounding_regions:
                for region in paragraph.bounding_regions:
                    page_number = region.get("pageNumber", page_number)
                    if hasattr(region, 'polygon'):
                        bounding_polygons.append(self._format_polygon(region.polygon))
            
            # Skip page numbers, headers, and footers as standalone chunks
            if role in ["pageNumber", "pageHeader", "pageFooter"]:
                continue
            
            # Handle different document element types
            if role == "title":
                # Main title - standalone chunk
                semantic_chunks.append({
                    "content": content,
                    "element_type": "title",
                    "page_number": page_number,
                    "bounding_polygons": bounding_polygons,
                    "role": role
                })
                current_section = None
                
            elif role == "sectionHeading":
                # Section heading - start new section or standalone
                if current_section and current_section["content"]:
                    # Finish previous section
                    semantic_chunks.append(current_section)
                
                # Create new section or standalone heading
                semantic_chunks.append({
                    "content": content,
                    "element_type": "section_heading",
                    "page_number": page_number,
                    "bounding_polygons": bounding_polygons,
                    "role": role
                })
                current_section = None
                
            elif role in ["footnote", "formula"]:
                # Special elements - standalone chunks
                semantic_chunks.append({
                    "content": content,
                    "element_type": role,
                    "page_number": page_number,
                    "bounding_polygons": bounding_polygons,
                    "role": role
                })
                
            else:
                # Regular paragraph - group with similar content
                if not current_section:
                    current_section = {
                        "content": content,
                        "element_type": "paragraph_group",
                        "page_number": page_number,
                        "bounding_polygons": bounding_polygons.copy(),
                        "role": "paragraph"
                    }
                else:
                    # Add to current section if on same page and content is related
                    if (page_number == current_section["page_number"] and 
                        len(current_section["content"]) < 1500):  # Keep sections reasonable size
                        current_section["content"] += f"\n\n{content}"
                        current_section["bounding_polygons"].extend(bounding_polygons)
                    else:
                        # Finish current section and start new one
                        semantic_chunks.append(current_section)
                        current_section = {
                            "content": content,
                            "element_type": "paragraph_group",
                            "page_number": page_number,
                            "bounding_polygons": bounding_polygons.copy(),
                            "role": "paragraph"
                        }
        
        # Don't forget the last section
        if current_section and current_section["content"]:
            semantic_chunks.append(current_section)
        
        return semantic_chunks

    async def _verbalize_image(self, image_base64: str, page_context: str = "") -> str:
        """
        Generate a detailed description of an image using a chat completion model.
        This follows the Microsoft documentation approach for image verbalization.
        """
        try:
            # Create a prompt for image verbalization with optional page context
            context_prompt = f"\n\nContext from the document page: {page_context}" if page_context.strip() else ""
            
            prompt = f"""You are an AI assistant that analyzes images from documents to create detailed, searchable descriptions.

Please provide a comprehensive description of this image that includes:
1. What type of visual element this is (chart, diagram, photo, table, etc.)
2. Key visual elements, text, or data visible in the image
3. The purpose or function this image serves in the document
4. Any relationships between elements shown
5. Important details that would help someone search for this content

Make your description detailed but concise, focusing on information that would be useful for document search and retrieval.{context_prompt}

Provide only the description without any preamble or explanation."""

            # Use the OpenAI client directly for image description (not instructor)
            response = await self.instructor_openai_client.chat.completions.create(
                model=self.chatcompletions_model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{image_base64}"}
                            }
                        ]
                    }
                ],
                max_tokens=500,
                temperature=0.1
            )
            
            description = response.choices[0].message.content.strip()
            return description if description else "Image from document (description unavailable)"
            
        except Exception as e:
            print(f"Failed to verbalize image: {e}")
            return "Image from document (description unavailable)"

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
        """Find paragraphs that are most relevant to the current chunk with improved precision."""
        relevant = []
        chunk_text_lower = chunk_text.lower()
        
        # First, try to find paragraphs that contain substantial portions of the chunk text
        for paragraph in paragraphs or []:
            para_content = paragraph.content.strip().lower()
            if not para_content:
                continue
                
            # Calculate how much of the paragraph content appears in the chunk
            para_words = para_content.split()
            if len(para_words) < 3:  # Skip very short paragraphs
                continue
                
            # Check if significant portions of the paragraph appear in the chunk
            # Use sliding window to find the longest matching subsequence
            max_consecutive_matches = 0
            current_consecutive = 0
            
            for word in para_words:
                if word in chunk_text_lower:
                    current_consecutive += 1
                    max_consecutive_matches = max(max_consecutive_matches, current_consecutive)
                else:
                    current_consecutive = 0
            
            # Consider relevant if at least 50% of paragraph words match consecutively
            # or if it's a short paragraph with high overlap
            if (max_consecutive_matches >= len(para_words) * 0.5 or 
                (len(para_words) <= 10 and max_consecutive_matches >= len(para_words) * 0.7)):
                relevant.append(paragraph)
        
        # If no paragraphs found with the strict method, fall back to the original but with higher threshold
        if not relevant:
            chunk_words = set(chunk_text_lower.split())
            for paragraph in paragraphs or []:
                para_words = set(paragraph.content.lower().split())
                if len(para_words) < 3:
                    continue
                    
                # Use much higher threshold for word overlap
                overlap = len(chunk_words.intersection(para_words))
                overlap_ratio = overlap / len(para_words)
                if overlap >= 5 and overlap_ratio >= 0.6:  # At least 5 words AND 60% overlap
                    relevant.append(paragraph)
        
        # Limit the number of paragraphs to prevent massive highlighting
        # Sort by relevance and take top 3
        if len(relevant) > 3:
            # Simple relevance scoring based on content length and overlap
            scored_paragraphs = []
            chunk_words = set(chunk_text_lower.split())
            
            for para in relevant:
                para_words = set(para.content.lower().split())
                overlap = len(chunk_words.intersection(para_words))
                # Score based on overlap ratio and paragraph length (prefer more specific matches)
                score = (overlap / len(para_words)) * (1.0 / max(1, len(para_words) / 20))  # Favor shorter, more specific paragraphs
                scored_paragraphs.append((score, para))
            
            # Sort by score and take top 3
            scored_paragraphs.sort(key=lambda x: x[0], reverse=True)
            relevant = [para for _, para in scored_paragraphs[:3]]
        
        return relevant

    def _format_polygon(self, polygon):
        """Formats polygon coordinates."""
        return [
            {"x": polygon[i], "y": polygon[i + 1]} for i in range(0, len(polygon), 2)
        ]

    def _find_related_figure(self, chunk, images):
        """
        Determines if a text chunk is related to a figure/chart by analyzing:
        1. Content keywords (Exhibit, Figure, Chart, Table, etc.)
        2. Spatial proximity on the same page
        3. Bounding box overlap or adjacency
        """
        if not images:
            return None
            
        chunk_content = chunk.get("content", "").lower()
        chunk_page = chunk.get("page_number")
        
        # Check for figure-related keywords
        figure_keywords = [
            "exhibit", "figure", "chart", "table", "diagram", 
            "graph", "plot", "illustration", "image", "map",
            "returns by country", "performance", "ranking"
        ]
        
        has_figure_keywords = any(keyword in chunk_content for keyword in figure_keywords)
        
        if not has_figure_keywords:
            return None
            
        # Find images on the same page
        page_images = [img for img in images if img.get("page_number") == chunk_page]
        
        if not page_images:
            return None
            
        # For now, return the first image on the same page with figure keywords
        # TODO: Could be enhanced with spatial analysis of bounding boxes
        return page_images[0]

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
