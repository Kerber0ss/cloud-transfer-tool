from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    
    # App auth
    app_username: str = "admin"
    app_password: str = "changeme"
    secret_key: str = "insecure-dev-secret-key-change-in-production"
    
    # Google OAuth2
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/auth/google/callback"
    frontend_url: str = "http://localhost:3000"
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"
    
    # Celery
    celery_concurrency: int = 4

settings = Settings()
