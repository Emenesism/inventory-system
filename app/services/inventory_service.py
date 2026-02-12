from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from app.core.config import AppConfig
from app.data.inventory_store import InventoryStore
from app.models.errors import InventoryFileError
from app.services.backend_client import BackendAPIError, BackendClient
from app.utils.text import normalize_text


class InventoryService:
    def __init__(self, store: InventoryStore, config: AppConfig) -> None:
        self.store = store
        self.config = config
        self._name_index: dict[str, int] = {}
        self._logger = logging.getLogger(self.__class__.__name__)
        self._client = BackendClient(config.backend_url)
        self._loaded = False

    def set_inventory_path(self, path: str | Path | None) -> None:
        self.store.set_path(path)
        self.config.inventory_file = str(path) if path else None
        self.config.save()

    def import_excel(self, path: str | Path) -> dict[str, object]:
        path_obj = Path(path)
        if not path_obj.exists():
            raise InventoryFileError(f"فایل موجودی پیدا نشد: {path_obj}")
        try:
            with path_obj.open("rb") as handle:
                payload = self._client.post(
                    "/api/v1/inventory/import-excel",
                    files={
                        "file": (
                            path_obj.name,
                            handle,
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        )
                    },
                )
        except BackendAPIError as exc:
            raise InventoryFileError(str(exc)) from exc

        self.store.set_path(path_obj)
        self.config.inventory_file = str(path_obj)
        self.config.save()
        return payload if isinstance(payload, dict) else {}

    def load(self) -> pd.DataFrame:
        try:
            items: list[dict[str, object]] = []
            offset = 0
            page_size = 1000
            while True:
                payload = self._client.get(
                    "/api/v1/products",
                    params={"limit": page_size, "offset": offset},
                )
                batch = (
                    payload.get("items", [])
                    if isinstance(payload, dict)
                    else []
                )
                if not batch:
                    break
                items.extend(batch)
                if len(batch) < page_size:
                    break
                offset += len(batch)

            rows = []
            for item in items:
                rows.append(
                    {
                        "product_name": str(
                            item.get("product_name", "")
                        ).strip(),
                        "quantity": int(item.get("quantity", 0) or 0),
                        "avg_buy_price": float(
                            item.get("avg_buy_price", 0.0) or 0.0
                        ),
                        "last_buy_price": float(
                            item.get("last_buy_price", 0.0) or 0.0
                        ),
                        "alarm": item.get("alarm"),
                        "source": item.get("source"),
                    }
                )
            df = pd.DataFrame(rows)
            if df.empty:
                df = pd.DataFrame(
                    columns=[
                        "product_name",
                        "quantity",
                        "avg_buy_price",
                        "last_buy_price",
                        "alarm",
                        "source",
                    ]
                )
            self.store.dataframe = df
            self._rebuild_index(df)
            self._loaded = True
            return df
        except BackendAPIError as exc:
            self._loaded = False
            raise InventoryFileError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            self._loaded = False
            raise InventoryFileError(
                "بارگذاری موجودی از بک‌اند ناموفق بود."
            ) from exc

    def save(
        self, df: pd.DataFrame, admin_username: str | None = None
    ) -> Path | None:
        _ = admin_username
        rows: list[dict[str, object]] = []
        df_to_save = df.copy()
        if "last_buy_price" not in df_to_save.columns:
            df_to_save["last_buy_price"] = 0.0
        if "alarm" not in df_to_save.columns:
            df_to_save["alarm"] = None
        if "source" not in df_to_save.columns:
            df_to_save["source"] = None

        for _, row in df_to_save.iterrows():
            name = str(row.get("product_name", "")).strip()
            if not name:
                continue
            quantity_value = pd.to_numeric(
                row.get("quantity", 0), errors="coerce"
            )
            avg_value = pd.to_numeric(
                row.get("avg_buy_price", 0), errors="coerce"
            )
            last_value = pd.to_numeric(
                row.get("last_buy_price", 0), errors="coerce"
            )
            alarm_value = row.get("alarm")
            source_value = row.get("source")
            rows.append(
                {
                    "product_name": name,
                    "quantity": (
                        int(quantity_value) if pd.notna(quantity_value) else 0
                    ),
                    "avg_buy_price": (
                        float(avg_value) if pd.notna(avg_value) else 0.0
                    ),
                    "last_buy_price": (
                        float(last_value) if pd.notna(last_value) else 0.0
                    ),
                    "alarm": (
                        int(alarm_value)
                        if pd.notna(alarm_value)
                        and str(alarm_value).strip() != ""
                        else None
                    ),
                    "source": None
                    if source_value is None or str(source_value).strip() == ""
                    else str(source_value).strip(),
                }
            )

        if not rows:
            raise InventoryFileError(
                "هیچ ردیف معتبری برای ذخیره موجودی وجود ندارد."
            )

        try:
            self._client.post(
                "/api/v1/inventory/replace", json_body={"rows": rows}
            )
            refreshed = self.load()
            self._logger.info(
                "Inventory replaced via backend. Rows=%s", len(refreshed)
            )
        except BackendAPIError as exc:
            raise InventoryFileError(str(exc)) from exc
        return None

    def get_dataframe(self) -> pd.DataFrame:
        if self.store.dataframe is None:
            raise InventoryFileError("موجودی بارگذاری نشده است.")
        return self.store.dataframe

    def is_loaded(self) -> bool:
        return self._loaded

    def get_product_names(self) -> list[str]:
        if not self.is_loaded():
            return []
        df = self.store.dataframe
        if df is None or "product_name" not in df.columns:
            return []
        return df["product_name"].astype(str).str.strip().tolist()

    def find_index(self, product_name: str) -> int | None:
        key = self._normalize_name(product_name)
        return self._name_index.get(key)

    def get_low_stock_rows(self, threshold: int) -> list[dict[str, object]]:
        try:
            payload = self._client.get(
                "/api/v1/inventory/low-stock",
                params={"threshold": threshold},
            )
        except BackendAPIError as exc:
            raise InventoryFileError(str(exc)) from exc
        items = payload.get("items", []) if isinstance(payload, dict) else []
        return [item for item in items if isinstance(item, dict)]

    def _rebuild_index(self, df: pd.DataFrame) -> None:
        if "product_name" not in df.columns:
            self._name_index = {}
            return
        self._name_index = {
            self._normalize_name(name): idx
            for idx, name in df["product_name"].items()
        }

    @staticmethod
    def _normalize_name(name: str) -> str:
        return normalize_text(name)
