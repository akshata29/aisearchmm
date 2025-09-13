from email.policy import default
import os
import glob
from typing import Optional
import instructor
import aiofiles
import asyncio
import sys

from azure.core.pipeline.policies import UserAgentPolicy
from azure.ai.documentintelligence.aio import DocumentIntelligenceClient
from azure.ai.inference.aio import EmbeddingsClient, ImageEmbeddingsClient
from openai import AsyncAzureOpenAI, api_version
from azure.search.documents.aio import SearchClient
from azure.search.documents.indexes.aio import SearchIndexClient, SearchIndexerClient
from azure.storage.blob.aio import BlobServiceClient
from azure.core.credentials import AzureKeyCredential
from core.azure_client_factory import ClientFactory, AuthMode, SessionClients
from core.config import get_config
import logging
from data_ingestion.ingestion_models import ProcessRequest
from data_ingestion.image_verbalization_strategy import (
    IndexerImgVerbalizationStrategy,
)
from data_ingestion.strategy import Strategy
from constants import USER_AGENT
from data_ingestion.process_file import ProcessFile
import argparse


def load_environment_variables():
    """Loads environment variables from the .env file."""
    required_vars = [
        "DOCUMENTINTELLIGENCE_ENDPOINT",
        "AZURE_INFERENCE_EMBED_ENDPOINT",
        "SEARCH_SERVICE_ENDPOINT",
        "SEARCH_INDEX_NAME",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_DEPLOYMENT",
        "ARTIFACTS_STORAGE_ACCOUNT_URL",
    ]
    for var in required_vars:
        if not os.getenv(var):
            raise ValueError(f"Missing environment variable: {var}")


