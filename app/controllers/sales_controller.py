from __future__ import annotations

import logging

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QDialog

from app.models.errors import InventoryFileError
from app.services.action_log_service import ActionLogService
from app.services.inventory_service import InventoryService
from app.services.invoice_service import InvoiceService, SalesLine
from app.services.sales_import_service import SalesImportService
from app.services.sales_manual_service import SalesManualLine
from app.ui.pages.sales_import_page import SalesImportPage
from app.ui.widgets.sales_invoice_preview_dialog import (
    SalesInvoicePreviewData,
    SalesInvoicePreviewDialog,
    SalesInvoicePreviewLine,
    SalesInvoiceStockProjection,
)
from app.ui.widgets.sales_manual_invoice_dialog import (
    SalesManualInvoiceDialog,
)
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
        self.page.manual_invoice_requested.connect(self.open_manual_invoice)

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

        admin = (
            self._current_admin_provider()
            if self._current_admin_provider
            else None
        )
        is_manager = bool(admin and admin.role == "manager")
        editable = is_manager or admin is None
        self.page.set_edit_mode(
            editable, self.inventory_service.get_product_names()
        )
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

        self.page.flush_pending_edits()

        try:
            inventory_df = self.inventory_service.get_dataframe()
            preview_lines = [
                SalesManualLine(
                    product_name=row.resolved_name or row.product_name,
                    quantity=row.quantity_sold,
                    price=row.sell_price,
                )
                for row in self.page.preview_rows
                if row.status == "OK"
            ]
            preview_data = self._build_sales_preview_data(
                preview_lines, inventory_df, error_count
            )
            preview_dialog = SalesInvoicePreviewDialog(self.page, preview_data)
            if preview_dialog.exec() != QDialog.Accepted:
                self.toast.show("Sales import canceled", "info")
                return
        except Exception:  # noqa: BLE001
            self._logger.exception("Failed to prepare sales import preview")
            dialogs.show_error(
                self.page, "Sales Import", "Failed to build invoice preview."
            )
            self.toast.show("Sales preview failed", "error")
            return

        try:
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

    def open_manual_invoice(self) -> None:
        if not self.inventory_service.is_loaded():
            dialogs.show_error(
                self.page, "Inventory Error", "Load inventory first."
            )
            self.toast.show("Inventory not loaded", "error")
            return
        dialog = SalesManualInvoiceDialog(self.page)
        dialog.set_product_provider(self.inventory_service.get_product_names)
        dialog.submit_requested.connect(
            lambda lines, dlg=dialog: self._submit_manual_invoice(lines, dlg)
        )
        dialog.exec()

    def _submit_manual_invoice(
        self, lines: list[SalesManualLine], dialog: SalesManualInvoiceDialog
    ) -> None:
        if not self.inventory_service.is_loaded():
            dialogs.show_error(
                dialog, "Inventory Error", "Load inventory first."
            )
            self.toast.show("Inventory not loaded", "error")
            return

        valid_lines: list[SalesManualLine] = []
        invalid = 0
        for line in lines:
            if not line.product_name:
                invalid += 1
                continue
            if line.quantity <= 0:
                invalid += 1
                continue
            valid_lines.append(line)

        if not valid_lines:
            dialogs.show_error(
                dialog,
                "Manual Sales Invoice",
                "Add at least one valid line.",
            )
            self.toast.show("No valid sales lines", "error")
            return

        inventory_df = self.inventory_service.get_dataframe()
        missing = [
            line.product_name
            for line in valid_lines
            if self.inventory_service.find_index(line.product_name) is None
        ]
        if missing:
            dialogs.show_error(
                dialog,
                "Manual Sales Invoice",
                "Product(s) not found:\n\n" + "\n".join(sorted(set(missing))),
            )
            self.toast.show("Product(s) not found", "error")
            return

        inventory_index = {
            normalize_text(name): idx
            for idx, name in inventory_df["product_name"].items()
        }
        aggregated: dict[str, int] = {}
        for line in valid_lines:
            key = normalize_text(line.product_name)
            aggregated[key] = aggregated.get(key, 0) + line.quantity

        insufficient: list[str] = []
        for key, qty in aggregated.items():
            idx = inventory_index.get(key)
            if idx is None:
                continue
            current_qty = int(inventory_df.at[idx, "quantity"])
            if current_qty - qty < 0:
                insufficient.append(
                    f"{inventory_df.at[idx, 'product_name']} "
                    f"(available {current_qty})"
                )
        if insufficient:
            dialogs.show_error(
                dialog,
                "Manual Sales Invoice",
                "Insufficient stock:\n\n" + "\n".join(insufficient),
            )
            self.toast.show("Insufficient stock", "error")
            return

        cost_map = {
            normalize_text(name): float(inventory_df.at[idx, "avg_buy_price"])
            for idx, name in inventory_df["product_name"].items()
        }
        priced_lines = [
            SalesManualLine(
                product_name=line.product_name,
                quantity=line.quantity,
                price=float(
                    cost_map.get(normalize_text(line.product_name), 0.0)
                ),
            )
            for line in valid_lines
        ]

        preview_data = self._build_sales_preview_data(
            priced_lines, inventory_df, invalid
        )
        preview_dialog = SalesInvoicePreviewDialog(dialog, preview_data)
        if preview_dialog.exec() != QDialog.Accepted:
            self.toast.show("Manual sales invoice canceled", "info")
            return

        try:
            updated_df = inventory_df.copy()
            for key, qty in aggregated.items():
                idx = inventory_index.get(key)
                if idx is None:
                    continue
                current_qty = int(updated_df.at[idx, "quantity"])
                updated_df.at[idx, "quantity"] = int(current_qty - qty)
            self.inventory_service.save(updated_df)
            self.on_inventory_updated()
        except Exception as exc:  # noqa: BLE001
            dialogs.show_error(dialog, "Manual Sales Invoice", str(exc))
            self.toast.show("Manual sales invoice failed", "error")
            self._logger.exception("Failed to apply manual sales invoice")
            return

        try:
            sales_lines = [
                SalesLine(
                    product_name=line.product_name,
                    price=line.price,
                    quantity=line.quantity,
                    cost_price=float(
                        cost_map.get(normalize_text(line.product_name), 0.0)
                    ),
                )
                for line in priced_lines
            ]
            admin = (
                self._current_admin_provider()
                if self._current_admin_provider
                else None
            )
            invoice_id = self.invoice_service.create_sales_invoice(
                sales_lines,
                admin_id=admin.admin_id if admin else None,
                admin_username=admin.username if admin else None,
                invoice_type="sales_manual",
            )
            if self._action_log_service:
                total_qty = sum(line.quantity for line in priced_lines)
                total_amount = sum(
                    line.price * line.quantity for line in priced_lines
                )
                details = (
                    f"شماره فاکتور: {invoice_id}\n"
                    f"تعداد ردیف‌ها: {len(valid_lines)}\n"
                    f"تعداد کل: {total_qty}\n"
                    f"مبلغ کل: {total_amount:,.0f}"
                )
                self._action_log_service.log_action(
                    "sales_manual_invoice",
                    "ثبت فاکتور فروش دستی",
                    details,
                    admin=admin,
                )
            self.on_invoices_updated()
        except Exception:  # noqa: BLE001
            self._logger.exception("Failed to store manual sales invoice")

        if invalid:
            self.toast.show(
                f"Manual sales invoice saved (skipped {invalid} invalid rows).",
                "success",
            )
        else:
            self.toast.show("Manual sales invoice saved", "success")
        dialog.accept()

    def _build_sales_preview_data(
        self,
        valid_lines: list[SalesManualLine],
        inventory_df,
        invalid_count: int,
    ) -> SalesInvoicePreviewData:
        preview_lines: list[SalesInvoicePreviewLine] = []
        total_qty = 0
        total_amount = 0.0
        aggregated: dict[str, int] = {}

        for line in valid_lines:
            line_total = line.price * line.quantity
            total_qty += line.quantity
            total_amount += line_total
            key = normalize_text(line.product_name)
            aggregated[key] = aggregated.get(key, 0) + line.quantity
            preview_lines.append(
                SalesInvoicePreviewLine(
                    product_name=line.product_name,
                    price=line.price,
                    quantity=line.quantity,
                    line_total=line_total,
                )
            )

        inventory_index = {
            normalize_text(name): idx
            for idx, name in inventory_df["product_name"].items()
        }
        projections: list[SalesInvoiceStockProjection] = []
        for key, sold_qty in aggregated.items():
            idx = inventory_index.get(key)
            if idx is None:
                continue
            current_qty = int(inventory_df.at[idx, "quantity"])
            new_qty = current_qty - sold_qty
            projections.append(
                SalesInvoiceStockProjection(
                    product_name=str(
                        inventory_df.at[idx, "product_name"]
                    ).strip(),
                    current_qty=current_qty,
                    sold_qty=sold_qty,
                    new_qty=new_qty,
                )
            )

        return SalesInvoicePreviewData(
            lines=preview_lines,
            total_lines=len(valid_lines),
            total_quantity=total_qty,
            total_amount=total_amount,
            invalid_count=invalid_count,
            projections=projections,
        )
