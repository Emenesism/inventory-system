from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.core.config import AppConfig
from app.models.errors import InventoryFileError
from app.services.backend_client import BackendAPIError, BackendClient


@dataclass
class SalesPreviewRow:
    product_name: str
    quantity_sold: int
    sell_price: float
    cost_price: float
    status: str
    message: str
    resolved_name: str = ""


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
            raise InventoryFileError("Unsupported sales file format.")

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
                "Sales file missing required columns: "
                "product_name, quantity_sold (aliases: Product Name, Quantity)"
            )
        if "sell_price" in df.columns:
            df["sell_price"] = pd.to_numeric(df["sell_price"], errors="coerce")
        return df

    def preview(
        self, sales_df: pd.DataFrame, inventory_df: pd.DataFrame | None = None
    ) -> tuple[list[SalesPreviewRow], SalesPreviewSummary]:
        _ = inventory_df
        rows_payload = self._rows_from_dataframe(sales_df)
        try:
            payload = self._client.post(
                "/api/v1/sales/preview",
                json_body={"rows": rows_payload},
            )
        except BackendAPIError as exc:
            raise InventoryFileError(str(exc)) from exc

        return self._parse_preview_payload(payload)

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
        _ = inventory_df
        indices = (
            row_indices
            if row_indices is not None
            else list(range(len(preview_rows)))
        )
        if not indices:
            total = len(preview_rows)
            success = sum(1 for row in preview_rows if row.status == "OK")
            return SalesPreviewSummary(
                total=total, success=success, errors=total - success
            )

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
            total = len(preview_rows)
            success = sum(1 for row in preview_rows if row.status == "OK")
            return SalesPreviewSummary(
                total=total, success=success, errors=total - success
            )

        try:
            payload = self._client.post(
                "/api/v1/sales/preview",
                json_body={"rows": rows_payload},
            )
        except BackendAPIError as exc:
            raise InventoryFileError(str(exc)) from exc

        updated_rows, _summary = self._parse_preview_payload(payload)
        for position, updated in zip(valid_positions, updated_rows):
            preview_rows[position] = updated

        total = len(preview_rows)
        success = sum(1 for row in preview_rows if row.status == "OK")
        return SalesPreviewSummary(
            total=total, success=success, errors=total - success
        )

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
            preview_rows.append(
                SalesPreviewRow(
                    product_name=str(row.get("product_name", "")),
                    quantity_sold=int(row.get("quantity_sold", 0) or 0),
                    sell_price=float(row.get("sell_price", 0.0) or 0.0),
                    cost_price=float(row.get("cost_price", 0.0) or 0.0),
                    status=str(row.get("status", "Error")),
                    message=str(row.get("message", "")),
                    resolved_name=str(row.get("resolved_name", "")),
                )
            )

        summary = SalesPreviewSummary(
            total=int(
                summary_data.get("total", len(preview_rows))
                or len(preview_rows)
            ),
            success=int(summary_data.get("success", 0) or 0),
            errors=int(summary_data.get("errors", 0) or 0),
        )
        return preview_rows, summary
