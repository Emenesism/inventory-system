from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from app.core.config import AppConfig
from app.data.inventory_store import InventoryStore
from app.models.errors import InventoryFileError
from app.services.backend_client import BackendAPIError, BackendClient
from app.utils.text import is_empty_marker, normalize_text


class InventoryService:
    _INVENTORY_COLUMNS = [
        "product_name",
        "quantity",
        "avg_buy_price",
        "last_buy_price",
        "sell_price",
        "alarm",
        "source",
    ]

    def __init__(self, store: InventoryStore, config: AppConfig) -> None:
        self.store = store
        self.config = config
        self._name_index: dict[str, int] = {}
        self._logger = logging.getLogger(self.__class__.__name__)
        self._client = BackendClient(config.backend_url)
        self._loaded = False
        self._sell_price_alarm_percent = 20.0

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

    def import_sell_prices(self, path: str | Path) -> dict[str, object]:
        path_obj = Path(path)
        if not path_obj.exists():
            raise InventoryFileError(f"فایل قیمت پیدا نشد: {path_obj}")

        suffix = path_obj.suffix.lower()
        mime_type = (
            "text/csv"
            if suffix == ".csv"
            else (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        )
        try:
            with path_obj.open("rb") as handle:
                payload = self._client.post(
                    "/api/v1/inventory/import-sell-prices",
                    files={"file": (path_obj.name, handle, mime_type)},
                )
        except BackendAPIError as exc:
            raise InventoryFileError(str(exc)) from exc
        return payload if isinstance(payload, dict) else {}

    def fetch_sell_price_alarm_percent(self) -> float:
        try:
            payload = self._client.get("/api/v1/settings/sell-price-alarm")
        except BackendAPIError as exc:
            raise InventoryFileError(str(exc)) from exc
        percent_raw = (
            payload.get("percent", 20.0) if isinstance(payload, dict) else 20.0
        )
        try:
            percent = float(percent_raw)
        except (TypeError, ValueError) as exc:
            raise InventoryFileError("مقدار درصد هشدار نامعتبر است.") from exc
        if percent < 0:
            percent = 0.0
        self._sell_price_alarm_percent = percent
        return self._sell_price_alarm_percent

    def update_sell_price_alarm_percent(self, percent: float) -> float:
        try:
            payload = self._client.patch(
                "/api/v1/settings/sell-price-alarm",
                json_body={"percent": float(percent)},
            )
        except BackendAPIError as exc:
            raise InventoryFileError(str(exc)) from exc
        percent_raw = (
            payload.get("percent", percent)
            if isinstance(payload, dict)
            else percent
        )
        try:
            value = float(percent_raw)
        except (TypeError, ValueError) as exc:
            raise InventoryFileError("پاسخ درصد هشدار نامعتبر است.") from exc
        if value < 0:
            value = 0.0
        self._sell_price_alarm_percent = value
        return self._sell_price_alarm_percent

    def get_cached_sell_price_alarm_percent(self) -> float:
        return float(self._sell_price_alarm_percent)

    def load(self) -> pd.DataFrame:
        try:
            items: list[dict[str, object]] = []
            offset = 0
            page_size = 1000
            while True:
                payload = self._client.get(
                    "/api/v1/products",
                    params={
                        "limit": page_size,
                        "offset": offset,
                        "view": "inventory",
                    },
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
                        "sell_price": float(item.get("sell_price", 0.0) or 0.0),
                        "alarm": item.get("alarm"),
                        "source": (
                            None
                            if is_empty_marker(item.get("source"))
                            else str(item.get("source")).strip()
                        ),
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
                        "sell_price",
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
        new_rows = self._coerce_inventory_rows(df)
        if not new_rows:
            raise InventoryFileError(
                "هیچ ردیف معتبری برای ذخیره موجودی وجود ندارد."
            )
        old_rows = self._coerce_inventory_rows(self.store.dataframe)
        upserts, deletes = self._compute_inventory_delta(old_rows, new_rows)

        try:
            if upserts or deletes:
                self._client.post(
                    "/api/v1/inventory/sync",
                    json_body={"upserts": upserts, "deletes": deletes},
                )
                refreshed = self.load()
                self._logger.info(
                    "Inventory synced via backend. Upserts=%s Deletes=%s Rows=%s",
                    len(upserts),
                    len(deletes),
                    len(refreshed),
                )
            else:
                self._logger.info(
                    "Inventory sync skipped (no changes). Rows=%s",
                    len(new_rows),
                )
                local_df = self._rows_to_dataframe(new_rows)
                self.store.dataframe = local_df
                self._rebuild_index(local_df)
                self._loaded = True
        except BackendAPIError as exc:
            raise InventoryFileError(str(exc)) from exc
        return None

    def _coerce_inventory_rows(
        self, df: pd.DataFrame | None
    ) -> list[dict[str, object]]:
        if df is None:
            return []
        df_to_save = df.copy()
        if "product_name" not in df_to_save.columns:
            return []
        if "quantity" not in df_to_save.columns:
            df_to_save["quantity"] = 0
        if "avg_buy_price" not in df_to_save.columns:
            df_to_save["avg_buy_price"] = 0.0
        if "last_buy_price" not in df_to_save.columns:
            df_to_save["last_buy_price"] = 0.0
        if "sell_price" not in df_to_save.columns:
            df_to_save["sell_price"] = 0.0
        if "alarm" not in df_to_save.columns:
            df_to_save["alarm"] = None
        if "source" not in df_to_save.columns:
            df_to_save["source"] = None
        working = df_to_save[self._INVENTORY_COLUMNS].copy()
        working["product_name"] = (
            working["product_name"].fillna("").astype(str).str.strip()
        )
        working = working[working["product_name"] != ""].copy()
        if working.empty:
            return []

        working["quantity"] = (
            pd.to_numeric(working["quantity"], errors="coerce")
            .fillna(0)
            .astype(int)
        )
        working["avg_buy_price"] = (
            pd.to_numeric(working["avg_buy_price"], errors="coerce")
            .fillna(0.0)
            .astype(float)
        )
        working["last_buy_price"] = (
            pd.to_numeric(working["last_buy_price"], errors="coerce")
            .fillna(0.0)
            .astype(float)
        )
        working["sell_price"] = (
            pd.to_numeric(working["sell_price"], errors="coerce")
            .fillna(0.0)
            .astype(float)
        )
        alarm_numeric = pd.to_numeric(working["alarm"], errors="coerce")
        working["alarm"] = [
            int(value) if pd.notna(value) else None
            for value in alarm_numeric.tolist()
        ]
        working["source"] = [
            None if is_empty_marker(value) else str(value).strip()
            for value in working["source"].tolist()
        ]
        return working.to_dict(orient="records")

    def _compute_inventory_delta(
        self,
        old_rows: list[dict[str, object]],
        new_rows: list[dict[str, object]],
    ) -> tuple[list[dict[str, object]], list[str]]:
        old_map = {
            self._normalize_name(str(row.get("product_name", ""))): row
            for row in old_rows
            if str(row.get("product_name", "")).strip()
        }
        new_map = {
            self._normalize_name(str(row.get("product_name", ""))): row
            for row in new_rows
            if str(row.get("product_name", "")).strip()
        }
        upserts: list[dict[str, object]] = []
        for key, new_row in new_map.items():
            old_row = old_map.get(key)
            if old_row is None or self._inventory_row_changed(old_row, new_row):
                upserts.append(new_row)
        deletes = [
            str(old_map[key].get("product_name", "")).strip()
            for key in old_map
            if key not in new_map
        ]
        return upserts, deletes

    @staticmethod
    def _inventory_row_changed(
        old_row: dict[str, object], new_row: dict[str, object]
    ) -> bool:
        if (
            str(old_row.get("product_name", "")).strip()
            != str(new_row.get("product_name", "")).strip()
        ):
            return True
        int_fields = ("quantity", "alarm")
        float_fields = ("avg_buy_price", "last_buy_price", "sell_price")
        text_fields = ("source",)
        for field in int_fields:
            old_value = old_row.get(field)
            new_value = new_row.get(field)
            if old_value is None and new_value is None:
                continue
            if int(old_value or 0) != int(new_value or 0):
                return True
        for field in float_fields:
            old_value = float(old_row.get(field, 0) or 0)
            new_value = float(new_row.get(field, 0) or 0)
            if abs(old_value - new_value) > 1e-6:
                return True
        for field in text_fields:
            old_value = old_row.get(field)
            new_value = new_row.get(field)
            if (
                None if is_empty_marker(old_value) else str(old_value).strip()
            ) != (
                None if is_empty_marker(new_value) else str(new_value).strip()
            ):
                return True
        return False

    def _rows_to_dataframe(self, rows: list[dict[str, object]]) -> pd.DataFrame:
        if not rows:
            return pd.DataFrame(columns=self._INVENTORY_COLUMNS)
        return pd.DataFrame(rows, columns=self._INVENTORY_COLUMNS)

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

    def get_sell_price_for_product(self, product_name: str) -> float | None:
        if not self.is_loaded():
            return None
        idx = self.find_index(product_name)
        if idx is None:
            return None
        df = self.store.dataframe
        if df is None or idx not in df.index:
            return None
        if "sell_price" not in df.columns:
            return 0.0
        value = pd.to_numeric(df.at[idx, "sell_price"], errors="coerce")
        if pd.isna(value):
            return 0.0
        return float(value)

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
