from abc import ABC, abstractmethod
from typing import Optional
from pydantic import BaseModel


class ConnectorError(Exception):
    """Raised when connector cannot resolve download URL."""
    pass


class DownloadInfo(BaseModel):
    direct_url: str
    filename: str
    size_bytes: Optional[int] = None
    content_type: str = "application/octet-stream"


class BaseConnector(ABC):
    @abstractmethod
    async def get_download_info(self, url: str) -> DownloadInfo:
        """Resolve public share URL to direct download URL + metadata.

        Args:
            url: Public share URL (e.g. https://cloud.mail.ru/public/XXXX)

        Returns:
            DownloadInfo with direct download URL and file metadata

        Raises:
            ConnectorError: If URL is invalid, file not found, or access denied
        """
        pass
