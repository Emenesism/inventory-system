from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd
from rapidfuzz import fuzz, process

from app.core.config import AppConfig
from app.models.errors import InventoryFileError
from app.services.backend_client import BackendAPIError, BackendClient
from app.utils.text import normalize_text


@dataclass
class SalesPreviewRow:
    product_name: str
    quantity_sold: int
    sell_price: float
    cost_price: float
    status: str
    message: str
    resolved_name: str = ""
    match_percent: int | None = None


@dataclass
class SalesPreviewSummary:
    total: int
    success: int
    errors: int


class SalesImportService:
    REQUIRED_COLUMNS = ["product_name", "quantity_sold"]
    COLUMN_ALIASES = {
        "product name": "product_name",
        "product": "product_name",
        "نام کالا": "product_name",
        "نام محصول": "product_name",
        "کالا": "product_name",
        "محصول": "product_name",
        "quantity": "quantity_sold",
        "qty": "quantity_sold",
        "quantity sold": "quantity_sold",
        "total quantity": "quantity_sold",
        "تعداد": "quantity_sold",
        "جمع تعداد": "quantity_sold",
        "sell price": "sell_price",
        "sales price": "sell_price",
        "unit price": "sell_price",
        "price": "sell_price",
        "قیمت فروش": "sell_price",
        "قيمت فروش": "sell_price",
    }

    def __init__(self) -> None:
        config = AppConfig.load()
        self._client = BackendClient(config.backend_url)

    def load_sales_file(self, path: str) -> pd.DataFrame:
        suffix = str(path).lower()
        if suffix.endswith((".xlsx", ".xlsm")):
            df = pd.read_excel(path, engine="openpyxl")
        elif suffix.endswith(".csv"):
            df = pd.read_csv(path)
        else:
            raise InventoryFileError("قالب فایل فروش پشتیبانی نمی‌شود.")

        df.columns = [str(col).strip() for col in df.columns]
        lower_map = {str(col).strip().lower(): col for col in df.columns}

        rename_map: dict[str, str] = {}
        for required in self.REQUIRED_COLUMNS:
            if required in lower_map:
                rename_map[lower_map[required]] = required
        for alias, target in self.COLUMN_ALIASES.items():
            if alias in lower_map and target not in rename_map.values():
                rename_map[lower_map[alias]] = target

        df = df.rename(columns=rename_map)
        missing = [
            col for col in self.REQUIRED_COLUMNS if col not in df.columns
        ]
        if missing:
            raise InventoryFileError(
                "ستون‌های الزامی فایل فروش یافت نشد: "
                "product_name, quantity_sold (معادل‌ها: Product Name, Quantity)"
            )
        if "sell_price" in df.columns:
            df["sell_price"] = pd.to_numeric(df["sell_price"], errors="coerce")
        return df

    def preview(
        self, sales_df: pd.DataFrame, inventory_df: pd.DataFrame | None = None
    ) -> tuple[list[SalesPreviewRow], SalesPreviewSummary]:
        rows_payload = self._rows_from_dataframe(sales_df)
        try:
            payload = self._client.post(
                "/api/v1/sales/preview",
                json_body={"rows": rows_payload},
            )
        except BackendAPIError as exc:
            raise InventoryFileError(str(exc)) from exc

        preview_rows, summary = self._parse_preview_payload(payload)
        self._apply_local_fuzzy_matches(preview_rows, inventory_df)
        return preview_rows, self._build_summary(
            preview_rows, total_hint=summary.total
        )

    def apply(
        self,
        preview_rows: list[SalesPreviewRow],
        inventory_df: pd.DataFrame,
    ) -> pd.DataFrame:
        # Stock updates are applied in backend when invoice is created.
        _ = preview_rows
        return inventory_df

    def refresh_preview_rows(
        self,
        preview_rows: list[SalesPreviewRow],
        inventory_df: pd.DataFrame,
        row_indices: list[int] | None = None,
    ) -> SalesPreviewSummary:
        indices = (
            row_indices
            if row_indices is not None
            else list(range(len(preview_rows)))
        )
        if not indices:
            return self._build_summary(preview_rows)

        rows_payload: list[dict[str, object]] = []
        valid_positions: list[int] = []
        for idx in indices:
            if idx < 0 or idx >= len(preview_rows):
                continue
            row = preview_rows[idx]
            rows_payload.append(
                {
                    "product_name": row.product_name,
                    "quantity_sold": int(row.quantity_sold),
                    "sell_price": float(row.sell_price),
                }
            )
            valid_positions.append(idx)

        if not rows_payload:
            return self._build_summary(preview_rows)

        try:
            payload = self._client.post(
                "/api/v1/sales/preview",
                json_body={"rows": rows_payload},
            )
        except BackendAPIError as exc:
            raise InventoryFileError(str(exc)) from exc

        updated_rows, _summary = self._parse_preview_payload(payload)
        self._apply_local_fuzzy_matches(updated_rows, inventory_df)
        for position, updated in zip(valid_positions, updated_rows):
            preview_rows[position] = updated

        return self._build_summary(preview_rows)

    @staticmethod
    def _rows_from_dataframe(sales_df: pd.DataFrame) -> list[dict[str, object]]:
        payload: list[dict[str, object]] = []
        for _, row in sales_df.iterrows():
            name_raw = row.get("product_name", "")
            quantity_raw = row.get("quantity_sold", 0)
            sell_price_raw = row.get("sell_price", 0)
            name = "" if pd.isna(name_raw) else str(name_raw).strip()
            quantity_value = pd.to_numeric(quantity_raw, errors="coerce")
            sell_price_value = pd.to_numeric(sell_price_raw, errors="coerce")
            quantity_int = 0
            if pd.notna(quantity_value):
                quantity_float = float(quantity_value)
                if quantity_float % 1 == 0:
                    quantity_int = int(quantity_float)
            payload.append(
                {
                    "product_name": name,
                    "quantity_sold": quantity_int,
                    "sell_price": float(sell_price_value)
                    if pd.notna(sell_price_value)
                    else 0.0,
                }
            )
        return payload

    @staticmethod
    def _parse_preview_payload(
        payload: dict,
    ) -> tuple[list[SalesPreviewRow], SalesPreviewSummary]:
        rows_data = payload.get("rows", []) if isinstance(payload, dict) else []
        summary_data = (
            payload.get("summary", {}) if isinstance(payload, dict) else {}
        )

        preview_rows: list[SalesPreviewRow] = []
        for row in rows_data:
            if not isinstance(row, dict):
                continue
            status = str(row.get("status", "Error")).strip()
            message = str(row.get("message", "")).strip()
            if "insufficient stock" in message.lower():
                status = "OK"
                message = "Will update stock"
            match_percent = SalesImportService._coerce_match_percent(
                row.get("match_percent")
            )
            if match_percent is None:
                match_percent = SalesImportService._extract_match_percent(
                    message
                )
            preview_rows.append(
                SalesPreviewRow(
                    product_name=str(row.get("product_name", "")),
                    quantity_sold=int(row.get("quantity_sold", 0) or 0),
                    sell_price=float(row.get("sell_price", 0.0) or 0.0),
                    cost_price=float(row.get("cost_price", 0.0) or 0.0),
                    status=status,
                    message=message,
                    resolved_name=str(row.get("resolved_name", "")),
                    match_percent=match_percent,
                )
            )

        total_rows = len(preview_rows)
        success_rows = sum(1 for row in preview_rows if row.status == "OK")
        summary = SalesPreviewSummary(
            total=int(summary_data.get("total", total_rows) or total_rows),
            success=success_rows,
            errors=total_rows - success_rows,
        )
        return preview_rows, summary

    @staticmethod
    def _build_summary(
        preview_rows: list[SalesPreviewRow], total_hint: int | None = None
    ) -> SalesPreviewSummary:
        total = len(preview_rows)
        if total_hint is not None:
            try:
                hinted = int(total_hint)
            except (TypeError, ValueError):
                hinted = total
            total = max(total, hinted)
        success = sum(1 for row in preview_rows if row.status == "OK")
        errors = max(0, total - success)
        return SalesPreviewSummary(total=total, success=success, errors=errors)

    @classmethod
    def _apply_local_fuzzy_matches(
        cls,
        preview_rows: list[SalesPreviewRow],
        inventory_df: pd.DataFrame | None,
    ) -> None:
        if not preview_rows or inventory_df is None:
            return
        if inventory_df.empty or "product_name" not in inventory_df.columns:
            return

        candidates: list[dict[str, object]] = []
        normalized_choices: list[str] = []
        seen_keys: set[str] = set()
        for _, inv_row in inventory_df.iterrows():
            raw_name = inv_row.get("product_name", "")
            product_name = str(raw_name).strip()
            normalized_name = normalize_text(product_name)
            if not normalized_name or normalized_name in seen_keys:
                continue
            seen_keys.add(normalized_name)
            avg_buy_price = cls._to_non_negative_float(
                inv_row.get("avg_buy_price", 0.0)
            )
            sell_price = cls._to_non_negative_float(
                inv_row.get("sell_price", 0.0)
            )
            candidates.append(
                {
                    "product_name": product_name,
                    "avg_buy_price": avg_buy_price,
                    "sell_price": sell_price,
                }
            )
            normalized_choices.append(normalized_name)

        if not normalized_choices:
            return

        for row in preview_rows:
            if str(row.status).strip().lower() != "error":
                continue
            if str(row.message).strip() != "Product not found":
                continue
            query = normalize_text(row.product_name)
            if not query:
                continue
            match = process.extractOne(
                query,
                normalized_choices,
                scorer=fuzz.WRatio,
                score_cutoff=85.0,
            )
            if not match:
                continue
            _matched, score, index = match
            if (
                not isinstance(index, int)
                or index < 0
                or index >= len(candidates)
            ):
                continue
            candidate = candidates[index]
            matched_name = str(candidate.get("product_name", "")).strip()
            if not matched_name:
                continue
            percent = int(round(float(score)))
            percent = max(85, min(100, percent))
            matched_cost = cls._to_non_negative_float(
                candidate.get("avg_buy_price", 0.0)
            )
            matched_sell = cls._to_non_negative_float(
                candidate.get("sell_price", 0.0)
            )

            row.status = "OK"
            row.resolved_name = matched_name
            row.match_percent = percent
            row.message = f"Matched to {matched_name} ({percent}%)"
            row.cost_price = matched_cost
            if row.sell_price <= 0:
                row.sell_price = (
                    matched_sell if matched_sell > 0 else matched_cost
                )

    @staticmethod
    def _to_non_negative_float(value: object) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return 0.0
        if not math.isfinite(parsed) or parsed < 0:
            return 0.0
        return parsed

    @staticmethod
    def _coerce_match_percent(value: object) -> int | None:
        try:
            parsed = int(round(float(value)))
        except (TypeError, ValueError):
            return None
        return max(0, min(100, parsed))

    @staticmethod
    def _extract_match_percent(message: str) -> int | None:
        text = str(message or "").strip()
        if not text.startswith("Matched to "):
            return None
        left = text.rfind("(")
        right = text.rfind("%)")
        if left < 0 or right < 0 or right <= left:
            return None
        raw = text[left + 1 : right].strip()
        if not raw:
            return None
        try:
            value = int(raw)
        except ValueError:
            return None
        return max(0, min(100, value))
