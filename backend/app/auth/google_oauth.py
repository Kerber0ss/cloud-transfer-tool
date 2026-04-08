import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
import redis as redis_lib

from app.config import settings
from app.auth.app_auth import get_current_user
from app.models import GoogleDriveAccount

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth/google", tags=["google-auth"])

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid",
]


def get_redis():
    return redis_lib.from_url(settings.redis_url, decode_responses=True)


def get_flow() -> Flow:
    client_config = {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_redirect_uri],
        }
    }
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=settings.google_redirect_uri,
    )
    return flow


def save_tokens_to_redis(username: str, token_data: dict):
    r = get_redis()
    r.set(f"gdrive_token:{username}", json.dumps(token_data))


def load_tokens_from_redis(username: str) -> dict | None:
    r = get_redis()
    data = r.get(f"gdrive_token:{username}")
    if data:
        return json.loads(data)
    return None


def delete_tokens_from_redis(username: str):
    r = get_redis()
    r.delete(f"gdrive_token:{username}")


async def get_google_credentials(username: str) -> Credentials | None:
    """Load and auto-refresh Google credentials from Redis."""
    token_data = load_tokens_from_redis(username)
    if not token_data:
        return None

    creds = Credentials(
        token=token_data.get("access_token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=SCOPES,
    )

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            token_data["access_token"] = creds.token
            save_tokens_to_redis(username, token_data)
        except Exception as e:
            logger.error(f"Failed to refresh Google token for {username}: {e}")
            return None

    return creds


@router.get("")
async def google_auth_redirect(current_user: str = Depends(get_current_user)):
    """Redirect user to Google OAuth2 consent screen."""
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth2 not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env",
        )
    flow = get_flow()
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=current_user,
    )
    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def google_auth_callback(code: str, state: str):
    """Handle Google OAuth2 callback, exchange code for tokens."""
    username = state

    flow = get_flow()
    try:
        flow.fetch_token(code=code)
    except Exception as e:
        logger.error(f"Failed to fetch Google token: {e}")
        return RedirectResponse(url=f"{settings.frontend_url}/?google_error=true")

    creds = flow.credentials

    email = None
    name = None
    try:
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {creds.token}"},
            )
            if resp.status_code == 200:
                user_info = resp.json()
                email = user_info.get("email")
                name = user_info.get("name")
    except Exception as e:
        logger.warning(f"Could not fetch user info: {e}")

    token_data = {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "email": email,
        "name": name,
    }
    save_tokens_to_redis(username, token_data)

    return RedirectResponse(url=f"{settings.frontend_url}/?google_connected=true")


@router.get("/status", response_model=GoogleDriveAccount)
async def google_status(current_user: str = Depends(get_current_user)):
    """Return Google Drive connection status for current user."""
    token_data = load_tokens_from_redis(current_user)
    if not token_data:
        return GoogleDriveAccount(connected=False)
    return GoogleDriveAccount(
        connected=True,
        email=token_data.get("email"),
        name=token_data.get("name"),
    )


@router.delete("/disconnect")
async def google_disconnect(current_user: str = Depends(get_current_user)):
    """Remove Google Drive tokens from Redis."""
    delete_tokens_from_redis(current_user)
    return {"message": "Google Drive disconnected"}


@router.get("/picker-token")
async def google_picker_token(current_user: str = Depends(get_current_user)):
    """Return Google access token for use with Google Picker API."""
    creds = await get_google_credentials(current_user)
    if not creds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google Drive not connected",
        )
    return {"access_token": creds.token}
