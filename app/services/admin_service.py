from __future__ import annotations

from dataclasses import dataclass

from app.core.config import AppConfig
from app.services.backend_client import BackendAPIError, BackendClient


@dataclass(frozen=True)
class AdminUser:
    admin_id: int
    username: str
    role: str
    auto_lock_minutes: int


class AdminService:
    def __init__(self, db_path=None) -> None:
        _ = db_path
        config = AppConfig.load()
        self._client = BackendClient(config.backend_url)

    def authenticate(self, username: str, password: str) -> AdminUser | None:
        if not username.strip() or not password:
            return None
        try:
            payload = self._client.post(
                "/api/v1/admins/authenticate",
                json_body={"username": username, "password": password},
            )
        except BackendAPIError:
            return None
        return self._to_admin(payload)

    def list_admins(self) -> list[AdminUser]:
        try:
            payload = self._client.get("/api/v1/admins")
        except BackendAPIError as exc:
            raise ValueError(str(exc)) from exc
        items = payload.get("items", []) if isinstance(payload, dict) else []
        return [self._to_admin(item) for item in items if isinstance(item, dict)]

    def create_admin(
        self,
        username: str,
        password: str,
        role: str,
        auto_lock_minutes: int = 1,
        admin_username: str | None = None,
    ) -> AdminUser:
        _ = admin_username
        try:
            payload = self._client.post(
                "/api/v1/admins",
                json_body={
                    "username": username,
                    "password": password,
                    "role": role,
                    "auto_lock_minutes": auto_lock_minutes,
                },
            )
        except BackendAPIError as exc:
            raise ValueError(str(exc)) from exc
        return self._to_admin(payload)

    def update_password(
        self,
        admin_id: int,
        new_password: str,
        admin_username: str | None = None,
    ) -> None:
        _ = admin_username
        try:
            self._client.patch(
                f"/api/v1/admins/{admin_id}/password",
                json_body={"password": new_password},
            )
        except BackendAPIError as exc:
            raise ValueError(str(exc)) from exc

    def update_auto_lock(
        self,
        admin_id: int,
        minutes: int,
        admin_username: str | None = None,
    ) -> None:
        _ = admin_username
        try:
            self._client.patch(
                f"/api/v1/admins/{admin_id}/auto-lock",
                json_body={"auto_lock_minutes": int(minutes)},
            )
        except BackendAPIError as exc:
            raise ValueError(str(exc)) from exc

    def delete_admin(
        self, admin_id: int, admin_username: str | None = None
    ) -> None:
        _ = admin_username
        try:
            self._client.delete(f"/api/v1/admins/{admin_id}")
        except BackendAPIError as exc:
            raise ValueError(str(exc)) from exc

    def get_admin_by_id(self, admin_id: int) -> AdminUser | None:
        try:
            payload = self._client.get(f"/api/v1/admins/{admin_id}")
        except BackendAPIError:
            return None
        if not isinstance(payload, dict):
            return None
        return self._to_admin(payload)

    @staticmethod
    def _to_admin(raw: dict) -> AdminUser:
        return AdminUser(
            admin_id=int(raw.get("admin_id", 0) or 0),
            username=str(raw.get("username", "")),
            role=str(raw.get("role", "employee")),
            auto_lock_minutes=int(raw.get("auto_lock_minutes", 1) or 1),
        )
