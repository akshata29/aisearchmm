import logging
import time
import functools
from typing import Dict, List, Optional, Any
from aiohttp import web
from azure.search.documents.aio import SearchClient
from azure.core.exceptions import AzureError
from utils.logging_config import StructuredLogger
from core.exceptions import ApplicationError, ValidationError

logger = StructuredLogger(__name__)


def monitor_performance(operation_name: str):
    """Simple performance monitoring decorator."""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                logger.performance.log_duration(operation_name, duration)
                return result
            except Exception as e:
                duration = time.time() - start_time
                logger.performance.log_duration(operation_name, duration, status="error")
                raise
        return wrapper
    return decorator


def track_error(operation: str, error: Exception):
    """Simple error tracking function."""
    logger.error(f"Error in {operation}", extra={
        "operation": operation,
        "error_type": type(error).__name__,
        "error_message": str(error)
    }, exc_info=True)


class AdminHandler:
    """
    Production-ready handler for administrative operations on search documents.
    
    Features:
    - Comprehensive error handling and logging
    - Performance monitoring
    - Input validation
    - Rate limiting considerations
    - Structured responses
    """

    def __init__(self, max_batch_size: int = 10000, timeout_seconds: int = 30):
        """
        Initialize AdminHandler with production configurations.
        
        Args:
            max_batch_size: Maximum number of documents to process in a single batch
            timeout_seconds: Timeout for search operations
        """
        self.max_batch_size = max_batch_size
        self.timeout_seconds = timeout_seconds
        logger.info("AdminHandler initialized", extra={
            "max_batch_size": max_batch_size,
            "timeout_seconds": timeout_seconds
        })

    @monitor_performance("admin.get_document_statistics")
    async def get_document_statistics(self, search_client: SearchClient) -> web.Response:
        """
        Get comprehensive document statistics from the search index.
        
        Returns:
            JSON response with total documents, chunks, and detailed statistics
        """
        operation_id = f"get_stats_{int(time.time())}"
        logger.info("Starting document statistics retrieval", extra={"operation_id": operation_id})
        
        try:
            start_time = time.time()
            
            # Get all documents in the index with optimized query
            search_results = await search_client.search(
                search_text="*",
                select="document_title,text_document_id,image_document_id,content_id,document_type,published_date",
                top=self.max_batch_size,
                timeout=self.timeout_seconds
            )

            document_stats: Dict[str, Dict[str, Any]] = {}
            total_documents = 0
            total_chunks = 0
            processed_chunks = 0

            async for result in search_results:
                processed_chunks += 1
                
                doc_title = result.get("document_title", "Unknown")
                doc_type = result.get("document_type", "unknown")
                text_doc_id = result.get("text_document_id")
                image_doc_id = result.get("image_document_id")
                published_date = result.get("published_date")

                if doc_title not in document_stats:
                    document_stats[doc_title] = {
                        "document_title": doc_title,
                        "text_chunks": 0,
                        "image_chunks": 0,
                        "total_chunks": 0,
                        "document_type": doc_type,
                        "published_date": published_date,
                        "text_document_ids": set(),
                        "image_document_ids": set(),
                    }

                total_chunks += 1
                document_stats[doc_title]["total_chunks"] += 1

                if text_doc_id:
                    document_stats[doc_title]["text_chunks"] += 1
                    document_stats[doc_title]["text_document_ids"].add(text_doc_id)

                if image_doc_id:
                    document_stats[doc_title]["image_chunks"] += 1
                    document_stats[doc_title]["image_document_ids"].add(image_doc_id)

                # Log progress for large datasets
                if processed_chunks % 1000 == 0:
                    logger.info(f"Processed {processed_chunks} chunks", extra={
                        "operation_id": operation_id,
                        "processed_chunks": processed_chunks
                    })

            # Convert sets to lists for JSON serialization
            for doc_stat in document_stats.values():
                doc_stat["text_document_ids"] = list(doc_stat["text_document_ids"])
                doc_stat["image_document_ids"] = list(doc_stat["image_document_ids"])

            total_documents = len(document_stats)
            processing_time = time.time() - start_time

            response_data = {
                "total_documents": total_documents,
                "total_chunks": total_chunks,
                "documents": list(document_stats.values()),
                "processing_time_seconds": round(processing_time, 3),
                "operation_id": operation_id
            }

            logger.info("Document statistics retrieval completed", extra={
                "operation_id": operation_id,
                "total_documents": total_documents,
                "total_chunks": total_chunks,
                "processing_time": processing_time
            })

            return web.json_response(response_data)

        except AzureError as e:
            error_msg = f"Azure Search error during statistics retrieval: {str(e)}"
            logger.error(error_msg, extra={
                "operation_id": operation_id,
                "error_type": "AzureError",
                "error_details": str(e)
            })
            track_error("admin.get_document_statistics", e)
            return web.json_response({
                "error": "Search service error",
                "operation_id": operation_id
            }, status=500)
        
        except Exception as e:
            error_msg = f"Unexpected error getting document statistics: {str(e)}"
            logger.error(error_msg, extra={
                "operation_id": operation_id,
                "error_type": type(e).__name__,
                "error_details": str(e)
            }, exc_info=True)
            track_error("admin.get_document_statistics", e)
            return web.json_response({
                "error": "Internal server error",
                "operation_id": operation_id
            }, status=500)

    @monitor_performance("admin.delete_document_by_title")
    async def delete_document_by_title(self, request: web.Request, search_client: SearchClient) -> web.Response:
        """
        Delete all chunks for a specific document title with comprehensive validation.
        
        Args:
            request: HTTP request containing document_title in JSON body
            search_client: Azure Search client
            
        Returns:
            JSON response with deletion results
        """
        operation_id = f"delete_title_{int(time.time())}"
        logger.info("Starting document deletion by title", extra={"operation_id": operation_id})
        
        try:
            # Validate request body
            try:
                body = await request.json()
            except Exception as e:
                logger.warning("Invalid JSON in request body", extra={
                    "operation_id": operation_id,
                    "error": str(e)
                })
                return web.json_response({
                    "error": "Invalid JSON in request body",
                    "operation_id": operation_id
                }, status=400)

            document_title = body.get("document_title")

            if not document_title or not isinstance(document_title, str):
                logger.warning("Missing or invalid document_title", extra={
                    "operation_id": operation_id,
                    "document_title": document_title
                })
                return web.json_response({
                    "error": "document_title is required and must be a string",
                    "operation_id": operation_id
                }, status=400)

            # Sanitize input
            document_title = document_title.strip()
            if len(document_title) > 500:  # Reasonable limit
                return web.json_response({
                    "error": "document_title too long (max 500 characters)",
                    "operation_id": operation_id
                }, status=400)

            logger.info("Searching for documents to delete", extra={
                "operation_id": operation_id,
                "document_title": document_title
            })

            # Search for all documents with the specified title
            # Escape single quotes for OData filter
            escaped_title = document_title.replace("'", "''")
            search_results = await search_client.search(
                search_text="*",
                filter=f"document_title eq '{escaped_title}'",
                select="content_id",
                top=self.max_batch_size,
                timeout=self.timeout_seconds
            )

            document_ids = []
            async for result in search_results:
                content_id = result.get("content_id")
                if content_id:
                    document_ids.append(content_id)

            if not document_ids:
                logger.info("No documents found for deletion", extra={
                    "operation_id": operation_id,
                    "document_title": document_title
                })
                return web.json_response({
                    "message": f"No documents found with title: {document_title}",
                    "deleted_chunks": 0,
                    "operation_id": operation_id
                })

            # Delete documents by their IDs using the delete_documents method
            delete_documents = [{"content_id": doc_id} for doc_id in document_ids]

            logger.info(f"Deleting {len(document_ids)} chunks", extra={
                "operation_id": operation_id,
                "document_title": document_title,
                "chunk_count": len(document_ids)
            })

            result = await search_client.delete_documents(documents=delete_documents)

            logger.info("Document deletion completed", extra={
                "operation_id": operation_id,
                "document_title": document_title,
                "deleted_chunks": len(document_ids)
            })

            return web.json_response({
                "message": f"Deleted {len(document_ids)} chunks for document: {document_title}",
                "deleted_chunks": len(document_ids),
                "operation_id": operation_id
            })

        except AzureError as e:
            error_msg = f"Azure Search error during document deletion: {str(e)}"
            logger.error(error_msg, extra={
                "operation_id": operation_id,
                "document_title": document_title if 'document_title' in locals() else "unknown",
                "error_type": "AzureError"
            })
            track_error("admin.delete_document_by_title", e)
            return web.json_response({
                "error": "Search service error during deletion",
                "operation_id": operation_id
            }, status=500)

        except Exception as e:
            error_msg = f"Unexpected error deleting document by title: {str(e)}"
            logger.error(error_msg, extra={
                "operation_id": operation_id,
                "document_title": document_title if 'document_title' in locals() else "unknown",
                "error_type": type(e).__name__
            }, exc_info=True)
            track_error("admin.delete_document_by_title", e)
            return web.json_response({
                "error": "Internal server error",
                "operation_id": operation_id
            }, status=500)

    @monitor_performance("admin.delete_document_by_id")
    async def delete_document_by_id(self, request: web.Request, search_client: SearchClient) -> web.Response:
        """
        Delete a specific document chunk by content_id with validation.
        
        Args:
            request: HTTP request containing content_id in JSON body
            search_client: Azure Search client
            
        Returns:
            JSON response with deletion results
        """
        operation_id = f"delete_id_{int(time.time())}"
        logger.info("Starting document deletion by ID", extra={"operation_id": operation_id})
        
        try:
            # Validate request body
            try:
                body = await request.json()
            except Exception as e:
                logger.warning("Invalid JSON in request body", extra={
                    "operation_id": operation_id,
                    "error": str(e)
                })
                return web.json_response({
                    "error": "Invalid JSON in request body",
                    "operation_id": operation_id
                }, status=400)

            content_id = body.get("content_id")

            if not content_id or not isinstance(content_id, str):
                logger.warning("Missing or invalid content_id", extra={
                    "operation_id": operation_id,
                    "content_id": content_id
                })
                return web.json_response({
                    "error": "content_id is required and must be a string",
                    "operation_id": operation_id
                }, status=400)

            # Sanitize input
            content_id = content_id.strip()
            if len(content_id) > 200:  # Reasonable limit for IDs
                return web.json_response({
                    "error": "content_id too long (max 200 characters)",
                    "operation_id": operation_id
                }, status=400)

            logger.info("Deleting document chunk", extra={
                "operation_id": operation_id,
                "content_id": content_id
            })

            # Delete the document using the delete_documents method
            delete_documents = [{"content_id": content_id}]

            result = await search_client.delete_documents(documents=delete_documents)

            logger.info("Document chunk deletion completed", extra={
                "operation_id": operation_id,
                "content_id": content_id
            })

            return web.json_response({
                "message": f"Deleted document chunk: {content_id}",
                "operation_id": operation_id
            })

        except AzureError as e:
            error_msg = f"Azure Search error during chunk deletion: {str(e)}"
            logger.error(error_msg, extra={
                "operation_id": operation_id,
                "content_id": content_id if 'content_id' in locals() else "unknown",
                "error_type": "AzureError"
            })
            track_error("admin.delete_document_by_id", e)
            return web.json_response({
                "error": "Search service error during deletion",
                "operation_id": operation_id
            }, status=500)

        except Exception as e:
            error_msg = f"Unexpected error deleting document by ID: {str(e)}"
            logger.error(error_msg, extra={
                "operation_id": operation_id,
                "content_id": content_id if 'content_id' in locals() else "unknown",
                "error_type": type(e).__name__
            }, exc_info=True)
            track_error("admin.delete_document_by_id", e)
            return web.json_response({
                "error": "Internal server error",
                "operation_id": operation_id
            }, status=500)

    @monitor_performance("admin.get_document_chunks")
    async def get_document_chunks(self, request: web.Request, search_client: SearchClient) -> web.Response:
        """
        Get all chunks for a specific document title with full metadata and pagination support.
        
        Args:
            request: HTTP request with document_title query parameter
            search_client: Azure Search client
            
        Returns:
            JSON response with document chunks
        """
        operation_id = f"get_chunks_{int(time.time())}"
        logger.info("Starting document chunks retrieval", extra={"operation_id": operation_id})
        
        try:
            document_title = request.query.get("document_title")
            
            if not document_title:
                logger.warning("Missing document_title parameter", extra={
                    "operation_id": operation_id
                })
                return web.json_response({
                    "error": "document_title parameter is required",
                    "operation_id": operation_id
                }, status=400)

            # Sanitize input
            document_title = document_title.strip()
            if len(document_title) > 500:
                return web.json_response({
                    "error": "document_title too long (max 500 characters)",
                    "operation_id": operation_id
                }, status=400)

            # Optional pagination parameters
            try:
                limit = min(int(request.query.get("limit", 10000)), self.max_batch_size)
                offset = max(int(request.query.get("offset", 0)), 0)
            except ValueError:
                return web.json_response({
                    "error": "limit and offset must be valid integers",
                    "operation_id": operation_id
                }, status=400)

            logger.info("Searching for document chunks", extra={
                "operation_id": operation_id,
                "document_title": document_title,
                "limit": limit,
                "offset": offset
            })

            # Search for all chunks with the specified title
            # Escape single quotes for OData filter
            escaped_title = document_title.replace("'", "''")
            search_results = await search_client.search(
                search_text="*",
                filter=f"document_title eq '{escaped_title}'",
                select="content_id,document_title,content_text,content_path,text_document_id,image_document_id,document_type,published_date,locationMetadata",
                top=limit,
                skip=offset,
                timeout=self.timeout_seconds
            )

            chunks = []
            chunk_count = 0
            
            async for result in search_results:
                chunk_count += 1
                chunk = {
                    "content_id": result.get("content_id"),
                    "document_title": result.get("document_title"),
                    "content_text": result.get("content_text"),
                    "content_path": result.get("content_path"),
                    "text_document_id": result.get("text_document_id"),
                    "image_document_id": result.get("image_document_id"),
                    "document_type": result.get("document_type"),
                    "published_date": result.get("published_date"),
                    "locationMetadata": result.get("locationMetadata")
                }
                chunks.append(chunk)

            logger.info("Document chunks retrieval completed", extra={
                "operation_id": operation_id,
                "document_title": document_title,
                "chunk_count": chunk_count,
                "limit": limit,
                "offset": offset
            })

            response_data = {
                "chunks": chunks,
                "count": chunk_count,
                "limit": limit,
                "offset": offset,
                "operation_id": operation_id
            }

            return web.json_response(response_data)

        except AzureError as e:
            error_msg = f"Azure Search error during chunks retrieval: {str(e)}"
            logger.error(error_msg, extra={
                "operation_id": operation_id,
                "document_title": document_title if 'document_title' in locals() else "unknown",
                "error_type": "AzureError"
            })
            track_error("admin.get_document_chunks", e)
            return web.json_response({
                "error": "Search service error during chunks retrieval",
                "operation_id": operation_id
            }, status=500)

        except Exception as e:
            error_msg = f"Unexpected error getting document chunks: {str(e)}"
            logger.error(error_msg, extra={
                "operation_id": operation_id,
                "document_title": document_title if 'document_title' in locals() else "unknown",
                "error_type": type(e).__name__
            }, exc_info=True)
            track_error("admin.get_document_chunks", e)
            return web.json_response({
                "error": "Internal server error",
                "operation_id": operation_id
            }, status=500)

    def attach_to_app(self, app: web.Application, search_client: SearchClient) -> None:
        """
        Attach admin routes to the aiohttp application with proper error handling.
        
        Args:
            app: aiohttp web application
            search_client: Azure Search client
        """
        logger.info("Attaching admin routes to application")
        
        try:
            app.add_routes([
                web.get("/api/admin/documents", lambda _: self.get_document_statistics(search_client)),
                web.get("/api/admin/document_chunks", lambda request: self.get_document_chunks(request, search_client)),
                web.post("/api/admin/delete_document", lambda request: self.delete_document_by_title(request, search_client)),
                web.post("/api/admin/delete_chunk", lambda request: self.delete_document_by_id(request, search_client)),
            ])
            
            logger.info("Admin routes successfully attached", extra={
                "routes": [
                    "/api/admin/documents",
                    "/api/admin/document_chunks", 
                    "/api/admin/delete_document",
                    "/api/admin/delete_chunk"
                ]
            })
            
        except Exception as e:
            logger.error("Failed to attach admin routes", extra={
                "error": str(e),
                "error_type": type(e).__name__
            }, exc_info=True)
            raise ApplicationError(f"Failed to attach admin routes: {str(e)}")
