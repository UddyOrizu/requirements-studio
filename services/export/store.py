"""Object storage for export zips: Azure Blob Storage, or the local filesystem for tests and quick local runs.

Keys look like {process_id}/{export_id}.zip (M9 Delivery): blob names in the RS_AZURE_BLOB_CONTAINER_EXPORTS container,
or paths under RS_EXPORT_DIR. Production authenticates with the app's managed
identity (DefaultAzureCredential + RS_AZURE_STORAGE_ACCOUNT_URL); dev and CI use Azurite via a connection string.
"""
import asyncio
from pathlib import Path
from typing import Protocol

from services.common.settings import Settings


class ExportStore(Protocol):
    async def put(self, key: str, data: bytes, content_type: str = "application/zip") -> str: ...  # returns a URI
    async def get(self, key: str) -> bytes: ...


class FileStore:
    def __init__(self, root: Path):
        self.root = root

    async def put(self, key: str, data: bytes, content_type: str = "application/zip") -> str:
        path = self.root / key
        await asyncio.to_thread(lambda: (path.parent.mkdir(parents=True, exist_ok=True), path.write_bytes(data)))
        return f"file://{path}"

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread((self.root / key).read_bytes)


class AzureBlobStore:
    """One container; keys are blob names. The container is created on first use if it does not exist."""

    def __init__(self, *, container: str, account_url: str = "", connection_string: str = ""):
        from azure.storage.blob.aio import BlobServiceClient

        if connection_string:
            self._service = BlobServiceClient.from_connection_string(connection_string)
            self._credential = None
        else:
            from azure.identity.aio import DefaultAzureCredential

            self._credential = DefaultAzureCredential()
            self._service = BlobServiceClient(account_url, credential=self._credential)
        self.container = container
        self._ready = False

    async def _container(self):
        client = self._service.get_container_client(self.container)
        if not self._ready:
            from azure.core.exceptions import ResourceExistsError
            try:
                await client.create_container()
            except ResourceExistsError:
                pass
            self._ready = True
        return client

    async def put(self, key: str, data: bytes, content_type: str = "application/zip") -> str:
        from azure.storage.blob import ContentSettings

        container = await self._container()
        blob = container.get_blob_client(key)
        await blob.upload_blob(data, overwrite=True, content_settings=ContentSettings(content_type=content_type))
        return blob.url

    async def get(self, key: str) -> bytes:
        container = await self._container()
        stream = await container.get_blob_client(key).download_blob()
        return await stream.readall()

    async def close(self) -> None:
        await self._service.close()
        if self._credential is not None:
            await self._credential.close()


def build_store(settings: Settings) -> ExportStore:
    if settings.object_store == "azure_blob":
        return AzureBlobStore(container=settings.azure_blob_container_exports,
                              account_url=settings.azure_storage_account_url,
                              connection_string=settings.azure_storage_connection_string)
    return FileStore(Path(settings.export_dir))
