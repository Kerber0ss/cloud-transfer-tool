from app.models import Provider
from app.connectors.base import BaseConnector, ConnectorError
from app.connectors.mailru import MailRuConnector


_CONNECTORS: dict[Provider, type[BaseConnector]] = {
    Provider.MAIL_RU: MailRuConnector,
}


def get_connector(provider: Provider) -> BaseConnector:
    """Return connector instance for the given provider."""
    connector_class = _CONNECTORS.get(provider)
    if not connector_class:
        raise ConnectorError(f"No connector available for provider: {provider}. Not yet implemented.")
    return connector_class()
