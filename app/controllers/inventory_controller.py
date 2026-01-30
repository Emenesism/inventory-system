from __future__ import annotations

import logging

from PySide6.QtCore import QObject

from app.models.errors import InventoryFileError
from app.services.action_log_service import ActionLogService
from app.services.inventory_service import InventoryService
from app.ui.pages.inventory_page import InventoryPage
from app.ui.widgets.toast import ToastManager
from app.utils import dialogs
from app.utils.excel import apply_banded_rows, autofit_columns, ensure_sheet_rtl
from app.utils.text import normalize_text


class InventoryController(QObject):
    def __init__(
        self,
        page: InventoryPage,
        inventory_service: InventoryService,
        toast: ToastManager,
        action_log_service: ActionLogService,
        current_admin_provider,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.page = page
        self.inventory_service = inventory_service
        self.toast = toast
        self.action_log_service = action_log_service
        self._current_admin_provider = current_admin_provider
        self._logger = logging.getLogger(self.__class__.__name__)

        self.page.reload_requested.connect(self.reload)
        self.page.save_requested.connect(self.save)
        self.page.export_requested.connect(self.export)

    def reload(self) -> None:
        try:
            df = self.inventory_service.load()
        except InventoryFileError as exc:
            dialogs.show_error(self.page, "Inventory Error", str(exc))
            self.toast.show("Inventory reload failed", "error")
            self._logger.exception("Failed to reload inventory")
            return
        self.page.set_inventory(df)
        self.toast.show("Inventory reloaded", "success")

    def save(self) -> None:
        df = self.page.get_dataframe()
        if df is None:
            return
        try:
            old_df = self.inventory_service.get_dataframe().copy()
        except Exception:  # noqa: BLE001
            old_df = None
        try:
            self.inventory_service.save(df)
        except InventoryFileError as exc:
            dialogs.show_error(self.page, "Inventory Error", str(exc))
            self.toast.show("Inventory save failed", "error")
            self._logger.exception("Failed to save inventory")
            return
        if old_df is not None:
            details = self._build_inventory_diff(old_df, df)
            if not details:
                details = "تغییر مشخصی یافت نشد، اما ذخیره انجام شد."
            admin = (
                self._current_admin_provider()
                if self._current_admin_provider
                else None
            )
            self.action_log_service.log_action(
                "inventory_edit",
                "ویرایش دستی موجودی",
                details,
                admin=admin,
            )
        self.toast.show("Inventory saved", "success")

    def export(self) -> None:
        df = self.page.get_dataframe()
        if df is None:
            dialogs.show_error(self.page, "Inventory", "No inventory loaded.")
            return
        if df.empty:
            dialogs.show_error(self.page, "Inventory", "No data to export.")
            return
        from PySide6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getSaveFileName(
            self.page,
            "Export Inventory",
            "stock.xlsx",
            "Excel Files (*.xlsx)",
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".xlsx"):
            file_path = f"{file_path}.xlsx"
        try:
            df.to_excel(file_path, index=False)
            ensure_sheet_rtl(file_path)
            apply_banded_rows(file_path)
            autofit_columns(file_path)
        except Exception as exc:  # noqa: BLE001
            dialogs.show_error(self.page, "Inventory", str(exc))
            self._logger.exception("Failed to export inventory")
            return
        if self.action_log_service:
            admin = (
                self._current_admin_provider()
                if self._current_admin_provider
                else None
            )
            self.action_log_service.log_action(
                "inventory_export",
                "خروجی موجودی",
                f"تعداد ردیف‌ها: {len(df)}\nمسیر: {file_path}",
                admin=admin,
            )
        self.toast.show("Inventory exported", "success")

    @staticmethod
    def _build_inventory_diff(old_df, new_df) -> str:  # noqa: ANN001
        def values_differ(a, b) -> bool:
            try:
                if a is None and b is None:
                    return False
                if isinstance(a, (int, float)) or isinstance(b, (int, float)):
                    return abs(float(a) - float(b)) > 1e-6
            except Exception:  # noqa: BLE001
                pass
            return str(a) != str(b)

        def key_map(df):
            return {
                normalize_text(str(row["product_name"])): row
                for _, row in df.iterrows()
                if str(row.get("product_name", "")).strip()
            }

        old_map = key_map(old_df)
        new_map = key_map(new_df)
        changes: list[str] = []

        for key, new_row in new_map.items():
            old_row = old_map.get(key)
            name = str(new_row.get("product_name", ""))
            if old_row is None:
                qty = new_row.get("quantity", "")
                avg = new_row.get("avg_buy_price", "")
                changes.append(
                    f"کالای جدید: {name} | تعداد={qty} | میانگین={avg}"
                )
                continue
            diff_parts: list[str] = []
            for col in new_df.columns:
                if col == "product_name":
                    continue
                old_val = old_row.get(col)
                new_val = new_row.get(col)
                if values_differ(old_val, new_val):
                    label = {
                        "quantity": "تعداد",
                        "avg_buy_price": "میانگین قیمت خرید",
                        "alarm": "آلارم",
                        "source": "منبع",
                    }.get(col, col)
                    diff_parts.append(f"{label}: {old_val} → {new_val}")
            if diff_parts:
                changes.append(f"ویرایش {name}: " + "، ".join(diff_parts))

        for key, old_row in old_map.items():
            if key not in new_map:
                name = str(old_row.get("product_name", ""))
                changes.append(f"حذف کالا: {name}")

        return "\n".join(changes[:200])
