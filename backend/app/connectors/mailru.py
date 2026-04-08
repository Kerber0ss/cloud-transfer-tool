import re
import logging
from urllib.parse import urlparse

import httpx

from app.connectors.base import BaseConnector, ConnectorError, DownloadInfo

logger = logging.getLogger(__name__)

MAIL_RU_API = "https://cloud.mail.ru/api/v2"
MAIL_RU_HOST = "https://cloud.mail.ru"


class MailRuConnector(BaseConnector):

    async def get_download_info(self, url: str) -> DownloadInfo:
        if "cloud.mail.ru" not in url:
            raise ConnectorError(f"Not a cloud.mail.ru URL: {url}")

        parsed = urlparse(url)
        match = re.search(r'/public/(.+)', parsed.path)
        if not match:
            raise ConnectorError(f"Cannot extract weblink from URL: {url}")

        weblink = match.group(1)

        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; CloudTransfer/1.0)",
                "Accept": "application/json",
            }
        ) as client:
            # CSRF token is required by mail.ru API before any data request
            try:
                csrf_resp = await client.get(f"{MAIL_RU_API}/tokens/csrf")
                csrf_resp.raise_for_status()
                csrf_token = csrf_resp.json().get("body", {}).get("token", "")
            except Exception as e:
                logger.warning(f"Could not get CSRF token: {e}, trying direct approach")
                csrf_token = ""

            direct_url = None
            filename = None
            size_bytes = None

            if csrf_token:
                try:
                    api_resp = await client.get(
                        f"{MAIL_RU_API}/file",
                        params={"weblink": weblink, "token": csrf_token},
                    )
                    if api_resp.status_code == 200:
                        data = api_resp.json()
                        body = data.get("body", {})

                        weblink_get = body.get("weblink_get", [])
                        if weblink_get:
                            direct_url = weblink_get[0].get("url", "").rstrip("/") + "/" + weblink

                        filename = body.get("name")
                        size_bytes = body.get("size")
                    elif api_resp.status_code == 404:
                        raise ConnectorError(f"File not found: {url}")
                    elif api_resp.status_code == 403:
                        raise ConnectorError(f"Access denied: {url}")
                except ConnectorError:
                    raise
                except Exception as e:
                    logger.warning(f"API approach failed: {e}")

            if not direct_url:
                try:
                    # mail.ru returns 405 for HEAD on public pages, use GET with stream
                    async with client.stream("GET", url) as get_resp:
                        if get_resp.status_code == 404:
                            raise ConnectorError(f"File not found: {url}")
                        if get_resp.status_code == 403:
                            raise ConnectorError(f"Access denied: {url}")
                        if get_resp.status_code >= 400:
                            raise ConnectorError(f"Cannot access file (HTTP {get_resp.status_code}): {url}")

                        final_url = str(get_resp.url)
                        resp_ct = get_resp.headers.get("content-type", "")
                        if "cloclo" in final_url or ("cloud.mail.ru" in final_url and "text/html" not in resp_ct):
                            direct_url = final_url
                        else:
                            direct_url = f"https://cloud.mail.ru/attachments/{weblink}"
                except ConnectorError:
                    raise
                except Exception as e:
                    logger.warning(f"GET fallback failed: {e}")
                    raise ConnectorError(f"Cannot resolve download URL for: {url}") from e

            if not direct_url:
                raise ConnectorError(f"Failed to resolve direct download URL for: {url}")

            if not filename:
                parts = weblink.rstrip("/").split("/")
                filename = parts[-1] if parts else "download"

            content_type = "application/octet-stream"
            try:
                head_direct = await client.head(direct_url)
                content_type = head_direct.headers.get("content-type", "application/octet-stream").split(";")[0]
                if content_type == "text/html":
                    raise ConnectorError(f"File not found or not accessible: {url}")
                if size_bytes is None:
                    cl = head_direct.headers.get("content-length")
                    if cl:
                        size_bytes = int(cl)
            except ConnectorError:
                raise
            except Exception as e:
                logger.warning(f"Could not get metadata from direct URL: {e}")

            return DownloadInfo(
                direct_url=direct_url,
                filename=filename,
                size_bytes=size_bytes,
                content_type=content_type,
            )
