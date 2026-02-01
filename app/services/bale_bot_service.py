from __future__ import annotations

import io
import json
import logging
from pathlib import Path
from typing import Any, Mapping

import requests

DEFAULT_BASE_URL = "https://tapi.bale.ai"
REQUEST_FORMAT_JSON = "json"
REQUEST_FORMAT_FORM = "form"
REQUEST_FORMAT_QUERY = "query"
REQUEST_FORMAT_MULTIPART = "multipart"

logger = logging.getLogger(__name__)


class BaleBotClient:
    def __init__(
        self,
        token: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = 30,
    ) -> None:
        token_value = token.strip()
        if not token_value:
            raise ValueError("Token is required.")
        self.token = token_value
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._logger = logging.getLogger(self.__class__.__name__)

    def build_api_url(self, method_name: str) -> str:
        method_value = method_name.strip()
        if not method_value:
            raise ValueError("Method name is required.")
        return f"{self.base_url}/bot{self.token}/{method_value}"

    def build_file_url(self, file_path: str) -> str:
        if not file_path:
            raise ValueError("File path is required.")
        clean_path = str(file_path).lstrip("/")
        return f"{self.base_url}/file/bot{self.token}/{clean_path}"

    def request(
        self,
        method_name: str,
        payload: Mapping[str, Any] | None = None,
        http_method: str = "POST",
        request_format: str = REQUEST_FORMAT_JSON,
        files: Mapping[str, Any] | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        url = self.build_api_url(method_name)
        method_value = http_method.strip().upper()
        if method_value not in {"GET", "POST"}:
            raise ValueError("HTTP method must be GET or POST.")

        timeout_value = timeout if timeout is not None else self.timeout

        if method_value == "GET":
            params = self._prepare_payload(payload, use_json=False)
            response = requests.get(url, params=params, timeout=timeout_value)
        else:
            response = self._post_request(
                url,
                payload=payload,
                request_format=request_format,
                files=files,
                timeout=timeout_value,
            )

        response.raise_for_status()
        try:
            return response.json()
        except ValueError as exc:  # noqa: BLE001
            self._logger.exception("Bale response was not valid JSON")
            raise ValueError("Bale response was not valid JSON.") from exc

    def send_message(
        self,
        chat_id: str | int,
        text: str,
        reply_to_message_id: int | None = None,
        reply_markup: Mapping[str, Any] | None = None,
        request_format: str = REQUEST_FORMAT_JSON,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "reply_to_message_id": reply_to_message_id,
            "reply_markup": reply_markup,
        }
        return self.request(
            "sendMessage",
            payload=payload,
            http_method="POST",
            request_format=request_format,
            timeout=timeout,
        )

    def send_document(
        self,
        chat_id: str | int,
        document: Any,
        caption: str | None = None,
        reply_to_message_id: int | None = None,
        reply_markup: Mapping[str, Any] | None = None,
        request_format: str | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        payload = {
            "chat_id": chat_id,
            "caption": caption,
            "reply_to_message_id": reply_to_message_id,
            "reply_markup": reply_markup,
        }

        files: dict[str, Any] | None = None
        opened_file = None

        try:
            document_field, files, opened_file = self._prepare_document(
                document
            )
            if document_field is not None:
                payload["document"] = document_field

            format_value = request_format
            if format_value is None:
                format_value = (
                    REQUEST_FORMAT_MULTIPART if files else REQUEST_FORMAT_FORM
                )
            elif (
                files
                and format_value.strip().lower() != REQUEST_FORMAT_MULTIPART
            ):
                raise ValueError(
                    "File uploads require request_format='multipart'."
                )

            return self.request(
                "sendDocument",
                payload=payload,
                http_method="POST",
                request_format=format_value,
                files=files,
                timeout=timeout,
            )
        finally:
            if opened_file is not None:
                opened_file.close()

    def get_file(
        self,
        file_id: str,
        request_format: str = REQUEST_FORMAT_QUERY,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        payload = {"file_id": file_id}
        return self.request(
            "getFile",
            payload=payload,
            http_method="GET",
            request_format=request_format,
            timeout=timeout,
        )

    def get_updates(
        self,
        offset: int | None = None,
        limit: int | None = None,
        timeout_seconds: int | None = None,
        request_format: str = REQUEST_FORMAT_QUERY,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        payload = {
            "offset": offset,
            "limit": limit,
            "timeout": timeout_seconds,
        }
        return self.request(
            "getUpdates",
            payload=payload,
            http_method="GET",
            request_format=request_format,
            timeout=timeout,
        )

    def get_updates_with_next_offset(
        self,
        offset: int | None = None,
        limit: int | None = None,
        timeout_seconds: int | None = None,
        request_format: str = REQUEST_FORMAT_QUERY,
        timeout: int | None = None,
    ) -> tuple[dict[str, Any], int | None]:
        response = self.get_updates(
            offset=offset,
            limit=limit,
            timeout_seconds=timeout_seconds,
            request_format=request_format,
            timeout=timeout,
        )
        return response, self.next_update_offset(response, offset)

    @staticmethod
    def extract_updates(
        response: Mapping[str, Any] | None,
    ) -> list[dict[str, Any]]:
        if not response or not response.get("ok"):
            return []
        result = response.get("result")
        if not isinstance(result, list):
            return []
        return [item for item in result if isinstance(item, dict)]

    @classmethod
    def next_update_offset(
        cls,
        response: Mapping[str, Any] | None,
        current_offset: int | None = None,
    ) -> int | None:
        updates = cls.extract_updates(response)
        if not updates:
            return current_offset
        update_ids = [
            item.get("update_id")
            for item in updates
            if isinstance(item.get("update_id"), int)
        ]
        if not update_ids:
            return current_offset
        return max(update_ids) + 1

    def _post_request(
        self,
        url: str,
        payload: Mapping[str, Any] | None,
        request_format: str,
        files: Mapping[str, Any] | None,
        timeout: int,
    ) -> requests.Response:
        format_value = request_format.strip().lower()
        if format_value == REQUEST_FORMAT_JSON:
            body = self._prepare_payload(payload, use_json=True)
            return requests.post(url, json=body, timeout=timeout)
        if format_value == REQUEST_FORMAT_FORM:
            body = self._prepare_payload(payload, use_json=False)
            return requests.post(url, data=body, timeout=timeout)
        if format_value == REQUEST_FORMAT_QUERY:
            params = self._prepare_payload(payload, use_json=False)
            return requests.post(url, params=params, timeout=timeout)
        if format_value == REQUEST_FORMAT_MULTIPART:
            body = self._prepare_payload(payload, use_json=False)
            return requests.post(
                url, data=body, files=files or {}, timeout=timeout
            )
        raise ValueError(
            "request_format must be json, form, query, or multipart."
        )

    def _prepare_payload(
        self,
        payload: Mapping[str, Any] | None,
        use_json: bool,
    ) -> dict[str, Any]:
        if not payload:
            return {}
        prepared: dict[str, Any] = {}
        for key, value in payload.items():
            if value is None:
                continue
            if key == "reply_markup":
                prepared[key] = self._prepare_reply_markup(value, use_json)
                continue
            if use_json:
                prepared[key] = value
            elif isinstance(value, (dict, list)):
                prepared[key] = json.dumps(value, ensure_ascii=False)
            else:
                prepared[key] = value
        return prepared

    @staticmethod
    def _prepare_reply_markup(value: Any, use_json: bool) -> Any:
        if isinstance(value, str):
            return value
        if use_json:
            return value
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _prepare_document(
        document: Any,
    ) -> tuple[Any | None, dict[str, Any] | None, Any | None]:
        if isinstance(document, Path):
            handle = document.open("rb")
            return None, {"document": (document.name, handle)}, handle

        if isinstance(document, (bytes, bytearray)):
            handle = io.BytesIO(document)
            return None, {"document": ("document", handle)}, handle

        if isinstance(document, str):
            path = Path(document)
            if path.exists() and path.is_file():
                handle = path.open("rb")
                return None, {"document": (path.name, handle)}, handle
            return document, None, None

        if hasattr(document, "read"):
            name = getattr(document, "name", "document")
            filename = Path(str(name)).name
            return None, {"document": (filename, document)}, None

        return document, None, None
