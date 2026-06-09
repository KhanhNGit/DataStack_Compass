"""DataStack Compass — Ingestion connectors package."""

from ingestion.connectors.base_connector import (
    BaseConnector,
    ConnectorError,
    GitHubReleaseConnector,
    HttpConnector,
)

__all__ = [
    "BaseConnector",
    "ConnectorError",
    "GitHubReleaseConnector",
    "HttpConnector",
]
