from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from app.models.errors import InventoryFileError
from app.utils.excel import apply_banded_rows


@dataclass
class InventoryStore:
    path: Path | None = None
    dataframe: pd.DataFrame | None = None

    REQUIRED_COLUMNS = ["product_name", "quantity", "avg_buy_price"]
    OPTIONAL_COLUMNS = ["last_buy_price", "sell_price"]
    COLUMN_ORDER = [
        "product_name",
        "quantity",
        "avg_buy_price",
        "last_buy_price",
        "sell_price",
        "alarm",
        "source",
    ]
    PERSIAN_COLUMN_MAP = {
        "نام محصول": "product_name",
        "تعداد": "quantity",
        "قیمت خرید": "avg_buy_price",
        "قيمت خريد": "avg_buy_price",
        "میانگین قیمت خرید": "avg_buy_price",
        "آخرین قیمت خرید": "last_buy_price",
        "آخرين قيمت خريد": "last_buy_price",
        "Last Buy Price": "last_buy_price",
        "last buy price": "last_buy_price",
        "قیمت فروش": "sell_price",
        "قيمت فروش": "sell_price",
        "Sell Price": "sell_price",
        "sell price": "sell_price",
        "آلارم": "alarm",
        "منبع": "source",
    }

    def set_path(self, path: str | Path | None) -> None:
        self.path = Path(path) if path else None

    def load(self) -> pd.DataFrame:
        if not self.path:
            raise InventoryFileError("هیچ فایل موجودی انتخاب نشده است.")
        if not self.path.exists():
            raise InventoryFileError(f"فایل موجودی پیدا نشد: {self.path}")

        try:
            df = self._read_file(self.path)
        except InventoryFileError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise InventoryFileError(
                "خواندن فایل موجودی ناموفق بود. قالب فایل را بررسی کنید."
            ) from exc

        df = self._normalize_columns(df)
        df = self._ensure_optional_columns(df)
        self._validate(df)
        df = self._reorder_columns(df)
        self.dataframe = df
        return df

    def save(self, df: pd.DataFrame) -> None:
        if not self.path:
            raise InventoryFileError("هیچ فایل موجودی انتخاب نشده است.")
        df_to_save = self._reorder_columns(df.copy())

        suffix = self.path.suffix.lower()
        if suffix not in {".xlsx", ".xlsm"}:
            raise InventoryFileError("قالب فایل موجودی پشتیبانی نمی‌شود.")

        df_to_save.to_excel(self.path, index=False)
        self._ensure_sheet_ltr(self.path)
        apply_banded_rows(self.path)
        self.dataframe = df_to_save

    def _read_file(self, path: Path) -> pd.DataFrame:
        suffix = path.suffix.lower()
        if suffix in {".xlsx", ".xlsm"}:
            return pd.read_excel(path, engine="openpyxl")
        raise InventoryFileError("قالب فایل موجودی پشتیبانی نمی‌شود.")

    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df.columns = [str(col).strip() for col in df.columns]
        lower_map = {str(col).strip().lower(): col for col in df.columns}
        normalized_map = {str(col).strip(): col for col in df.columns}

        rename_map = {}
        for required in self.REQUIRED_COLUMNS:
            if required in lower_map:
                rename_map[lower_map[required]] = required
        alias_map = {
            "last buy price": "last_buy_price",
            "last_buy_price": "last_buy_price",
            "sell price": "sell_price",
            "sell_price": "sell_price",
        }
        for alias, target in alias_map.items():
            if alias in lower_map and target not in rename_map.values():
                rename_map[lower_map[alias]] = target
        for persian_name, target in self.PERSIAN_COLUMN_MAP.items():
            if (
                persian_name in normalized_map
                and target not in rename_map.values()
            ):
                rename_map[normalized_map[persian_name]] = target
        df = df.rename(columns=rename_map)
        return df

    def _validate(self, df: pd.DataFrame) -> None:
        missing = [
            col for col in self.REQUIRED_COLUMNS if col not in df.columns
        ]
        if missing:
            raise InventoryFileError(
                f"ستون‌های الزامی در فایل موجودی وجود ندارد: {', '.join(missing)}"
            )

        name_series = df["product_name"]
        blank_mask = name_series.isna() | (
            name_series.astype(str).str.strip() == ""
        )
        if blank_mask.any():
            df.drop(df.index[blank_mask], inplace=True)
            df.reset_index(drop=True, inplace=True)
        df["product_name"] = df["product_name"].astype(str).str.strip()

        quantity = pd.to_numeric(df["quantity"], errors="coerce").fillna(0)
        if (quantity % 1 != 0).any():
            raise InventoryFileError("تعداد موجودی باید عدد صحیح باشد.")
        df["quantity"] = quantity.astype(int)

        avg_buy = pd.to_numeric(df["avg_buy_price"], errors="coerce").fillna(0)
        df["avg_buy_price"] = avg_buy.astype(float)

        if "last_buy_price" in df.columns:
            last_buy = pd.to_numeric(
                df["last_buy_price"], errors="coerce"
            ).fillna(0)
            df["last_buy_price"] = last_buy.astype(float)
        if "sell_price" in df.columns:
            sell_price = pd.to_numeric(
                df["sell_price"], errors="coerce"
            ).fillna(0)
            df["sell_price"] = sell_price.astype(float)

    def _ensure_optional_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        for column in self.OPTIONAL_COLUMNS:
            if column not in df.columns:
                df[column] = 0.0
        return df

    def _reorder_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        preferred = [col for col in self.COLUMN_ORDER if col in df.columns]
        remaining = [col for col in df.columns if col not in preferred]
        if not preferred:
            return df
        return df[preferred + remaining]

    @staticmethod
    def _ensure_sheet_ltr(path: Path) -> None:
        try:
            from openpyxl import load_workbook
        except ImportError:
            return
        try:
            wb = load_workbook(path)
        except Exception:  # noqa: BLE001
            return
        for ws in wb.worksheets:
            ws.sheet_view.rightToLeft = True
        wb.save(path)
