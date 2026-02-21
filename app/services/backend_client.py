from __future__ import annotations

import os
import threading
from typing import Any

import requests
from requests.adapters import HTTPAdapter


class BackendAPIError(RuntimeError):
    pass


class BackendClient:
    _pool_guard = threading.RLock()
    _session_pool: dict[str, requests.Session] = {}
    _session_locks: dict[str, threading.RLock] = {}

    def __init__(self, base_url: str | None = None) -> None:
        configured = (base_url or "").strip()
        env_value = os.getenv("REZA_BACKEND_URL", "").strip()
        self.base_url = (
            env_value or configured or "http://127.0.0.1:8080"
        ).rstrip("/")
        self._timeout = (8, 120)
        self._session, self._session_lock = self._get_shared_session(
            self.base_url
        )

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
            with self._session_lock:
                response = self._session.request(
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

    @classmethod
    def _get_shared_session(
        cls, base_url: str
    ) -> tuple[requests.Session, threading.RLock]:
        with cls._pool_guard:
            session = cls._session_pool.get(base_url)
            session_lock = cls._session_locks.get(base_url)
            if session is None or session_lock is None:
                session = requests.Session()
                adapter = HTTPAdapter(
                    pool_connections=20,
                    pool_maxsize=20,
                    max_retries=0,
                )
                session.mount("http://", adapter)
                session.mount("https://", adapter)
                session.headers.update({"Accept": "application/json"})
                session_lock = threading.RLock()
                cls._session_pool[base_url] = session
                cls._session_locks[base_url] = session_lock
            return session, session_lock