def setup_directories():
    """Sets up necessary directories for document and image processing."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    documents_to_process_folder = os.path.abspath(
        os.path.join(script_dir, "../../data")
    )
    documents_output_folder = os.path.abspath(os.path.join(script_dir, "./static"))
    os.makedirs(documents_output_folder, exist_ok=True)

    return documents_to_process_folder, documents_output_folder


def get_blob_storage_credentials():
    storage_account_name = os.getenv("STORAGE_ACCOUNT_NAME")
    blob_container_name = os.getenv("BLOB_CONTAINER_NAME")
    sas_token = os.getenv("BLOB_SAS_TOKEN")
    if not blob_container_name or not sas_token:
        raise ValueError(
            "Blob container name and SAS token must be provided for blob storage source."
        )
    return storage_account_name, blob_container_name, sas_token


async def main(source: str, indexer_Strategy: Optional[str] = None):
    load_environment_variables()
    documents_to_process_folder, documents_output_folder = setup_directories()

    # Use factory to get clients; rely on existing config values
    config = get_config()

    if config.azure_openai.api_key or config.search_service.api_key or config.document_intelligence.key:
        auth_mode = AuthMode.API_KEY
    else:
        auth_mode = AuthMode.MANAGED_IDENTITY

    # Use a fixed session id for the document processor
    session_id = "doc_processor"
    logger = logging.getLogger(__name__)
    logger.info("Document processor starting: session_id=%s auth_mode=%s", session_id, auth_mode)

    bundle = await ClientFactory.get_session_clients(session_id, auth_mode)
    logger.info(
        "Obtained session bundle for document processor: openai=%s document_intel=%s blob=%s search_index=%s",
        bool(bundle.openai_client),
        bool(bundle.document_intelligence_client),
        bool(bundle.blob_service_client),
        bool(bundle.search_index_client),
    )

    document_client = bundle.document_intelligence_client

    # For embeddings, prefer the inference clients if present else reuse AOAI wrapper
    text_embedding_client = None
    image_embedding_client = None
    # If inference endpoints are configured and we need separate clients, keep previous behavior
    if os.environ.get("AZURE_INFERENCE_EMBED_ENDPOINT") and os.environ.get("AZURE_INFERENCE_EMBED_MODEL_NAME"):
        # Caller previously used token credential; reuse AAD when available
        token_cred = bundle.credential
        if token_cred:
            text_embedding_client = EmbeddingsClient(
                endpoint=os.environ["AZURE_INFERENCE_EMBED_ENDPOINT"],
                credential=token_cred,
                model=os.environ["AZURE_INFERENCE_EMBED_MODEL_NAME"],
            )
            image_embedding_client = ImageEmbeddingsClient(
                endpoint=os.environ["AZURE_INFERENCE_EMBED_ENDPOINT"],
                credential=token_cred,
                model=os.environ["AZURE_INFERENCE_EMBED_MODEL_NAME"],
            )

    # Fallback: use AOAI embeddings via openai client
    if text_embedding_client is None:
        class AOAIWrapper:
            def __init__(self, client, model):
                self.client = client
                self.model = model

            async def embed(self, input):
                if isinstance(input, str):
                    input = [input]
                return await self.client.embeddings.create(input=input, model=self.model)

        text_embedding_client = AOAIWrapper(bundle.openai_client, config.azure_openai.embedding_deployment)
        image_embedding_client = text_embedding_client

    search_client = bundle.get_search_client(config.search_service.index_name)

    index_client = bundle.search_index_client

    indexer_Client = SearchIndexerClient(
        endpoint=config.search_service.endpoint,
        credential=(AzureKeyCredential(config.search_service.api_key) if config.search_service.api_key else bundle.credential),
        user_agent_policy=UserAgentPolicy(base_user_agent=USER_AGENT),
    )

    # Create OpenAI/instructor clients
    openai_client = bundle.openai_client
    instructor_openai_client = instructor.from_openai(openai_client)

    blob_service_client = bundle.blob_service_client

    strategy: Strategy | None = None
    request: Optional[ProcessRequest] = None
    if indexer_Strategy == "indexer-image-verbal":
        strategy = IndexerImgVerbalizationStrategy()
        request = ProcessRequest(
            blobServiceClient=blob_service_client,
            blobSource=os.environ["SAMPLES_STORAGE_CONTAINER"],
            indexClient=index_client,
            indexName=os.environ["SEARCH_INDEX_NAME"],
            knowledgeStoreContainer=os.environ["ARTIFACTS_STORAGE_CONTAINER"],
            localDataSource=documents_to_process_folder,
            indexerClient=indexer_Client,
            chatCompletionEndpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            chatCompletionModel=os.environ["AZURE_OPENAI_DEPLOYMENT"],
            chatCompletionDeployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
            aoaiEmbeddingEndpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            aoaiEmbeddingDeployment=os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"],
            aoaiEmbeddingModel=os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"],
            cognitiveServicesEndpoint=os.environ["DOCUMENTINTELLIGENCE_ENDPOINT"],
            subscriptionId=os.environ["AZURE_SUBSCRIPTION_ID"],
            resourceGroup=os.environ["AZURE_RESOURCE_GROUP"],
        )
        await strategy.run(request) if request is not None else None
    elif indexer_Strategy == "self-multimodal-embedding":
        process_file = ProcessFile(
            document_client,
            text_embedding_client,
            image_embedding_client,
            search_client,
            index_client,
            openai_client,  # Use regular OpenAI client
            blob_service_client,
            os.environ["AZURE_OPENAI_DEPLOYMENT"],
        )

        if source == "files":
            await process_files(
                process_file, documents_to_process_folder, documents_output_folder
            )
        elif source == "blobs":
            # prefer session bundle's blob client when present; pass bundle so process_blobs can reuse it
            await process_blobs(process_file, bundle, *get_blob_storage_credentials())
        else:
            raise ValueError("Invalid source. Must be 'files' or 'blobs'.")
    else:
        raise ValueError("Invalid indexer strategy. Check readme for available.")

    print("Done")
    # Close clients if they expose an async close()
    async def _maybe_close(obj):
        try:
            if obj is None:
                return
            close = getattr(obj, "close", None)
            if close is not None:
                await close()
        except Exception:
            pass

    await _maybe_close(document_client)
    await _maybe_close(text_embedding_client)
    await _maybe_close(image_embedding_client)
    await _maybe_close(blob_service_client)
    await _maybe_close(search_client)
    await _maybe_close(index_client)
    await _maybe_close(indexer_Client)
    await _maybe_close(openai_client)
    await _maybe_close(instructor_openai_client)
    # Close the session bundle to release any cached resources
    await bundle.close()


async def process_files(
    process_file, documents_to_process_folder, documents_output_folder
):
    document_paths = glob.glob(os.path.join(documents_to_process_folder, "*.*"))
    for doc_path in document_paths:
        print(f"Processing file: {doc_path}")
        async with aiofiles.open(doc_path, "rb") as f:
            file_bytes = await f.read()
            await process_file.process_file(
                file_bytes,
                os.path.basename(doc_path),
                os.environ["SEARCH_INDEX_NAME"],
                chunking_strategy="document_layout"  # Use default document layout strategy
            )

            # Copy the document to documents_output_folder
            destination_path = os.path.join(
                documents_output_folder, os.path.basename(doc_path)
            )
            with open(doc_path, "rb") as src_file:
                with open(destination_path, "wb") as dest_file:
                    dest_file.write(src_file.read())


async def process_blobs(
    process_file,
    bundle: Optional[SessionClients],
    storage_account_name: str,
    blob_container_name: str,
    sas_token: str,
):
    print(f"storage_account_name: {storage_account_name}")
    print(f"blob_container_name: {blob_container_name}")
    print(f"sas_token: {sas_token}")

    # If a session bundle with an existing blob_service_client is provided, reuse it
    if bundle and getattr(bundle, "blob_service_client", None):
        container_client = bundle.blob_service_client.get_container_client(blob_container_name)
    else:
        blob_service_client = BlobServiceClient(
            account_url=f"https://{storage_account_name}.blob.core.windows.net",
            credential=sas_token,
        )
        container_client = blob_service_client.get_container_client(blob_container_name)

    blobs = container_client.list_blobs(include=["metadata"])

    count = 0
    for blob in blobs:
        print(f"Processing blob: {blob.name}")
        blob_client = container_client.get_blob_client(blob)

        stream = blob_client.download_blob()
        data = stream.readall()
        count += 1
        await process_file.process_file(
            data,
            blob.name,
            os.environ["SEARCH_INDEX_NAME"],
            chunking_strategy="document_layout"  # Use default document layout strategy
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Process documents or blobs using indexers."
    )
    parser.add_argument(
        "--source",
        choices=["files", "blobs"],
        help="Specify the source of documents: 'files' for local files or 'blobs' for blobs.",
    )
    parser.add_argument(
        "--indexer_strategy",
        choices=["indexer-image-verbal", "self-multimodal-embedding"],
    )
    args = parser.parse_args()

    asyncio.run(main(args.source, args.indexer_strategy))