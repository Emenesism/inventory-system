from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from rapidfuzz import process

from app.models.errors import InventoryFileError
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
        "quantity": "quantity_sold",
        "qty": "quantity_sold",
        "quantity sold": "quantity_sold",
        "total quantity": "quantity_sold",
        "sell price": "sell_price",
        "sales price": "sell_price",
        "unit price": "sell_price",
        "price": "sell_price",
    }

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
        self, sales_df: pd.DataFrame, inventory_df: pd.DataFrame
    ) -> tuple[list[SalesPreviewRow], SalesPreviewSummary]:
        preview_rows: list[SalesPreviewRow] = []

        inventory_lookup: dict[str, int] = {}
        cost_lookup: dict[str, float] = {}
        name_lookup: dict[str, str] = {}
        for _, row in inventory_df.iterrows():
            key = normalize_text(row.get("product_name", ""))
            if key:
                inventory_lookup[key] = int(row.get("quantity", 0))
                cost_lookup[key] = float(row.get("avg_buy_price", 0.0))
                name_lookup.setdefault(
                    key, str(row.get("product_name", "")).strip()
                )
        available = inventory_lookup.copy()
        inventory_keys = list(inventory_lookup.keys())

        total = 0
        success = 0
        errors = 0

        for _, row in sales_df.iterrows():
            total += 1
            raw_name = row.get("product_name", "")
            product_name = "" if pd.isna(raw_name) else str(raw_name).strip()
            quantity_raw = row.get("quantity_sold", None)

            if not product_name:
                preview_rows.append(
                    SalesPreviewRow(
                        "", 0, 0.0, 0.0, "Error", "Missing product name"
                    )
                )
                errors += 1
                continue

            quantity = pd.to_numeric(quantity_raw, errors="coerce")
            if pd.isna(quantity) or quantity <= 0 or float(quantity) % 1 != 0:
                preview_rows.append(
                    SalesPreviewRow(
                        product_name, 0, 0.0, 0.0, "Error", "Invalid quantity"
                    )
                )
                errors += 1
                continue

            quantity = int(quantity)
            key = normalize_text(product_name)
            matched_key = key if key in available else ""
            match_message = ""

            if not matched_key and inventory_keys:
                match = process.extractOne(
                    key,
                    inventory_keys,
                    score_cutoff=95,
                    processor=None,
                )
                if match:
                    matched_key = match[0]
                    match_message = (
                        f"Matched to {name_lookup.get(matched_key, '')}"
                    )

            cost_price = cost_lookup.get(matched_key or key, 0.0)
            sell_price = row.get("sell_price", None)
            if pd.isna(sell_price) or sell_price is None or sell_price <= 0:
                sell_price = cost_price
            else:
                sell_price = float(sell_price)

            if not matched_key:
                preview_rows.append(
                    SalesPreviewRow(
                        product_name,
                        quantity,
                        sell_price,
                        cost_price,
                        "Error",
                        "Product not found",
                    )
                )
                errors += 1
                continue

            available[matched_key] -= quantity
            preview_rows.append(
                SalesPreviewRow(
                    product_name,
                    quantity,
                    sell_price,
                    cost_price,
                    "OK",
                    match_message or "Will update stock",
                    name_lookup.get(matched_key, product_name),
                )
            )
            success += 1

        summary = SalesPreviewSummary(
            total=total, success=success, errors=errors
        )
        return preview_rows, summary

    def apply(
        self, preview_rows: list[SalesPreviewRow], inventory_df: pd.DataFrame
    ) -> pd.DataFrame:
        updated_df = inventory_df.copy()
        name_to_index = {
            normalize_text(name): idx
            for idx, name in updated_df["product_name"].items()
        }

        for row in preview_rows:
            if row.status != "OK":
                continue
            key = normalize_text(row.resolved_name or row.product_name)
            idx = name_to_index.get(key)
            if idx is None:
                continue
            current_qty = int(updated_df.at[idx, "quantity"])
            updated_df.at[idx, "quantity"] = current_qty - row.quantity_sold

        return updated_df

    def refresh_preview_rows(
        self,
        preview_rows: list[SalesPreviewRow],
        inventory_df: pd.DataFrame,
        row_indices: list[int] | None = None,
    ) -> SalesPreviewSummary:
        inventory_lookup: dict[str, int] = {}
        cost_lookup: dict[str, float] = {}
        name_lookup: dict[str, str] = {}
        for _, row in inventory_df.iterrows():
            key = normalize_text(row.get("product_name", ""))
            if key:
                inventory_lookup[key] = int(row.get("quantity", 0))
                cost_lookup[key] = float(row.get("avg_buy_price", 0.0))
                name_lookup.setdefault(
                    key, str(row.get("product_name", "")).strip()
                )
        inventory_keys = list(inventory_lookup.keys())

        indices = (
            row_indices
            if row_indices is not None
            else list(range(len(preview_rows)))
        )
        for idx in indices:
            if idx < 0 or idx >= len(preview_rows):
                continue
            row = preview_rows[idx]
            self._refresh_row(row, inventory_keys, cost_lookup, name_lookup)

        total = len(preview_rows)
        success = sum(1 for row in preview_rows if row.status == "OK")
        errors = total - success
        return SalesPreviewSummary(total=total, success=success, errors=errors)

    @staticmethod
    def _refresh_row(
        row: SalesPreviewRow,
        inventory_keys: list[str],
        cost_lookup: dict[str, float],
        name_lookup: dict[str, str],
    ) -> None:
        product_name = str(row.product_name or "").strip()
        row.product_name = product_name
        if not product_name:
            row.status = "Error"
            row.message = "Missing product name"
            row.resolved_name = ""
            row.cost_price = 0.0
            return

        quantity = pd.to_numeric(row.quantity_sold, errors="coerce")
        if pd.isna(quantity) or quantity <= 0 or float(quantity) % 1 != 0:
            row.status = "Error"
            row.message = "Invalid quantity"
            row.resolved_name = ""
            row.cost_price = 0.0
            return

        quantity = int(quantity)
        row.quantity_sold = quantity
        key = normalize_text(product_name)
        matched_key = key if key in name_lookup else ""
        match_message = ""

        if not matched_key and inventory_keys:
            match = process.extractOne(
                key,
                inventory_keys,
                score_cutoff=95,
                processor=None,
            )
            if match:
                matched_key = match[0]
                match_message = f"Matched to {name_lookup.get(matched_key, '')}"

        cost_price = cost_lookup.get(matched_key or key, 0.0)
        row.cost_price = cost_price
        if row.sell_price is None or row.sell_price <= 0:
            row.sell_price = cost_price

        if not matched_key:
            row.status = "Error"
            row.message = "Product not found"
            row.resolved_name = ""
            return

        row.status = "OK"
        row.message = match_message or "Will update stock"
        row.resolved_name = name_lookup.get(matched_key, product_name)
