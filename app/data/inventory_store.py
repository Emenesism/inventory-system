from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from app.models.errors import InventoryFileError
from app.utils.crypto import decrypt_bytes, encrypt_bytes
from app.utils.excel import apply_banded_rows


@dataclass
class InventoryStore:
    path: Path | None = None
    dataframe: pd.DataFrame | None = None
    passphrase: str = "1111"

    REQUIRED_COLUMNS = ["product_name", "quantity", "avg_buy_price"]
    COLUMN_ORDER = [
        "product_name",
        "quantity",
        "avg_buy_price",
        "alarm",
        "source",
    ]
    PERSIAN_COLUMN_MAP = {
        "نام محصول": "product_name",
        "تعداد": "quantity",
        "قیمت خرید": "avg_buy_price",
        "قيمت خريد": "avg_buy_price",
        "میانگین قیمت خرید": "avg_buy_price",
        "آلارم": "alarm",
        "منبع": "source",
    }

    def set_path(self, path: str | Path | None) -> None:
        self.path = Path(path) if path else None

    def set_passphrase(self, passphrase: str | None) -> None:
        self.passphrase = passphrase or "1111"

    def load(self) -> pd.DataFrame:
        if not self.path:
            raise InventoryFileError("No inventory file selected.")
        if not self.path.exists():
            raise InventoryFileError(f"Inventory file not found: {self.path}")

        try:
            df = self._read_file(self.path)
        except InventoryFileError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise InventoryFileError(
                "Failed to read inventory file. Please check the format."
            ) from exc

        df = self._normalize_columns(df)
        self._validate(df)
        df = self._reorder_columns(df)
        self.dataframe = df
        return df

    def save(self, df: pd.DataFrame) -> None:
        if not self.path:
            raise InventoryFileError("No inventory file selected.")
        df_to_save = self._reorder_columns(df.copy())

        suffix = self.path.suffix.lower()
        if suffix == ".dat":
            self._write_encrypted_file(df_to_save)
        elif suffix in {".xlsx", ".xlsm"}:
            df_to_save.to_excel(self.path, index=False)
            self._ensure_sheet_ltr(self.path)
            apply_banded_rows(self.path)
        else:
            raise InventoryFileError("Unsupported inventory file format.")

        self.dataframe = df_to_save

    def backup(self, backup_dir: Path | None = None) -> Path | None:
        if not self.path:
            raise InventoryFileError("No inventory file selected.")
        if not self.path.exists():
            return None
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        backup_name = f"inventory_backup_{timestamp}{self.path.suffix}"
        target_dir = backup_dir if backup_dir else self.path.parent
        backup_path = target_dir / backup_name
        shutil.copy2(self.path, backup_path)
        return backup_path

    def _read_file(self, path: Path) -> pd.DataFrame:
        suffix = path.suffix.lower()
        if suffix == ".dat":
            return self._read_encrypted_file(path)
        if suffix in {".xlsx", ".xlsm"}:
            return pd.read_excel(path, engine="openpyxl")
        raise InventoryFileError("Unsupported inventory file format.")

    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df.columns = [str(col).strip() for col in df.columns]
        lower_map = {str(col).strip().lower(): col for col in df.columns}
        normalized_map = {str(col).strip(): col for col in df.columns}

        rename_map = {}
        for required in self.REQUIRED_COLUMNS:
            if required in lower_map:
                rename_map[lower_map[required]] = required
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
                f"Inventory file missing required columns: {', '.join(missing)}"
            )

        if df["product_name"].isna().any():
            raise InventoryFileError("Inventory file has blank product names.")
        df["product_name"] = df["product_name"].astype(str).str.strip()
        if (df["product_name"] == "").any():
            raise InventoryFileError("Inventory file has blank product names.")

        quantity = pd.to_numeric(df["quantity"], errors="coerce").fillna(0)
        if (quantity % 1 != 0).any():
            raise InventoryFileError(
                "Inventory quantities must be whole numbers."
            )
        df["quantity"] = quantity.astype(int)

        avg_buy = pd.to_numeric(df["avg_buy_price"], errors="coerce").fillna(0)
        df["avg_buy_price"] = avg_buy.astype(float)

    def _reorder_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        preferred = [col for col in self.COLUMN_ORDER if col in df.columns]
        remaining = [col for col in df.columns if col not in preferred]
        if not preferred:
            return df
        return df[preferred + remaining]

    def _read_encrypted_file(self, path: Path) -> pd.DataFrame:
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise InventoryFileError("Failed to read inventory file.") from exc
        try:
            decrypted = decrypt_bytes(payload, self._get_passphrase())
        except Exception as exc:  # noqa: BLE001
            raise InventoryFileError(
                "Failed to decrypt inventory file. Check passcode or file integrity."
            ) from exc

        temp_dir = Path(tempfile.mkdtemp(prefix="armkala_inventory_"))
        temp_path = temp_dir / "inventory.xlsx"
        try:
            temp_path.write_bytes(decrypted)
            return pd.read_excel(temp_path, engine="openpyxl")
        finally:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass
            try:
                temp_dir.rmdir()
            except OSError:
                pass

    def _write_encrypted_file(self, df: pd.DataFrame) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="armkala_inventory_"))
        temp_path = temp_dir / "inventory.xlsx"
        try:
            df.to_excel(temp_path, index=False)
            self._ensure_sheet_ltr(temp_path)
            apply_banded_rows(temp_path)
            plaintext = temp_path.read_bytes()
            encrypted = encrypt_bytes(plaintext, self._get_passphrase())
            self._atomic_write(self.path, encrypted)
        finally:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass
            try:
                temp_dir.rmdir()
            except OSError:
                pass

    def _atomic_write(self, path: Path | None, data: bytes) -> None:
        if path is None:
            raise InventoryFileError("No inventory file selected.")
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_file = tempfile.NamedTemporaryFile(
            prefix=f"{path.stem}_",
            suffix=".tmp",
            dir=str(path.parent),
            delete=False,
        )
        temp_name = temp_file.name
        try:
            with temp_file:
                temp_file.write(data)
            Path(temp_name).replace(path)
        finally:
            try:
                os.remove(temp_name)
            except FileNotFoundError:
                pass

    def _get_passphrase(self) -> str:
        if not self.passphrase:
            raise InventoryFileError("Inventory encryption key missing.")
        return self.passphrase

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
