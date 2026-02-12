from __future__ import annotations

from app.core.config import AppConfig
from app.services.backend_client import BackendAPIError, BackendClient


class BasalamIdStore:
    def __init__(self, db_path=None) -> None:
        _ = db_path
        config = AppConfig.load()
        self._client = BackendClient(config.backend_url)

    def fetch_existing_ids(self, ids: list[str]) -> set[str]:
        if not ids:
            return set()
        try:
            payload = self._client.post(
                "/api/v1/basalam/order-ids/check",
                json_body={"ids": ids},
            )
        except BackendAPIError:
            return set()
        existing = (
            payload.get("existing_ids", []) if isinstance(payload, dict) else []
        )
        return {str(item) for item in existing}

    def store_ids(self, ids: list[str]) -> None:
        if not ids:
            return
        try:
            self._client.post(
                "/api/v1/basalam/order-ids/store",
                json_body={"ids": ids},
            )
        except BackendAPIError:
            return
