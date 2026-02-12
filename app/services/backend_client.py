from __future__ import annotations

import os
from typing import Any

import requests


class BackendAPIError(RuntimeError):
    pass


class BackendClient:
    def __init__(self, base_url: str | None = None) -> None:
        configured = (base_url or "").strip()
        env_value = os.getenv("REZA_BACKEND_URL", "").strip()
        self.base_url = (
            env_value or configured or "http://127.0.0.1:8080"
        ).rstrip("/")
        self._timeout = (8, 120)

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._request("GET", path, params=params)

    def post(
        self,
        path: str,
        json_body: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> Any:
        return self._request("POST", path, json_body=json_body, files=files)

    def patch(self, path: str, json_body: dict[str, Any] | None = None) -> Any:
        return self._request("PATCH", path, json_body=json_body)

    def delete(self, path: str) -> Any:
        return self._request("DELETE", path)

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        try:
            response = requests.request(
                method=method,
                url=url,
                params=params,
                json=json_body,
                files=files,
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise BackendAPIError(
                f"درخواست به بک‌اند ناموفق بود: {exc}"
            ) from exc

        if response.status_code == 204:
            return None

        payload: Any
        try:
            payload = response.json()
        except ValueError:
            payload = response.text

        if response.status_code >= 400:
            if isinstance(payload, dict):
                message = str(payload.get("error") or payload)
            else:
                message = str(payload)
            raise BackendAPIError(message)

        return payload
