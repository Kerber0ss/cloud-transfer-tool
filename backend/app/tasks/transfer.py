import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import redis as redis_lib

from app.tasks.celery_app import celery_app
from app.config import settings

logger = logging.getLogger(__name__)


def get_redis():
    return redis_lib.from_url(settings.redis_url, decode_responses=True)


@celery_app.task(bind=True, name="transfer_file")
def transfer_file(
    self,
    task_id: str,
    username: str,
    source_url: str,
    provider: str,
    gdrive_folder_id: str,
    gdrive_folder_name: str,
    filename: Optional[str] = None,
):
    from app.auth.google_oauth import get_google_credentials
    from app.connectors.registry import get_connector
    from app.connectors.base import ConnectorError
    from app.models import Provider
    from app.services.upload_engine import stream_to_gdrive

    r = get_redis()

    def update_progress(bytes_transferred: int, total_bytes: Optional[int]):
        progress_pct = 0
        if total_bytes and total_bytes > 0:
            progress_pct = min(int(bytes_transferred / total_bytes * 100), 99)

        self.update_state(
            state="PROGRESS",
            meta={
                "status": "RUNNING",
                "progress_pct": progress_pct,
                "bytes_transferred": bytes_transferred,
                "total_bytes": total_bytes,
                "filename": filename or "unknown",
                "gdrive_folder_name": gdrive_folder_name,
                "error": None,
            },
        )

    try:
        self.update_state(
            state="PROGRESS",
            meta={
                "status": "RUNNING",
                "progress_pct": 0,
                "bytes_transferred": 0,
                "total_bytes": None,
                "filename": filename or "resolving...",
                "gdrive_folder_name": gdrive_folder_name,
                "error": None,
            },
        )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            credentials = loop.run_until_complete(get_google_credentials(username))
            if credentials is None:
                raise RuntimeError("Google Drive not connected. Please reconnect your Google Drive account.")

            connector = get_connector(Provider(provider))
            download_info = loop.run_until_complete(connector.get_download_info(source_url))
            logger.info(f"Resolved: {download_info.filename} ({download_info.size_bytes} bytes)")

            if filename:
                download_info = download_info.model_copy(update={"filename": filename})
            else:
                filename_resolved = download_info.filename

            self.update_state(
                state="PROGRESS",
                meta={
                    "status": "RUNNING",
                    "progress_pct": 0,
                    "bytes_transferred": 0,
                    "total_bytes": download_info.size_bytes,
                    "filename": download_info.filename,
                    "gdrive_folder_name": gdrive_folder_name,
                    "error": None,
                },
            )

            gdrive_file_id = loop.run_until_complete(
                stream_to_gdrive(
                    download_info=download_info,
                    gdrive_folder_id=gdrive_folder_id,
                    credentials=credentials,
                    progress_callback=update_progress,
                )
            )

        finally:
            loop.close()

        logger.info(f"Transfer complete: {download_info.filename} → {gdrive_file_id}")
        return {
            "status": "SUCCESS",
            "gdrive_file_id": gdrive_file_id,
            "filename": download_info.filename,
            "gdrive_folder_name": gdrive_folder_name,
        }

    except ConnectorError as e:
        logger.error(f"Connector error for task {task_id}: {e}")
        self.update_state(state="FAILURE", meta={"error": str(e), "status": "FAILED"})
        raise
    except Exception as e:
        logger.error(f"Task {task_id} failed: {e}", exc_info=True)
        self.update_state(state="FAILURE", meta={"error": str(e), "status": "FAILED"})
        raise
