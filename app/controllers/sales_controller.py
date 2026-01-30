from __future__ import annotations

import logging

from PySide6.QtCore import QObject

from app.models.errors import InventoryFileError
from app.services.action_log_service import ActionLogService
from app.services.inventory_service import InventoryService
from app.services.invoice_service import InvoiceService, SalesLine
from app.services.sales_import_service import SalesImportService
from app.ui.pages.sales_import_page import SalesImportPage
from app.ui.widgets.toast import ToastManager
from app.utils import dialogs
from app.utils.excel import apply_banded_rows, autofit_columns, ensure_sheet_rtl
from app.utils.text import normalize_text


class SalesImportController(QObject):
    def __init__(
        self,
        page: SalesImportPage,
        inventory_service: InventoryService,
        sales_service: SalesImportService,
        invoice_service: InvoiceService,
        toast: ToastManager,
        on_inventory_updated,
        on_invoices_updated,
        parent=None,
        current_admin_provider=None,
        action_log_service: ActionLogService | None = None,
    ) -> None:
        super().__init__(parent)
        self.page = page
        self.inventory_service = inventory_service
        self.sales_service = sales_service
        self.invoice_service = invoice_service
        self.toast = toast
        self.on_inventory_updated = on_inventory_updated
        self.on_invoices_updated = on_invoices_updated
        self._current_admin_provider = current_admin_provider
        self._logger = logging.getLogger(self.__class__.__name__)
        self._action_log_service = action_log_service

        self.page.preview_requested.connect(self.preview)
        self.page.apply_requested.connect(self.apply)
        self.page.product_name_edited.connect(self.update_row_statuses)
        self.page.export_requested.connect(self.export)

    def preview(self, path: str) -> None:
        if not self.inventory_service.is_loaded():
            dialogs.show_error(
                self.page, "Inventory Error", "Load inventory first."
            )
            self.toast.show("Inventory not loaded", "error")
            return
        try:
            sales_df = self.sales_service.load_sales_file(path)
            inventory_df = self.inventory_service.get_dataframe()
            preview_rows, summary = self.sales_service.preview(
                sales_df, inventory_df
            )
        except InventoryFileError as exc:
            dialogs.show_error(self.page, "Sales Import Error", str(exc))
            self.toast.show("Sales preview failed", "error")
            self._logger.exception("Failed to preview sales import")
            return

        self.page.set_preview(preview_rows, summary)
        self.toast.show("Preview ready", "success")

    def apply(self) -> None:
        if not self.inventory_service.is_loaded():
            dialogs.show_error(
                self.page, "Inventory Error", "Load inventory first."
            )
            self.toast.show("Inventory not loaded", "error")
            return
        if not self.page.preview_rows:
            dialogs.show_error(
                self.page, "Sales Import", "Load a preview first."
            )
            self.toast.show("No preview loaded", "error")
            return

        ok_count = sum(
            1 for row in self.page.preview_rows if row.status == "OK"
        )
        error_count = len(self.page.preview_rows) - ok_count
        if ok_count == 0:
            dialogs.show_error(
                self.page, "Sales Import", "No valid rows to apply."
            )
            self.toast.show("No valid rows to apply", "error")
            return

        proceed = dialogs.ask_yes_no(
            self.page,
            "Apply Sales Updates",
            f"Apply {ok_count} updates? {error_count} rows will be skipped.",
        )
        if not proceed:
            return

        try:
            inventory_df = self.inventory_service.get_dataframe()
            updated_df = self.sales_service.apply(
                self.page.preview_rows, inventory_df
            )
            self.inventory_service.save(updated_df)
            self.on_inventory_updated()
        except InventoryFileError as exc:
            dialogs.show_error(self.page, "Sales Import Error", str(exc))
            self.toast.show("Sales import failed", "error")
            self._logger.exception("Failed to apply sales import")
            return

        try:
            sales_lines = [
                SalesLine(
                    product_name=row.resolved_name or row.product_name,
                    price=row.sell_price,
                    quantity=row.quantity_sold,
                    cost_price=row.cost_price,
                )
                for row in self.page.preview_rows
                if row.status == "OK"
            ]
            if sales_lines:
                admin = (
                    self._current_admin_provider()
                    if self._current_admin_provider
                    else None
                )
                invoice_id = self.invoice_service.create_sales_invoice(
                    sales_lines,
                    admin_id=admin.admin_id if admin else None,
                    admin_username=admin.username if admin else None,
                )
                if self._action_log_service:
                    total_qty = sum(line.quantity for line in sales_lines)
                    total_amount = sum(
                        line.price * line.quantity for line in sales_lines
                    )
                    details = (
                        f"شماره فاکتور: {invoice_id}\n"
                        f"تعداد ردیف‌ها: {len(sales_lines)}\n"
                        f"تعداد کل: {total_qty}\n"
                        f"مبلغ کل: {total_amount:,.0f}"
                    )
                    self._action_log_service.log_action(
                        "sales_import",
                        "ثبت فاکتور فروش",
                        details,
                        admin=admin,
                    )
                self.on_invoices_updated()
        except Exception:  # noqa: BLE001
            self._logger.exception("Failed to store sales invoice history")

        self.page.reset_after_apply()
        self.toast.show("Sales import applied", "success")

    def update_row_statuses(self, row_indices: list[int]) -> None:
        if not row_indices or not self.page.preview_rows:
            return
        if not self.inventory_service.is_loaded():
            return
        try:
            inventory_df = self.inventory_service.get_dataframe()
            summary = self.sales_service.refresh_preview_rows(
                self.page.preview_rows,
                inventory_df,
                row_indices=row_indices,
            )
        except Exception:  # noqa: BLE001
            self._logger.exception("Failed to refresh sales preview rows")
            return
        self.page.update_preview_rows(row_indices, summary)

    def export(self) -> None:
        if not self.page.preview_rows:
            dialogs.show_error(
                self.page, "Sales Export", "Load a preview first."
            )
            return
        if not self.inventory_service.is_loaded():
            dialogs.show_error(
                self.page, "Inventory Error", "Load inventory first."
            )
            return

        self.page.flush_pending_edits()

        not_found_rows = [
            row
            for row in self.page.preview_rows
            if row.status == "Error" and row.message == "Product not found"
        ]
        fuzzy_rows = [
            row
            for row in self.page.preview_rows
            if row.status == "OK" and row.message.startswith("Matched to ")
        ]

        if not not_found_rows and not fuzzy_rows:
            dialogs.show_info(
                self.page,
                "Sales Export",
                "No missing or fuzzy matches to export.",
            )
            return

        from PySide6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getSaveFileName(
            self.page,
            "Export Sales Issues",
            "sales_import_review.xlsx",
            "Excel Files (*.xlsx)",
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".xlsx"):
            file_path = f"{file_path}.xlsx"

        try:
            import pandas as pd
        except Exception as exc:  # noqa: BLE001
            dialogs.show_error(self.page, "Sales Export", str(exc))
            return

        inventory_df = self.inventory_service.get_dataframe()
        stock_map = {}
        for _, inv_row in inventory_df.iterrows():
            key = normalize_text(inv_row.get("product_name", ""))
            if key:
                stock_map[key] = inv_row

        def _translate_status(status: str) -> str:
            return {"OK": "موفق", "Error": "خطا"}.get(status, status)

        def _translate_message(message: str) -> str:
            if message.startswith("Matched to "):
                matched = message.replace("Matched to ", "", 1).strip()
                return f"مطابقت با {matched}"
            return {
                "Product not found": "کالا یافت نشد",
                "Missing product name": "نام کالا خالی است",
                "Invalid quantity": "تعداد نامعتبر است",
                "Will update stock": "موجودی بروزرسانی می‌شود",
            }.get(message, message)

        def _translate_inventory_columns(columns: list[str]) -> dict[str, str]:
            mapping = {
                "product_name": "نام محصول",
                "quantity": "تعداد",
                "avg_buy_price": "میانگین قیمت خرید",
                "alarm": "آلارم",
                "source": "منبع",
                "category": "دسته‌بندی",
                "brand": "برند",
                "sku": "کد کالا",
                "code": "کد",
                "barcode": "بارکد",
                "size": "سایز",
                "color": "رنگ",
                "description": "توضیحات",
                "notes": "یادداشت",
            }
            translated: dict[str, str] = {}
            for col in columns:
                label = mapping.get(col)
                if label:
                    translated[col] = label
                else:
                    # Keep already-Persian headers; otherwise prefix with Persian label.
                    if any("\u0600" <= ch <= "\u06ff" for ch in str(col)):
                        translated[col] = str(col)
                    else:
                        translated[col] = f"ستون {col}"
            return translated

        inventory_columns = list(inventory_df.columns)
        inventory_label_map = _translate_inventory_columns(inventory_columns)

        not_found_payload = []
        for row in not_found_rows:
            not_found_payload.append(
                {
                    "نام محصول فروش": row.product_name,
                    "تعداد فروش": row.quantity_sold,
                    "وضعیت": _translate_status(row.status),
                    "پیام": _translate_message(row.message),
                }
            )

        fuzzy_payload = []
        for row in fuzzy_rows:
            record = {
                "نام محصول فروش": row.product_name,
                "تعداد فروش": row.quantity_sold,
                "محصول مطابق": row.resolved_name,
                "وضعیت": "مطابقت تقریبی",
                "پیام": _translate_message(row.message),
            }
            key = normalize_text(row.resolved_name or row.product_name)
            stock_row = stock_map.get(key)
            if stock_row is not None:
                for col in inventory_columns:
                    record[inventory_label_map[col]] = stock_row.get(col, None)
            else:
                for col in inventory_columns:
                    record.setdefault(inventory_label_map[col], None)
            fuzzy_payload.append(record)

        try:
            with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
                if not_found_payload:
                    pd.DataFrame(not_found_payload).to_excel(
                        writer, index=False, sheet_name="یافت نشد"
                    )
                if fuzzy_payload:
                    pd.DataFrame(fuzzy_payload).to_excel(
                        writer, index=False, sheet_name="مطابقت تقریبی"
                    )
            ensure_sheet_rtl(file_path)
            apply_banded_rows(file_path)
            autofit_columns(file_path)
        except Exception as exc:  # noqa: BLE001
            dialogs.show_error(self.page, "Sales Export", str(exc))
            self._logger.exception("Failed to export sales issues")
            return

        if self._action_log_service:
            admin = (
                self._current_admin_provider()
                if self._current_admin_provider
                else None
            )
            details = (
                f"موارد یافت نشد: {len(not_found_payload)}\n"
                f"موارد fuzzy: {len(fuzzy_payload)}\n"
                f"مسیر: {file_path}"
            )
            self._action_log_service.log_action(
                "sales_import_export",
                "خروجی مغایرت‌های فروش",
                details,
                admin=admin,
            )

        self.toast.show("Sales export completed", "success")
