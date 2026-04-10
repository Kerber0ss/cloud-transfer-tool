from enum import Enum
from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class Provider(str, Enum):
    MAIL_RU = "mail_ru"
    MEGA = "mega"
    DROPBOX = "dropbox"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class UploadJobCreate(BaseModel):
    source_url: str
    provider: Provider
    gdrive_folder_id: str
    gdrive_folder_name: str
    filename: Optional[str] = None


class UploadJobResponse(BaseModel):
    task_id: str
    status: TaskStatus
    filename: str
    source_provider: Provider
    gdrive_folder_name: str
    created_at: datetime
    progress_pct: int = 0
    bytes_transferred: int = 0
    total_bytes: Optional[int] = None
    error: Optional[str] = None


class TaskProgressUpdate(BaseModel):
    task_id: str
    status: TaskStatus
    progress_pct: int = 0
    bytes_transferred: int = 0
    total_bytes: Optional[int] = None
    error: Optional[str] = None


class GoogleDriveAccount(BaseModel):
    connected: bool
    email: Optional[str] = None
    name: Optional[str] = None
    expired: Optional[bool] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
