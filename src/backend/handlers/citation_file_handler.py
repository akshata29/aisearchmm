from aiohttp import web
from azure.storage.blob.aio import ContainerClient, BlobServiceClient
from azure.storage.blob import generate_blob_sas, BlobSasPermissions

from datetime import datetime, timedelta


class CitationFilesHandler:
    def __init__(
        self,
        blob_service_client: BlobServiceClient,
        samples_container_client: ContainerClient,
        artifacts_container_client: ContainerClient,
    ):
        self.container_client = samples_container_client
        self.artifacts_container_client = artifacts_container_client  # For images/figures
        self.blob_service_client = blob_service_client

    async def handle(self, request):
        try:
            data = await request.json()
            response = await self._get_file_url(data["fileName"])
            return web.json_response(response)
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    async def _get_file_url(self, blob_name: str):
        # Determine if this is an image/figure file (should use artifacts container)
        # Images are typically in paths like "aimm/timestamp/figure_X.Y.png"
        is_image = blob_name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')) or 'figure_' in blob_name.lower()
        
        # Use appropriate container based on file type
        container_client = self.artifacts_container_client if is_image else self.container_client
        
        blob_client = container_client.get_blob_client(
            blob_name.replace("\\", "/")
        )
        start_time = datetime.utcnow()
        expiry_time = start_time + timedelta(hours=1)  # Key valid for 1 hour

        # Create the user delegation key
        user_delegation_key = await self.blob_service_client.get_user_delegation_key(
            key_start_time=start_time, key_expiry_time=expiry_time
        )
        sas_token = generate_blob_sas(
            account_name=blob_client.account_name or "",
            container_name=container_client.container_name,  # Use the appropriate container
            blob_name=blob_name.replace("\\", "/"),
            user_delegation_key=user_delegation_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(minutes=60),
        )

        signed_url = f"{blob_client.url}?{sas_token}"
        return signed_url
