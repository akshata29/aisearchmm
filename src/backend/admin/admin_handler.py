import logging
from aiohttp import web
from azure.search.documents.aio import SearchClient

logger = logging.getLogger("admin")


class AdminHandler:
    """Handler for administrative operations on search documents"""

    def __init__(self):
        pass

    async def get_document_statistics(self, search_client: SearchClient):
        """Get document statistics from the search index"""
        try:
            # Get all documents in the index
            search_results = await search_client.search(
                search_text="*",
                select="document_title,text_document_id,image_document_id,content_id,document_type,published_date",
                top=10000  # Get a large number to capture all documents
            )
            
            document_stats = {}
            total_documents = 0
            total_chunks = 0
            
            async for result in search_results:
                doc_title = result.get("document_title", "Unknown")
                doc_type = result.get("document_type", "unknown")
                text_doc_id = result.get("text_document_id")
                image_doc_id = result.get("image_document_id")
                
                if doc_title not in document_stats:
                    document_stats[doc_title] = {
                        "document_title": doc_title,
                        "text_chunks": 0,
                        "image_chunks": 0,
                        "total_chunks": 0,
                        "document_type": doc_type,
                        "published_date": result.get("published_date"),
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
            
            # Convert sets to lists for JSON serialization
            for doc_stat in document_stats.values():
                doc_stat["text_document_ids"] = list(doc_stat["text_document_ids"])
                doc_stat["image_document_ids"] = list(doc_stat["image_document_ids"])
            
            total_documents = len(document_stats)
            
            return web.json_response({
                "total_documents": total_documents,
                "total_chunks": total_chunks,
                "documents": list(document_stats.values())
            })
        
        except Exception as e:
            logger.error(f"Error getting document statistics: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def delete_document_by_title(self, request, search_client: SearchClient):
        """Delete all chunks for a specific document title"""
        try:
            body = await request.json()
            document_title = body.get("document_title")
            
            if not document_title:
                return web.json_response({"error": "document_title is required"}, status=400)
            
            # Search for all documents with the specified title
            search_results = await search_client.search(
                search_text="*",
                filter=f"document_title eq '{document_title}'",
                select="content_id",
                top=10000
            )
            
            document_ids = []
            async for result in search_results:
                content_id = result.get("content_id")
                if content_id:
                    document_ids.append(content_id)
            
            if not document_ids:
                return web.json_response({"message": f"No documents found with title: {document_title}"})
            
            # Delete documents by their IDs using the delete_documents method
            delete_documents = [{"content_id": doc_id} for doc_id in document_ids]
            
            result = await search_client.delete_documents(documents=delete_documents)
            
            logger.info(f"Deleted {len(document_ids)} chunks for document: {document_title}")
            
            return web.json_response({
                "message": f"Deleted {len(document_ids)} chunks for document: {document_title}",
                "deleted_chunks": len(document_ids)
            })
        
        except Exception as e:
            logger.error(f"Error deleting document by title: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def delete_document_by_id(self, request, search_client: SearchClient):
        """Delete a specific document chunk by content_id"""
        try:
            body = await request.json()
            content_id = body.get("content_id")
            
            if not content_id:
                return web.json_response({"error": "content_id is required"}, status=400)
            
            # Delete the document using the delete_documents method
            delete_documents = [{"content_id": content_id}]
            
            result = await search_client.delete_documents(documents=delete_documents)
            
            logger.info(f"Deleted document chunk: {content_id}")
            
            return web.json_response({
                "message": f"Deleted document chunk: {content_id}"
            })
        
        except Exception as e:
            logger.error(f"Error deleting document by ID: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def get_document_chunks(self, request, search_client: SearchClient):
        """Get all chunks for a specific document title with full metadata"""
        try:
            document_title = request.query.get("document_title")
            
            if not document_title:
                return web.json_response({"error": "document_title parameter is required"}, status=400)
            
            # Search for all chunks with the specified title
            search_results = await search_client.search(
                search_text="*",
                filter=f"document_title eq '{document_title}'",
                select="content_id,document_title,content_text,content_path,text_document_id,image_document_id,document_type,published_date,locationMetadata",
                top=1000  # Should be enough for most documents
            )
            
            chunks = []
            async for result in search_results:
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
            
            logger.info(f"Retrieved {len(chunks)} chunks for document: {document_title}")
            
            return web.json_response(chunks)
        
        except Exception as e:
            logger.error(f"Error getting document chunks: {e}")
            return web.json_response({"error": str(e)}, status=500)

    def attach_to_app(self, app: web.Application, search_client: SearchClient):
        """Attach admin routes to the aiohttp application"""
        app.add_routes([
            web.get("/api/admin/documents", lambda _: self.get_document_statistics(search_client)),
            web.get("/api/admin/document_chunks", lambda request: self.get_document_chunks(request, search_client)),
            web.post("/api/admin/delete_document", lambda request: self.delete_document_by_title(request, search_client)),
            web.post("/api/admin/delete_chunk", lambda request: self.delete_document_by_id(request, search_client)),
        ])
