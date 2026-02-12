from __future__ import annotations

from dataclasses import dataclass

from app.core.config import AppConfig
from app.services.backend_client import BackendAPIError, BackendClient
from app.services.admin_service import AdminUser


@dataclass
class ActionEntry:
    action_id: int
    created_at: str
    admin_id: int | None
    admin_username: str | None
    action_type: str
    title: str
    details: str


class ActionLogService:
    def __init__(self, db_path=None) -> None:
        _ = db_path
        config = AppConfig.load()
        self._client = BackendClient(config.backend_url)

    def log_action(
        self,
        action_type: str,
        title: str,
        details: str,
        admin: AdminUser | None = None,
    ) -> None:
        try:
            self._client.post(
                "/api/v1/actions",
                json_body={
                    "action_type": action_type,
                    "title": title,
                    "details": details,
                    "admin_username": admin.username if admin else None,
                },
            )
        except BackendAPIError:
            # Logging should not break user workflows.
            return

    def list_actions(
        self,
        limit: int = 200,
        offset: int = 0,
        search: str | None = None,
    ) -> list[ActionEntry]:
        try:
            payload = self._client.get(
                "/api/v1/actions",
                params={
                    "limit": limit,
                    "offset": offset,
                    "search": search or "",
                },
            )
        except BackendAPIError:
            return []
        rows = payload.get("items", []) if isinstance(payload, dict) else []
        result: list[ActionEntry] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            result.append(
                ActionEntry(
                    action_id=int(row.get("action_id", 0) or 0),
                    created_at=str(row.get("created_at", "")),
                    admin_id=None,
                    admin_username=(
                        None
                        if row.get("admin_username") in {None, ""}
                        else str(row.get("admin_username"))
                    ),
                    action_type=str(row.get("action_type", "")),
                    title=str(row.get("title", "")),
                    details=str(row.get("details", "")),
                )
            )
        return result

    def count_actions(self, search: str | None = None) -> int:
        try:
            payload = self._client.get(
                "/api/v1/actions/count",
                params={"search": search or ""},
            )
        except BackendAPIError:
            return 0
        return int(payload.get("count", 0) if isinstance(payload, dict) else 0)
