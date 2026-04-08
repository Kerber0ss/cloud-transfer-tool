import json
import logging
from datetime import datetime, timezone

import redis as redis_lib
from fastapi import APIRouter, Depends, HTTPException, status

from app.config import settings
from app.auth.app_auth import get_current_user
from app.auth.google_oauth import load_tokens_from_redis
from app.models import UploadJobCreate, Provider
from app.tasks.transfer import transfer_file

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/upload", tags=["upload"])


def get_redis():
    return redis_lib.from_url(settings.redis_url, decode_responses=True)


@router.post("")
async def create_upload_job(
    job: UploadJobCreate,
    current_user: str = Depends(get_current_user),
):
    token_data = load_tokens_from_redis(current_user)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google Drive not connected. Please connect your Google Drive account first.",
        )

    if job.provider not in (Provider.MAIL_RU,):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider '{job.provider}' is not yet supported. Currently supported: mail_ru",
        )

    if job.provider == Provider.MAIL_RU and "cloud.mail.ru" not in job.source_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL does not appear to be a cloud.mail.ru link",
        )

    result = transfer_file.delay(
        task_id="pending",
        username=current_user,
        source_url=job.source_url,
        provider=job.provider.value,
        gdrive_folder_id=job.gdrive_folder_id,
        gdrive_folder_name=job.gdrive_folder_name,
        filename=job.filename,
    )
    task_id = result.id

    r = get_redis()
    meta = {
        "task_id": task_id,
        "username": current_user,
        "source_url": str(job.source_url),
        "provider": job.provider.value,
        "gdrive_folder_id": job.gdrive_folder_id,
        "gdrive_folder_name": job.gdrive_folder_name,
        "filename": job.filename or "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    r.set(f"task_meta:{task_id}", json.dumps(meta))
    r.rpush(f"task_list:{current_user}", task_id)
    r.expire(f"task_list:{current_user}", 604800)

    logger.info(f"Dispatched transfer task {task_id} for user {current_user}")
    return {"task_id": task_id}
