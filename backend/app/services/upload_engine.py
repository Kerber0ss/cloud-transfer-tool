import logging
from typing import Callable, Optional

import httpx
from google.oauth2.credentials import Credentials

from app.connectors.base import DownloadInfo

logger = logging.getLogger(__name__)

CHUNK_SIZE = 8 * 1024 * 1024  # 8MB
GDRIVE_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"


async def _initiate_resumable_session(
    credentials: Credentials,
    filename: str,
    content_type: str,
    folder_id: str,
    total_size: Optional[int],
) -> str:
    """Initiate a Google Drive resumable upload session. Returns upload session URI."""
    headers = {
        "Authorization": f"Bearer {credentials.token}",
        "Content-Type": "application/json",
        "X-Upload-Content-Type": content_type,
    }
    if total_size is not None:
        headers["X-Upload-Content-Length"] = str(total_size)

    metadata = {
        "name": filename,
        "parents": [folder_id],
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{GDRIVE_UPLOAD_URL}?uploadType=resumable",
            headers=headers,
            json=metadata,
        )
        response.raise_for_status()

    session_uri = response.headers.get("Location")
    if not session_uri:
        raise RuntimeError("Google Drive did not return a resumable upload session URI")
    return session_uri


async def _upload_chunk(
    client: httpx.AsyncClient,
    session_uri: str,
    chunk_data: bytes,
    start_byte: int,
    total_size: Optional[int],
    is_last: bool,
) -> tuple[bool, Optional[str]]:
    """Upload a single chunk. Returns (completed, file_id or None)."""
    chunk_len = len(chunk_data)
    end_byte = start_byte + chunk_len - 1

    if total_size is not None:
        content_range = f"bytes {start_byte}-{end_byte}/{total_size}"
    elif is_last:
        content_range = f"bytes {start_byte}-{end_byte}/{start_byte + chunk_len}"
    else:
        content_range = f"bytes {start_byte}-{end_byte}/*"

    headers = {
        "Content-Range": content_range,
        "Content-Length": str(chunk_len),
    }

    response = await client.put(
        session_uri,
        content=chunk_data,
        headers=headers,
    )

    if response.status_code in (200, 201):
        # Upload complete
        data = response.json()
        return True, data.get("id")
    elif response.status_code == 308:
        # Resume Incomplete — chunk accepted, continue
        return False, None
    else:
        response.raise_for_status()
        return False, None


async def stream_to_gdrive(
    download_info: DownloadInfo,
    gdrive_folder_id: str,
    credentials: Credentials,
    progress_callback: Callable[[int, Optional[int]], None],
) -> str:
    """
    Stream file from direct_url directly to Google Drive using Resumable Upload.

    The file is NEVER written to disk. Only one CHUNK_SIZE chunk lives in memory at a time.

    Args:
        download_info: Source file info (direct_url, filename, size_bytes, content_type)
        gdrive_folder_id: Google Drive folder ID (use 'root' for My Drive)
        credentials: Valid Google OAuth2 Credentials object
        progress_callback: Called with (bytes_transferred, total_bytes) after each chunk

    Returns:
        Google Drive file ID of the uploaded file

    Raises:
        RuntimeError: If upload fails at any stage
        httpx.HTTPStatusError: If HTTP request fails
    """
    logger.info(
        f"Starting stream upload: {download_info.filename} "
        f"({download_info.size_bytes} bytes) → Drive folder {gdrive_folder_id}"
    )

    # Step 1: Initiate resumable upload session
    session_uri = await _initiate_resumable_session(
        credentials=credentials,
        filename=download_info.filename,
        content_type=download_info.content_type,
        folder_id=gdrive_folder_id,
        total_size=download_info.size_bytes,
    )
    logger.debug(f"Resumable session created: {session_uri[:80]}...")

    # Step 2: Stream source → buffer → Google Drive
    bytes_sent = 0
    gdrive_file_id: Optional[str] = None
    buffer = bytearray()

    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=30.0, read=120.0, write=120.0, pool=10.0)) as upload_client:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=10.0),
            follow_redirects=True,
        ) as download_client:
            async with download_client.stream("GET", download_info.direct_url) as response:
                response.raise_for_status()

                total_size = download_info.size_bytes
                if total_size is None:
                    cl = response.headers.get("content-length")
                    if cl:
                        total_size = int(cl)
                        logger.info(f"Discovered content-length from response: {total_size}")

                async for raw_chunk in response.aiter_bytes():
                    buffer.extend(raw_chunk)

                    # Upload when buffer reaches CHUNK_SIZE
                    while len(buffer) >= CHUNK_SIZE:
                        chunk = bytes(buffer[:CHUNK_SIZE])
                        buffer = buffer[CHUNK_SIZE:]

                        completed, file_id = await _upload_chunk(
                            client=upload_client,
                            session_uri=session_uri,
                            chunk_data=chunk,
                            start_byte=bytes_sent,
                            total_size=total_size,
                            is_last=False,
                        )
                        bytes_sent += len(chunk)
                        progress_callback(bytes_sent, total_size)
                        logger.debug(f"Uploaded chunk: {bytes_sent} bytes sent")

                        if completed:
                            gdrive_file_id = file_id
                            break

                    if gdrive_file_id:
                        break

        # Step 3: Upload remaining buffer as final chunk
        if not gdrive_file_id and buffer:
            chunk = bytes(buffer)
            completed, file_id = await _upload_chunk(
                client=upload_client,
                session_uri=session_uri,
                chunk_data=chunk,
                start_byte=bytes_sent,
                total_size=total_size,
                is_last=True,
            )
            bytes_sent += len(chunk)
            progress_callback(bytes_sent, total_size)

            if completed:
                gdrive_file_id = file_id
            else:
                raise RuntimeError(f"Upload incomplete after sending all data. bytes_sent={bytes_sent}")

    if not gdrive_file_id:
        raise RuntimeError("Upload completed but no file ID returned from Google Drive")

    logger.info(f"Upload complete: {download_info.filename} → {gdrive_file_id} ({bytes_sent} bytes)")
    return gdrive_file_id
