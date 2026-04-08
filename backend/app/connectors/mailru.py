import re
import logging
from urllib.parse import urlparse

import httpx

from app.connectors.base import BaseConnector, ConnectorError, DownloadInfo

logger = logging.getLogger(__name__)

MAIL_RU_API = "https://cloud.mail.ru/api/v2"


class MailRuConnector(BaseConnector):

    async def get_download_info(self, url: str) -> DownloadInfo:
        if "cloud.mail.ru" not in url:
            raise ConnectorError(f"Not a cloud.mail.ru URL: {url}")

        parsed = urlparse(url)
        match = re.search(r'/public/(.+)', parsed.path)
        if not match:
            raise ConnectorError(f"Cannot extract weblink from URL: {url}")

        weblink = match.group(1).rstrip("/")

        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        ) as client:
            # 1) Visit public page to establish session cookies
            page_resp = await client.get(url)
            if page_resp.status_code == 404:
                raise ConnectorError(f"File not found: {url}")
            if page_resp.status_code >= 400:
                raise ConnectorError(f"Cannot access file (HTTP {page_resp.status_code}): {url}")

            html = page_resp.text

            # 2) Extract file metadata from embedded JSON in HTML
            filename = None
            size_bytes = None

            name_match = re.search(r'"name"\s*:\s*"([^"]{1,500})"', html)
            if name_match:
                filename = name_match.group(1)

            size_match = re.search(r'"size"\s*:\s*(\d+)', html)
            if size_match:
                size_bytes = int(size_match.group(1))

            # 3) Get CSRF token (now with cookies from step 1)
            csrf_token = ""

            csrf_html_match = re.search(r'"csrf"\s*:\s*"([^"]+)"', html)
            if csrf_html_match:
                csrf_token = csrf_html_match.group(1)

            if not csrf_token:
                try:
                    csrf_resp = await client.get(f"{MAIL_RU_API}/tokens/csrf")
                    if csrf_resp.status_code == 200:
                        csrf_token = csrf_resp.json().get("body", {}).get("token", "")
                except Exception as e:
                    logger.warning(f"CSRF API failed: {e}")

            if not csrf_token:
                raise ConnectorError(f"Cannot authenticate with cloud.mail.ru for: {url}")

            # 4) Get file info via API
            try:
                file_resp = await client.get(
                    f"{MAIL_RU_API}/file",
                    params={"weblink": weblink, "token": csrf_token},
                )
                if file_resp.status_code == 200:
                    body = file_resp.json().get("body", {})
                    if not filename:
                        filename = body.get("name")
                    if size_bytes is None:
                        size_bytes = body.get("size")
                    if body.get("type") == "folder":
                        raise ConnectorError(
                            "This link points to a folder. Please share a direct file link."
                        )
                elif file_resp.status_code == 404:
                    raise ConnectorError(f"File not found: {url}")
            except ConnectorError:
                raise
            except Exception as e:
                logger.warning(f"File info API failed: {e}")

            # 5) Get download URL via dispatcher
            direct_url = None
            try:
                disp_resp = await client.get(
                    f"{MAIL_RU_API}/dispatcher",
                    params={"token": csrf_token},
                )
                if disp_resp.status_code == 200:
                    disp_body = disp_resp.json().get("body", {})
                    weblink_get = disp_body.get("weblink_get", [])
                    if weblink_get:
                        base = weblink_get[0].get("url", "").rstrip("/")
                        direct_url = f"{base}/{weblink}"
            except Exception as e:
                logger.warning(f"Dispatcher API failed: {e}")

            if not direct_url:
                raise ConnectorError(f"Failed to resolve download URL for: {url}")

            if not filename:
                parts = weblink.split("/")
                filename = parts[-1] if parts else "download"

            # 6) Verify download URL and get content-type
            content_type = "application/octet-stream"
            try:
                head_resp = await client.head(direct_url)
                if head_resp.status_code >= 400:
                    head_resp = await client.get(
                        direct_url, headers={"Range": "bytes=0-0"}
                    )
                ct = head_resp.headers.get("content-type", "").split(";")[0]
                if ct and ct != "text/html":
                    content_type = ct
                if size_bytes is None:
                    cl = head_resp.headers.get("content-length")
                    if cl:
                        size_bytes = int(cl)
            except Exception as e:
                logger.warning(f"Could not verify direct URL: {e}")

            return DownloadInfo(
                direct_url=direct_url,
                filename=filename,
                size_bytes=size_bytes,
                content_type=content_type,
            )
