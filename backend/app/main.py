from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.auth.app_auth import router as auth_router
from app.auth.google_oauth import router as google_router
from app.api.tasks import router as tasks_router
from app.api.upload import router as upload_router

app = FastAPI(title="Cloud Transfer API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(google_router)
app.include_router(tasks_router)
app.include_router(upload_router)

@app.get("/health")
async def health():
    """Health check — tests Redis and Celery connectivity."""
    import redis as redis_lib
    from app.config import settings
    
    # Check Redis
    redis_status = "error"
    try:
        r = redis_lib.from_url(settings.redis_url, socket_connect_timeout=2)
        r.ping()
        redis_status = "ok"
    except Exception:
        redis_status = "error"
    
    # Check Celery (inspect ping with short timeout)
    celery_status = "unknown"
    try:
        from app.tasks.celery_app import celery_app
        inspect = celery_app.control.inspect(timeout=2.0)
        pong = inspect.ping()
        celery_status = "ok" if pong else "no_workers"
    except Exception:
        celery_status = "error"
    
    overall = "ok" if redis_status == "ok" else "degraded"
    
    return {
        "status": overall,
        "redis": redis_status,
        "celery": celery_status,
    }
