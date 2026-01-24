from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.models.errors import InventoryFileError


@dataclass
class SalesPreviewRow:
    product_name: str
    quantity_sold: int
    status: str
    message: str


@dataclass
class SalesPreviewSummary:
    total: int
    success: int
    errors: int


class SalesImportService:
    REQUIRED_COLUMNS = ["product_name", "quantity_sold"]

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
        missing = [col for col in self.REQUIRED_COLUMNS if col not in lower_map]
        if missing:
            raise InventoryFileError(
                f"Sales file missing required columns: {', '.join(missing)}"
            )
        df = df.rename(
            columns={
                lower_map["product_name"]: "product_name",
                lower_map["quantity_sold"]: "quantity_sold",
            }
        )
        return df

    def preview(
        self, sales_df: pd.DataFrame, inventory_df: pd.DataFrame
    ) -> tuple[list[SalesPreviewRow], SalesPreviewSummary]:
        preview_rows: list[SalesPreviewRow] = []

        inventory_lookup = {}
        for _, row in inventory_df.iterrows():
            key = str(row.get("product_name", "")).strip().lower()
            if key:
                inventory_lookup[key] = int(row.get("quantity", 0))
        available = inventory_lookup.copy()

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
                    SalesPreviewRow("", 0, "Error", "Missing product name")
                )
                errors += 1
                continue

            quantity = pd.to_numeric(quantity_raw, errors="coerce")
            if pd.isna(quantity) or quantity <= 0 or float(quantity) % 1 != 0:
                preview_rows.append(
                    SalesPreviewRow(
                        product_name, 0, "Error", "Invalid quantity"
                    )
                )
                errors += 1
                continue

            quantity = int(quantity)
            key = product_name.strip().lower()
            if key not in available:
                preview_rows.append(
                    SalesPreviewRow(
                        product_name, quantity, "Error", "Product not found"
                    )
                )
                errors += 1
                continue

            if quantity > available[key]:
                preview_rows.append(
                    SalesPreviewRow(
                        product_name,
                        quantity,
                        "Error",
                        f"Insufficient stock (available {available[key]})",
                    )
                )
                errors += 1
                continue

            available[key] -= quantity
            preview_rows.append(
                SalesPreviewRow(
                    product_name, quantity, "OK", "Will update stock"
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
            str(name).strip().lower(): idx
            for idx, name in updated_df["product_name"].items()
        }

        for row in preview_rows:
            if row.status != "OK":
                continue
            key = row.product_name.strip().lower()
            idx = name_to_index.get(key)
            if idx is None:
                continue
            current_qty = int(updated_df.at[idx, "quantity"])
            updated_df.at[idx, "quantity"] = current_qty - row.quantity_sold

        return updated_df
