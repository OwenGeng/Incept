"""Private Google Cloud Storage implementation for AI Video assets."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Any, BinaryIO

from anyio import to_thread

from app.ai_video.config import settings

if TYPE_CHECKING:
    from app.ai_video.core.storage import StoredFileInfo


def enabled() -> bool:
    """Return whether this runtime was configured to use the Incept GCS bucket."""
    return bool(settings.gcs_bucket_name.strip())


@lru_cache
def _client():
    """Create the ADC-authenticated GCS client once per process."""
    if not enabled():
        raise RuntimeError("GCS is not configured: set GCS_BUCKET_NAME")
    try:
        from google.cloud import storage
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("google-cloud-storage must be installed to use GCS asset storage") from exc
    return storage.Client(project=settings.gcp_project_id or None)


def _object_key(key: str) -> str:
    """Apply the deployment-owned GCS prefix to a logical asset key."""
    normalized = key.lstrip("/")
    base = settings.gcs_base_path.strip().strip("/")
    return f"{base}/{normalized}" if base else normalized


def object_uri(key: str) -> str:
    """Return the stable gs:// URI required by Gemini Omni reference inputs."""
    if not enabled():
        raise RuntimeError("Gemini Omni reference media requires GCS_BUCKET_NAME")
    return f"gs://{settings.gcs_bucket_name}/{_object_key(key)}"


def _external_url(key: str) -> str:
    """Return an explicitly configured external URL, never make a bucket public by default."""
    base = settings.gcs_public_base_url.strip().rstrip("/")
    if not base:
        raise RuntimeError(
            "External provider media access requires GCS_PUBLIC_BASE_URL; private GCS objects are served to users "
            "through the authenticated AI Video download endpoint."
        )
    return f"{base}/{_object_key(key)}"


async def init_storage() -> None:
    """Verify the configured bucket exists and is accessible to the Cloud Run service account."""
    def verify() -> None:
        bucket = _client().bucket(settings.gcs_bucket_name)
        if not bucket.exists():
            raise RuntimeError(f"Configured GCS bucket does not exist or is inaccessible: {settings.gcs_bucket_name}")

    await to_thread.run_sync(verify)


async def upload_file(
    *,
    key: str,
    data: bytes | BinaryIO,
    content_type: str | None = None,
    extra_args: dict[str, Any] | None = None,
) -> "StoredFileInfo":
    """Upload a private object with uniform bucket access-compatible semantics."""
    from app.ai_video.core.storage import StoredFileInfo

    object_key = _object_key(key)

    def upload() -> str | None:
        blob = _client().bucket(settings.gcs_bucket_name).blob(object_key)
        if isinstance(data, (bytes, bytearray)):
            blob.upload_from_string(bytes(data), content_type=content_type)
        else:
            blob.upload_from_file(data, content_type=content_type)
        blob.reload()
        return blob.etag

    etag = await to_thread.run_sync(upload)
    # The browser always fetches private media through the authenticated API.
    return StoredFileInfo(key=object_key, url=object_uri(key), etag=etag)


async def download_file(*, key: str) -> bytes:
    """Download one private GCS object into memory for the existing file service."""
    object_key = _object_key(key)
    return await to_thread.run_sync(
        lambda: _client().bucket(settings.gcs_bucket_name).blob(object_key).download_as_bytes()
    )


async def get_file_info(*, key: str) -> "StoredFileInfo":
    """Read GCS metadata without downloading the file body."""
    from app.ai_video.core.storage import StoredFileInfo

    object_key = _object_key(key)

    def head():
        blob = _client().bucket(settings.gcs_bucket_name).get_blob(object_key)
        if blob is None:
            raise FileNotFoundError(f"GCS object not found: {object_uri(key)}")
        return blob

    blob = await to_thread.run_sync(head)
    return StoredFileInfo(
        key=object_key,
        url=object_uri(key),
        size=int(blob.size) if blob.size is not None else None,
        content_type=blob.content_type,
        etag=blob.etag,
    )


async def create_download_url(*, key: str, expires_in: int = 900) -> str:
    """Return an operator-configured URL for third-party providers such as Creatify.

    Cloud Run ADC intentionally has no downloadable service-account private key,
    so this adapter does not attempt to mint an unsafe or unreliable local signed
    URL. Operators can expose a scoped CDN/signed-URL origin through the explicit
    ``GCS_PUBLIC_BASE_URL`` setting.
    """
    if expires_in <= 0:
        raise ValueError("expires_in must be positive")
    return _external_url(key)


async def list_files(*, prefix: str = "") -> list["StoredFileInfo"]:
    """List objects under a logical prefix for the existing management API."""
    from app.ai_video.core.storage import StoredFileInfo

    object_prefix = _object_key(prefix) if prefix else _object_key("")

    def list_objects() -> list[Any]:
        return list(_client().bucket(settings.gcs_bucket_name).list_blobs(prefix=object_prefix or None))

    blobs = await to_thread.run_sync(list_objects)
    return [
        StoredFileInfo(
            key=str(blob.name),
            url=f"gs://{settings.gcs_bucket_name}/{blob.name}",
            size=int(blob.size) if blob.size is not None else None,
            content_type=blob.content_type,
            etag=blob.etag,
        )
        for blob in blobs
    ]


async def delete_file(*, key: str) -> None:
    """Delete one private GCS object."""
    object_key = _object_key(key)
    await to_thread.run_sync(lambda: _client().bucket(settings.gcs_bucket_name).blob(object_key).delete())
