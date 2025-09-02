import os
import tempfile
import asyncio
import aiofiles
import datetime
import logging
import time
import hashlib
from typing import Optional, Dict, Any
from pathlib import Path
from aiohttp import web
import json
import uuid

from azure.core.pipeline.policies import UserAgentPolicy
from azure.ai.documentintelligence.aio import DocumentIntelligenceClient
from azure.ai.inference.aio import EmbeddingsClient, ImageEmbeddingsClient
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import AzureError
from openai import AsyncAzureOpenAI
from azure.search.documents.aio import SearchClient
from azure.search.documents.indexes.aio import SearchIndexClient, SearchIndexerClient
from azure.storage.blob.aio import BlobServiceClient
from azure.identity.aio import DefaultAzureCredential
import instructor

from constants import USER_AGENT
from data_ingestion.process_file import ProcessFile

# Set up structured logging
logger = logging.getLogger(__name__)


class SimpleDocumentUploadHandler:
    """Production-ready document upload handler with enhanced error handling and monitoring."""
    
    # Configuration constants
    SUPPORTED_EXTENSIONS = {'.pdf', '.docx', '.doc', '.txt', '.md', '.html', '.htm'}
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
    
    def __init__(self):
        self.credential = None
        self.clients = {}
        self.processing_status = {}  # Simple in-memory status tracking
        self.active_uploads = 0
        
        logger.info("Upload handler initialized", extra={
            "max_file_size_mb": self.MAX_FILE_SIZE / (1024 * 1024),
            "supported_extensions": list(self.SUPPORTED_EXTENSIONS)
        })

    def _validate_file(self, filename: str, file_size: int) -> None:
        """Validate uploaded file for security and format compliance."""
        if not filename:
            raise ValueError("Filename is required")
            
        # Check file extension
        file_ext = Path(filename).suffix.lower()
        if file_ext not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type: {file_ext}. "
                f"Supported types: {', '.join(self.SUPPORTED_EXTENSIONS)}"
            )
            
        # Check file size
        if file_size > self.MAX_FILE_SIZE:
            raise ValueError(
                f"File too large: {file_size / (1024*1024):.1f}MB. "
                f"Maximum allowed: {self.MAX_FILE_SIZE / (1024*1024):.1f}MB"
            )
            
        # Check filename for security (basic sanitization)
        if any(char in filename for char in ['..', '/', '\\', '<', '>', ':', '"', '|', '?', '*']):
            raise ValueError("Filename contains invalid characters")

    async def initialize_clients(self):
        """Initialize all Azure clients needed for document processing"""
        logger.info("Initializing Azure clients")
        start_time = time.time()
        
        if self.credential is None:
            self.credential = DefaultAzureCredential()

        # Initialize Document Intelligence client with key
        document_key = os.environ.get("DOCUMENTINTELLIGENCE_KEY")
        doc_endpoint = os.environ.get("DOCUMENTINTELLIGENCE_ENDPOINT")
        
        if not doc_endpoint:
            logger.error("DOCUMENTINTELLIGENCE_ENDPOINT environment variable is required")
            raise ValueError("DOCUMENTINTELLIGENCE_ENDPOINT environment variable is required")
            
        if document_key:
            self.clients['document'] = DocumentIntelligenceClient(
                endpoint=doc_endpoint,
                credential=AzureKeyCredential(document_key),
            )
            logger.info("Document Intelligence client initialized with API key")
        else:
            self.clients['document'] = DocumentIntelligenceClient(
                endpoint=doc_endpoint,
                credential=self.credential,
            )
            logger.info("Document Intelligence client initialized with managed identity")

        # Initialize embedding clients - use Azure OpenAI instead of Azure AI Inference
        # since AI Inference endpoint may not have embedding models available
        from openai import AsyncAzureOpenAI
        
        # Create a simple wrapper for Azure OpenAI embeddings to match the interface
        class AzureOpenAIEmbeddingClient:
            def __init__(self, client, deployment):
                self.client = client
                self.deployment = deployment
                
            async def embed(self, input, model=None):
                # Convert single string to list if needed
                if isinstance(input, str):
                    input = [input]
                
                response = await self.client.embeddings.create(
                    input=input,
                    model=self.deployment
                )
                return response
        
        # Initialize Azure OpenAI client for embeddings with graceful fallback
        openai_embedding_client = AsyncAzureOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            api_version="2024-08-01-preview",
        )

        deployment_name = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")

        async def get_embedding_clients():
            try:
                # Probe once with a tiny request to validate deployment
                _ = await openai_embedding_client.embeddings.create(
                    input=["ping"], model=deployment_name
                )
                aoai_client = AzureOpenAIEmbeddingClient(openai_embedding_client, deployment_name)
                return aoai_client, aoai_client
            except Exception as e:
                # Fallback to Azure AI Inference when AOAI deployment is missing
                if "DeploymentNotFound" in str(e) or "404" in str(e):
                    from azure.ai.inference.aio import EmbeddingsClient as InferenceEmbeddingsClient
                    inf_endpoint = os.environ.get("AZURE_INFERENCE_EMBED_ENDPOINT")
                    inf_key = os.environ.get("AZURE_INFERENCE_API_KEY")
                    inf_model = os.environ.get("AZURE_INFERENCE_EMBED_MODEL_NAME")
                    if inf_endpoint and inf_model and inf_key:
                        # Wrap Inference client to match .embed(input=..)
                        class InferenceWrapper:
                            def __init__(self, client, model):
                                self.client = client
                                self.model = model
                            async def embed(self, input, model=None):
                                if isinstance(input, str):
                                    input = [input]
                                resp = await self.client.embed(input=input, model=self.model)
                                return resp
                        inf_client = InferenceEmbeddingsClient(
                            endpoint=inf_endpoint,
                            credential=AzureKeyCredential(inf_key),
                        )
                        wrap = InferenceWrapper(inf_client, inf_model)
                        return wrap, wrap
                # Surface the AOAI error if no fallback is possible
                raise

        text_embed_client, image_embed_client = await get_embedding_clients()
        self.clients['text_embedding'] = text_embed_client
        self.clients['image_embedding'] = image_embed_client

        # Initialize OpenAI client with API key
        openai_client = AsyncAzureOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            api_version="2024-08-01-preview",
        )
        # Store both regular and instructor clients
        self.clients['openai'] = openai_client
        self.clients['instructor_openai'] = instructor.from_openai(openai_client)

        # Initialize Search clients with API key
        search_key = os.environ.get("SEARCH_API_KEY")
        if search_key:
            search_credential = AzureKeyCredential(search_key)
        else:
            search_credential = self.credential

        self.clients['search'] = SearchClient(
            endpoint=os.environ["SEARCH_SERVICE_ENDPOINT"],
            index_name=os.environ["SEARCH_INDEX_NAME"],
            credential=search_credential,
            user_agent_policy=UserAgentPolicy(base_user_agent=USER_AGENT),
        )

        self.clients['search_index'] = SearchIndexClient(
            endpoint=os.environ["SEARCH_SERVICE_ENDPOINT"],
            credential=search_credential,
            user_agent_policy=UserAgentPolicy(base_user_agent=USER_AGENT),
        )

        self.clients['search_indexer'] = SearchIndexerClient(
            endpoint=os.environ["SEARCH_SERVICE_ENDPOINT"],
            credential=search_credential,
            user_agent_policy=UserAgentPolicy(base_user_agent=USER_AGENT),
        )

        # Initialize Blob Storage client
        self.clients['blob_service'] = BlobServiceClient(
            account_url=os.environ["ARTIFACTS_STORAGE_ACCOUNT_URL"],
            credential=self.credential,
        )
        self.clients['blob_container'] = self.clients['blob_service'].get_container_client(
            os.environ["ARTIFACTS_STORAGE_CONTAINER"]
        )
        
        duration = time.time() - start_time
        logger.info("All Azure clients initialized successfully", extra={
            "initialization_time_seconds": round(duration, 3),
            "clients_count": len(self.clients)
        })

    async def handle_upload(self, request):
        """Handle file upload with enhanced validation and monitoring"""
        upload_id = str(uuid.uuid4())
        operation_start = time.time()
        
        try:
            logger.info("Starting file upload", extra={
                "upload_id": upload_id,
                "remote_addr": request.remote
            })
            
            # Check concurrent uploads limit
            if self.active_uploads >= 10:  # Reasonable limit
                logger.warning("Upload rejected due to rate limit", extra={
                    "upload_id": upload_id,
                    "active_uploads": self.active_uploads
                })
                return web.json_response({
                    "error": "Too many concurrent uploads. Please try again later."
                }, status=429)
            
            self.active_uploads += 1
            
            # Initialize status
            self.processing_status[upload_id] = {
                "status": "uploading",
                "message": "Receiving file...",
                "progress": 10,
                "created_at": datetime.datetime.now().isoformat(),
                "upload_id": upload_id
            }

            # Get the uploaded file
            reader = await request.multipart()
            field = await reader.next()
            
            if field.name != 'file':
                logger.warning("No file field found in upload", extra={"upload_id": upload_id})
                return web.json_response({
                    "error": "No file field found"
                }, status=400)

            # Get filename and validate
            filename = field.filename or "upload.pdf"
            
            # Get file size if available
            file_size = 0
            if hasattr(field, 'size') and field.size:
                file_size = field.size
                
            try:
                # Validate file before processing
                self._validate_file(filename, file_size)
            except ValueError as e:
                logger.warning("File validation failed", extra={
                    "upload_id": upload_id,
                    "file_name": filename,
                    "error": str(e)
                })
                return web.json_response({
                    "error": str(e)
                }, status=400)

            # Create temp file
            temp_dir = tempfile.mkdtemp()
            temp_file_path = Path(temp_dir) / filename
            
            # Update status
            self.processing_status[upload_id]["status"] = "saving"
            self.processing_status[upload_id]["message"] = "Saving file..."
            self.processing_status[upload_id]["progress"] = 30

            async with aiofiles.open(temp_file_path, 'wb') as f:
                while True:
                    chunk = await field.read_chunk()
                    if not chunk:
                        break
                    await f.write(chunk)

            # Update status
            self.processing_status[upload_id]["status"] = "uploaded"
            self.processing_status[upload_id]["message"] = "File uploaded successfully"
            self.processing_status[upload_id]["progress"] = 50
            self.processing_status[upload_id]["file_path"] = str(temp_file_path)
            self.processing_status[upload_id]["filename"] = filename

            duration = time.time() - operation_start
            logger.info("File upload completed successfully", extra={
                "upload_id": upload_id,
                "file_name": filename,
                "file_size_bytes": temp_file_path.stat().st_size if temp_file_path.exists() else 0,
                "duration_seconds": round(duration, 3)
            })

            return web.json_response({
                "upload_id": upload_id,
                "filename": filename,
                "message": "File uploaded successfully"
            })

        except AzureError as e:
            logger.error("Azure service error during upload", extra={
                "upload_id": upload_id,
                "error_type": "AzureError",
                "error_message": str(e)
            }, exc_info=True)
            return web.json_response({
                "error": "Azure service error during upload"
            }, status=500)
        except Exception as e:
            logger.error("Unexpected error during upload", extra={
                "upload_id": upload_id,
                "error_type": type(e).__name__,
                "error_message": str(e)
            }, exc_info=True)
            return web.json_response({
                "error": f"Upload failed: {str(e)}"
            }, status=500)
        finally:
            # Always decrement active uploads counter
            if hasattr(self, 'active_uploads'):
                self.active_uploads = max(0, self.active_uploads - 1)

    async def handle_process_document(self, request):
        """Handle document processing with enhanced logging and monitoring"""
        process_start = time.time()
        upload_id = None
        
        try:
            data = await request.json()
            upload_id = data.get('upload_id')
            published_date = data.get('published_date')  # Extract metadata
            document_type = data.get('document_type')    # Extract metadata
            
            # Extract chunking parameters with defaults
            chunk_size = data.get('chunk_size', 500)
            chunk_overlap = data.get('chunk_overlap', 50)
            output_format = data.get('output_format', 'markdown')  # 'markdown' or 'text'
            chunking_strategy = data.get('chunking_strategy', 'document_layout')  # 'document_layout' or 'custom'
            
            logger.info("Starting document processing", extra={
                "upload_id": upload_id,
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
                "output_format": output_format,
                "chunking_strategy": chunking_strategy,
                "document_type": document_type
            })
            
            if not upload_id or upload_id not in self.processing_status:
                logger.warning("Invalid or missing upload ID", extra={
                    "upload_id": upload_id,
                    "available_uploads": list(self.processing_status.keys())
                })
                return web.json_response({
                    "error": "Invalid upload ID"
                }, status=400)

            # Initialize clients if not done
            if not self.clients:
                await self.initialize_clients()

            file_info = self.processing_status[upload_id]
            file_path = file_info.get('file_path')
            filename = file_info.get('filename')

            if not file_path or not Path(file_path).exists():
                return web.json_response(
                    {"error": "File not found"}, 
                    status=400
                )

            # Store metadata and processing options in processing status for use in background processing
            self.processing_status[upload_id]["metadata"] = {
                "published_date": published_date,
                "document_type": document_type
            }
            
            self.processing_status[upload_id]["processing_options"] = {
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
                "output_format": output_format,
                "chunking_strategy": chunking_strategy
            }

            # Update status
            self.processing_status[upload_id]["status"] = "processing"
            self.processing_status[upload_id]["message"] = "Processing document..."
            self.processing_status[upload_id]["progress"] = 60

            # Start processing in background with proper task management
            loop = asyncio.get_running_loop()
            task = loop.create_task(self._process_document_async(upload_id, file_path, filename))
            
            # Store the task to prevent it from being garbage collected
            if not hasattr(self, '_background_tasks'):
                self._background_tasks = set()
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

            return web.json_response({
                "upload_id": upload_id,
                "message": "Document processing started"
            })

        except Exception as e:
            return web.json_response(
                {"error": f"Processing failed: {str(e)}"}, 
                status=500
            )

    async def handle_status(self, request):
        """Get processing status"""
        upload_id = request.query.get('upload_id')
        
        if not upload_id or upload_id not in self.processing_status:
            return web.json_response(
                {"error": "Invalid upload ID"}, 
                status=400
            )
        
        return web.json_response(self.processing_status[upload_id])

    async def _process_document_async(self, upload_id, file_path, filename):
        """Process document asynchronously with detailed progress tracking"""
        try:
            # Initialize detailed tracking
            self.processing_status[upload_id]["details"] = {
                "steps": [],
                "figures_processed": 0,
                "total_figures": 0,
                "pages_processed": 0,
                "total_pages": 0,
                "chunks_created": 0,
                "images_extracted": 0
            }

            # Update status
            self.processing_status[upload_id]["status"] = "analyzing"
            self.processing_status[upload_id]["message"] = "Analyzing document structure..."
            self.processing_status[upload_id]["progress"] = 70
            self.processing_status[upload_id]["details"]["steps"].append({
                "step": "document_analysis", 
                "status": "started", 
                "timestamp": datetime.datetime.now().isoformat()
            })

            # Create ProcessFile instance
            # Provide a progress callback to stream granular updates
            def progress_cb(step, message, progress=None, increments=None):
                try:
                    self.update_processing_progress(
                        upload_id, step, message, progress=progress, details=None, increments=increments
                    )
                except Exception:
                    pass

            processor = ProcessFile(
                document_client=self.clients['document'],
                text_model=self.clients['text_embedding'],
                image_model=self.clients['image_embedding'],
                search_client=self.clients['search'],
                index_client=self.clients['search_index'],
                instructor_openai_client=self.clients['openai'],  # Use regular OpenAI client for image descriptions
                blob_service_client=self.clients['blob_service'],
                chatcompletions_model_name=os.environ["AZURE_OPENAI_DEPLOYMENT"],
                progress_callback=progress_cb,
            )

            # Update status
            self.processing_status[upload_id]["status"] = "processing"
            self.processing_status[upload_id]["message"] = "Extracting content and generating embeddings..."
            self.processing_status[upload_id]["progress"] = 80
            self.processing_status[upload_id]["details"]["steps"].append({
                "step": "content_extraction", 
                "status": "started", 
                "timestamp": datetime.datetime.now().isoformat()
            })

            # Read file bytes
            with open(file_path, 'rb') as f:
                file_bytes = f.read()

            # Create a custom processor wrapper that updates progress
            class ProgressTrackingProcessor:
                def __init__(self, processor, upload_handler, upload_id):
                    self.processor = processor
                    self.upload_handler = upload_handler
                    self.upload_id = upload_id
                    
                async def process_file(self, *args, **kwargs):
                    # Hook into the processor to track progress
                    return await self.processor.process_file(*args, **kwargs)

            progress_processor = ProgressTrackingProcessor(processor, self, upload_id)

            # Extract metadata and processing options from processing status
            metadata = self.processing_status[upload_id].get("metadata", {})
            published_date = metadata.get("published_date")
            document_type = metadata.get("document_type")
            
            processing_options = self.processing_status[upload_id].get("processing_options", {})
            chunk_size = processing_options.get("chunk_size", 500)
            chunk_overlap = processing_options.get("chunk_overlap", 50)
            output_format = processing_options.get("output_format", "markdown")
            chunking_strategy = processing_options.get("chunking_strategy", "document_layout")

            # Process the file with metadata and processing options
            await processor.process_file(
                file_bytes=file_bytes,
                file_name=filename,
                index_name=os.environ["SEARCH_INDEX_NAME"],
                published_date=published_date,
                document_type=document_type,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                output_format=output_format,
                chunking_strategy=chunking_strategy
            )

            # Update final status
            self.processing_status[upload_id]["status"] = "completed"
            self.processing_status[upload_id]["message"] = "Document processed successfully!"
            self.processing_status[upload_id]["progress"] = 100
            self.processing_status[upload_id]["details"]["steps"].append({
                "step": "indexing_complete", 
                "status": "completed", 
                "timestamp": datetime.datetime.now().isoformat()
            })

            # Clean up temp file
            try:
                Path(file_path).unlink()
                Path(file_path).parent.rmdir()
            except:
                pass  # Ignore cleanup errors

        except Exception as e:
            self.processing_status[upload_id]["status"] = "error"
            self.processing_status[upload_id]["message"] = f"Processing failed: {str(e)}"
            self.processing_status[upload_id]["progress"] = 100
            self.processing_status[upload_id]["details"]["steps"].append({
                "step": "error", 
                "status": "failed", 
                "error": str(e),
                "timestamp": datetime.datetime.now().isoformat()
            })
            print(f"Document processing error for {upload_id}: {e}")

    def update_processing_progress(self, upload_id, step, message, progress=None, details=None, increments=None):
        """Update processing progress with detailed information"""
        if upload_id in self.processing_status:
            self.processing_status[upload_id]["message"] = message
            if progress is not None:
                self.processing_status[upload_id]["progress"] = progress
            if details:
                self.processing_status[upload_id]["details"].update(details)
            # Apply incremental counters safely
            if increments:
                det = self.processing_status[upload_id].setdefault("details", {})
                for k, v in increments.items():
                    try:
                        det[k] = int(det.get(k, 0)) + int(v)
                    except Exception:
                        det[k] = v
            self.processing_status[upload_id]["details"]["steps"].append({
                "step": step,
                "message": message,
                "timestamp": datetime.datetime.now().isoformat(),
                "details": details,
            })


# Create global instance
upload_handler = SimpleDocumentUploadHandler()
