import json
import asyncio
import logging
from typing import AsyncGenerator

import redis as redis_lib
from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.config import settings
from app.auth.app_auth import get_current_user
from app.models import TaskProgressUpdate, TaskStatus
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def get_redis():
    return redis_lib.from_url(settings.redis_url, decode_responses=True)


def celery_state_to_task_status(state: str) -> TaskStatus:
    mapping = {
        "PENDING": TaskStatus.PENDING,
        "STARTED": TaskStatus.RUNNING,
        "PROGRESS": TaskStatus.RUNNING,
        "SUCCESS": TaskStatus.SUCCESS,
        "FAILURE": TaskStatus.FAILED,
        "REVOKED": TaskStatus.CANCELLED,
    }
    return mapping.get(state, TaskStatus.PENDING)


def get_task_progress(task_id: str) -> TaskProgressUpdate:
    result = AsyncResult(task_id, app=celery_app)
    state = result.state
    status = celery_state_to_task_status(state)

    meta = {}
    if state == "PROGRESS" and isinstance(result.info, dict):
        meta = result.info
    elif state == "SUCCESS" and isinstance(result.result, dict):
        meta = result.result
    elif state == "FAILURE":
        meta = {"error": str(result.result)}

    return TaskProgressUpdate(
        task_id=task_id,
        status=status,
        progress_pct=meta.get("progress_pct", 0),
        bytes_transferred=meta.get("bytes_transferred", 0),
        total_bytes=meta.get("total_bytes"),
        error=meta.get("error"),
    )


@router.get("/", response_model=list)
async def list_tasks(current_user: str = Depends(get_current_user)):
    r = get_redis()
    task_ids = r.lrange(f"task_list:{current_user}", 0, -1)
    tasks = []
    for task_id in task_ids:
        try:
            progress = get_task_progress(task_id)
            meta_raw = r.get(f"task_meta:{task_id}")
            meta = json.loads(meta_raw) if meta_raw else {}
            tasks.append({
                "task_id": task_id,
                "status": progress.status,
                "progress_pct": progress.progress_pct,
                "bytes_transferred": progress.bytes_transferred,
                "total_bytes": progress.total_bytes,
                "error": progress.error,
                "filename": meta.get("filename", "unknown"),
                "source_url": meta.get("source_url", ""),
                "provider": meta.get("provider", ""),
                "gdrive_folder_name": meta.get("gdrive_folder_name", ""),
                "created_at": meta.get("created_at", ""),
            })
        except Exception as e:
            logger.warning(f"Could not get task {task_id}: {e}")
    return tasks


@router.delete("/")
async def clear_history(current_user: str = Depends(get_current_user)):
    r = get_redis()
    task_ids = r.lrange(f"task_list:{current_user}", 0, -1)
    for task_id in task_ids:
        r.delete(f"task_meta:{task_id}")
        r.delete(f"celery-task-meta-{task_id}")
    r.delete(f"task_list:{current_user}")
    return {"deleted": len(task_ids)}


@router.get("/{task_id}/status", response_model=TaskProgressUpdate)
async def task_status(task_id: str, current_user: str = Depends(get_current_user)):
    """Return current status of a task."""
    return get_task_progress(task_id)


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str, current_user: str = Depends(get_current_user)):
    """Cancel a running or pending task."""
    result = AsyncResult(task_id, app=celery_app)
    result.revoke(terminate=True, signal="SIGTERM")
    return {"message": f"Task {task_id} cancellation requested"}


async def sse_generator(task_id: str) -> AsyncGenerator[str, None]:
    """Generate SSE events polling Celery task state."""
    while True:
        try:
            progress = get_task_progress(task_id)
            data = progress.model_dump_json()
            yield f"data: {data}\n\n"

            if progress.status in (TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED):
                break
        except Exception as e:
            error_data = json.dumps({"error": str(e)})
            yield f"data: {error_data}\n\n"
            break

        await asyncio.sleep(1.5)


from typing import Optional as Opt
from fastapi import Query

@router.get("/{task_id}/events")
async def task_events(
    task_id: str,
    token: Opt[str] = Query(None),
    current_user: Opt[str] = None,
):
    """SSE endpoint — accepts Bearer token or ?token= query param."""
    from app.auth.app_auth import get_current_user as _get_user, ALGORITHM
    from jose import jwt, JWTError
    from app.config import settings as _settings
    
    
    if token:
        try:
            payload = jwt.decode(token, _settings.secret_key, algorithms=[ALGORITHM])
            current_user = payload.get("sub")
        except JWTError:
            pass
    
    if not current_user:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    return StreamingResponse(
        sse_generator(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
