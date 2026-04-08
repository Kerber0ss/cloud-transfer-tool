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
            # Visit page first — cookies from this response are required for all API calls
            page_resp = await client.get(url)
            if page_resp.status_code == 404:
                raise ConnectorError(f"File not found: {url}")
            if page_resp.status_code >= 400:
                raise ConnectorError(f"Cannot access file (HTTP {page_resp.status_code}): {url}")

            # Dispatcher gives us the download server (works with cookies, no CSRF needed)
            disp_resp = await client.get(f"{MAIL_RU_API}/dispatcher")
            if disp_resp.status_code != 200:
                raise ConnectorError(f"Cannot get download server for: {url}")

            disp_body = disp_resp.json().get("body", {})
            weblink_get = disp_body.get("weblink_get", [])
            if not weblink_get:
                raise ConnectorError(f"No download server available for: {url}")

            download_base = weblink_get[0].get("url", "").rstrip("/")

            # File/folder metadata
            file_resp = await client.get(
                f"{MAIL_RU_API}/file",
                params={"weblink": weblink},
            )
            if file_resp.status_code == 404:
                raise ConnectorError(f"File not found: {url}")
            if file_resp.status_code != 200:
                raise ConnectorError(f"Cannot get file info (HTTP {file_resp.status_code}): {url}")

            body = file_resp.json().get("body", {})
            item_type = body.get("type")
            filename = body.get("name")
            size_bytes = body.get("size")

            # Folders: resolve to the single file inside
            if item_type == "folder":
                folder_resp = await client.get(
                    f"{MAIL_RU_API}/folder",
                    params={"weblink": weblink},
                )
                if folder_resp.status_code != 200:
                    raise ConnectorError(f"Cannot list folder contents: {url}")

                items = folder_resp.json().get("body", {}).get("list", [])
                files = [f for f in items if f.get("type") == "file"]

                if not files:
                    raise ConnectorError("Folder is empty")
                if len(files) > 1:
                    raise ConnectorError(
                        f"Folder contains {len(files)} files. "
                        "Please share a direct link to a single file."
                    )

                file_item = files[0]
                filename = file_item.get("name", filename)
                size_bytes = file_item.get("size")
                file_weblink = file_item.get("weblink", f"{weblink}/{filename}")
                direct_url = f"{download_base}/{file_weblink}"
            else:
                direct_url = f"{download_base}/{weblink}"

            if not filename:
                parts = weblink.split("/")
                filename = parts[-1] if parts else "download"

            content_type = "application/octet-stream"
            try:
                head_resp = await client.head(direct_url)
                if head_resp.status_code >= 400:
                    head_resp = await client.get(
                        direct_url, headers={"Range": "bytes=0-0"}
                    )
                if head_resp.status_code < 400:
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
