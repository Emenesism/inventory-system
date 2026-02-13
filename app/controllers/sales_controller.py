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
                self.page,
                self.tr("خطای موجودی"),
                self.tr("ابتدا موجودی را بارگذاری کنید."),
            )
            self.toast.show(self.tr("موجودی بارگذاری نشده است"), "error")
            return
        try:
            sales_df = self.sales_service.load_sales_file(path)
            inventory_df = self.inventory_service.get_dataframe()
            preview_rows, summary = self.sales_service.preview(
                sales_df, inventory_df
            )
        except InventoryFileError as exc:
            dialogs.show_error(self.page, self.tr("خطای ورود فروش"), str(exc))
            self.toast.show(self.tr("پیش‌نمایش فروش ناموفق بود"), "error")
            self._logger.exception("Failed to preview sales import")
            return

        self.page.set_edit_mode(
            True, self.inventory_service.get_product_names()
        )
        self.page.set_preview(preview_rows, summary)
        self.toast.show(self.tr("پیش‌نمایش آماده است"), "success")

    def apply(self) -> None:
        if not self.inventory_service.is_loaded():
            dialogs.show_error(
                self.page,
                self.tr("خطای موجودی"),
                self.tr("ابتدا موجودی را بارگذاری کنید."),
            )
            self.toast.show(self.tr("موجودی بارگذاری نشده است"), "error")
            return
        if not self.page.preview_rows:
            dialogs.show_error(
                self.page,
                self.tr("ورود فروش"),
                self.tr("ابتدا پیش‌نمایش را بارگذاری کنید."),
            )
            self.toast.show(self.tr("پیش‌نمایشی بارگذاری نشده است"), "error")
            return

        ok_count = sum(
            1 for row in self.page.preview_rows if row.status == "OK"
        )
        error_count = len(self.page.preview_rows) - ok_count
        if ok_count == 0:
            dialogs.show_error(
                self.page,
                self.tr("ورود فروش"),
                self.tr("هیچ ردیف معتبری برای اعمال وجود ندارد."),
            )
            self.toast.show(
                self.tr("هیچ ردیف معتبری برای اعمال وجود ندارد"), "error"
            )
            return

        self.page.flush_pending_edits()

        invoice_name = None
        try:
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
                preview_lines, error_count
            )
            preview_dialog = SalesInvoicePreviewDialog(self.page, preview_data)
            if preview_dialog.exec() != QDialog.Accepted:
                self.toast.show(self.tr("ثبت فروش لغو شد"), "info")
                return
            invoice_name = preview_dialog.invoice_name()
        except Exception:  # noqa: BLE001
            self._logger.exception("Failed to prepare sales import preview")
            dialogs.show_error(
                self.page,
                self.tr("ورود فروش"),
                self.tr("ساخت پیش‌نمایش فاکتور ناموفق بود."),
            )
            self.toast.show(self.tr("پیش‌نمایش فروش ناموفق بود"), "error")
            return

        admin = (
            self._current_admin_provider()
            if self._current_admin_provider
            else None
        )
        admin_username = admin.username if admin else None
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
                invoice_type = self.page.get_sales_invoice_type()
                invoice_id = self.invoice_service.create_sales_invoice(
                    sales_lines,
                    invoice_name=invoice_name,
                    admin_id=admin.admin_id if admin else None,
                    admin_username=admin_username,
                    invoice_type=invoice_type,
                )
                if self._action_log_service:
                    total_qty = sum(line.quantity for line in sales_lines)
                    total_amount = sum(
                        line.price * line.quantity for line in sales_lines
                    )
                    details = self.tr(
                        "شماره فاکتور: {invoice_id}\n"
                        "تعداد ردیف‌ها: {line_count}\n"
                        "تعداد کل: {total_qty}\n"
                        "مبلغ کل: {total_amount}"
                    ).format(
                        invoice_id=invoice_id,
                        line_count=len(sales_lines),
                        total_qty=total_qty,
                        total_amount=f"{total_amount:,.0f}",
                    )
                    self._action_log_service.log_action(
                        "sales_import",
                        self.tr("ثبت فاکتور فروش"),
                        details,
                        admin=admin,
                    )
                self.inventory_service.load()
                self.on_inventory_updated()
                self.on_invoices_updated()
        except Exception as exc:  # noqa: BLE001
            dialogs.show_error(self.page, self.tr("ورود فروش"), str(exc))
            self.toast.show(self.tr("ثبت فروش ناموفق بود"), "error")
            self._logger.exception("Failed to apply sales import")
            return

        self.page.reset_after_apply()
        self.toast.show(self.tr("ورود فروش اعمال شد"), "success")

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
                self.page,
                self.tr("خروجی فروش"),
                self.tr("ابتدا پیش‌نمایش را بارگذاری کنید."),
            )
            return
        if not self.inventory_service.is_loaded():
            dialogs.show_error(
                self.page,
                self.tr("خطای موجودی"),
                self.tr("ابتدا موجودی را بارگذاری کنید."),
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
                self.tr("خروجی فروش"),
                self.tr("موردی برای خروجیِ خطا یا تطبیق تقریبی وجود ندارد."),
            )
            return

        from PySide6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getSaveFileName(
            self.page,
            self.tr("خروجی مغایرت‌های فروش"),
            "sales_import_review.xlsx",
            self.tr("فایل‌های اکسل (*.xlsx)"),
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".xlsx"):
            file_path = f"{file_path}.xlsx"

        try:
            import pandas as pd
        except Exception as exc:  # noqa: BLE001
            dialogs.show_error(self.page, self.tr("خروجی فروش"), str(exc))
            return

        inventory_df = self.inventory_service.get_dataframe()
        stock_map = {}
        for _, inv_row in inventory_df.iterrows():
            key = normalize_text(inv_row.get("product_name", ""))
            if key:
                stock_map[key] = inv_row

        def _translate_status(status: str) -> str:
            return {
                "OK": self.tr("موفق"),
                "Error": self.tr("خطا"),
            }.get(status, status)

        def _translate_message(message: str) -> str:
            if message.startswith("Matched to "):
                matched = message.replace("Matched to ", "", 1).strip()
                return self.tr("مطابقت با {matched}").format(matched=matched)
            return {
                "Product not found": self.tr("کالا یافت نشد"),
                "Missing product name": self.tr("نام کالا خالی است"),
                "Invalid quantity": self.tr("تعداد نامعتبر است"),
                "Will update stock": self.tr("موجودی بروزرسانی می‌شود"),
            }.get(message, message)

        def _translate_inventory_columns(columns: list[str]) -> dict[str, str]:
            mapping = {
                "product_name": self.tr("نام محصول"),
                "quantity": self.tr("تعداد"),
                "avg_buy_price": self.tr("میانگین قیمت خرید"),
                "alarm": self.tr("آلارم"),
                "source": self.tr("منبع"),
                "category": self.tr("دسته‌بندی"),
                "brand": self.tr("برند"),
                "sku": self.tr("کد کالا"),
                "code": self.tr("کد"),
                "barcode": self.tr("بارکد"),
                "size": self.tr("سایز"),
                "color": self.tr("رنگ"),
                "description": self.tr("توضیحات"),
                "notes": self.tr("یادداشت"),
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
                        translated[col] = self.tr("ستون {col}").format(col=col)
            return translated

        inventory_columns = list(inventory_df.columns)
        inventory_label_map = _translate_inventory_columns(inventory_columns)

        not_found_payload = []
        for row in not_found_rows:
            not_found_payload.append(
                {
                    self.tr("نام محصول فروش"): row.product_name,
                    self.tr("تعداد فروش"): row.quantity_sold,
                    self.tr("وضعیت"): _translate_status(row.status),
                    self.tr("پیام"): _translate_message(row.message),
                }
            )

        fuzzy_payload = []
        for row in fuzzy_rows:
            record = {
                self.tr("نام محصول فروش"): row.product_name,
                self.tr("تعداد فروش"): row.quantity_sold,
                self.tr("محصول مطابق"): row.resolved_name,
                self.tr("وضعیت"): self.tr("مطابقت تقریبی"),
                self.tr("پیام"): _translate_message(row.message),
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
                        writer,
                        index=False,
                        sheet_name=self.tr("یافت نشد"),
                    )
                if fuzzy_payload:
                    pd.DataFrame(fuzzy_payload).to_excel(
                        writer,
                        index=False,
                        sheet_name=self.tr("مطابقت تقریبی"),
                    )
            ensure_sheet_rtl(file_path)
            apply_banded_rows(file_path)
            autofit_columns(file_path)
        except Exception as exc:  # noqa: BLE001
            dialogs.show_error(self.page, self.tr("خروجی فروش"), str(exc))
            self._logger.exception("Failed to export sales issues")
            return

        if self._action_log_service:
            admin = (
                self._current_admin_provider()
                if self._current_admin_provider
                else None
            )
            details = self.tr(
                "موارد یافت نشد: {missing}\n"
                "موارد تطبیق تقریبی: {fuzzy}\n"
                "مسیر: {path}"
            ).format(
                missing=len(not_found_payload),
                fuzzy=len(fuzzy_payload),
                path=file_path,
            )
            self._action_log_service.log_action(
                "sales_import_export",
                self.tr("خروجی مغایرت‌های فروش"),
                details,
                admin=admin,
            )

        self.toast.show(self.tr("خروجی فروش انجام شد"), "success")

    def open_manual_invoice(self) -> None:
        if not self.inventory_service.is_loaded():
            dialogs.show_error(
                self.page,
                self.tr("خطای موجودی"),
                self.tr("ابتدا موجودی را بارگذاری کنید."),
            )
            self.toast.show(self.tr("موجودی بارگذاری نشده است"), "error")
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
                dialog,
                self.tr("خطای موجودی"),
                self.tr("ابتدا موجودی را بارگذاری کنید."),
            )
            self.toast.show(self.tr("موجودی بارگذاری نشده است"), "error")
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
                self.tr("فاکتور فروش دستی"),
                self.tr("حداقل یک ردیف معتبر اضافه کنید."),
            )
            self.toast.show(self.tr("هیچ ردیف فروش معتبری وجود ندارد"), "error")
            return

        try:
            import pandas as pd
        except Exception as exc:  # noqa: BLE001
            dialogs.show_error(dialog, self.tr("فاکتور فروش دستی"), str(exc))
            self.toast.show(self.tr("ثبت فاکتور فروش دستی ناموفق بود"), "error")
            return

        manual_df = pd.DataFrame(
            [
                {
                    "product_name": line.product_name,
                    "quantity_sold": line.quantity,
                    "sell_price": line.price,
                }
                for line in valid_lines
            ]
        )
        try:
            preview_rows, preview_summary = self.sales_service.preview(
                manual_df, None
            )
        except Exception as exc:  # noqa: BLE001
            dialogs.show_error(dialog, self.tr("فاکتور فروش دستی"), str(exc))
            self.toast.show(self.tr("ثبت فاکتور فروش دستی ناموفق بود"), "error")
            return

        priced_lines = [
            SalesManualLine(
                product_name=row.resolved_name or row.product_name,
                quantity=row.quantity_sold,
                price=row.sell_price,
            )
            for row in preview_rows
            if row.status == "OK"
        ]
        if not priced_lines:
            dialogs.show_error(
                dialog,
                self.tr("فاکتور فروش دستی"),
                self.tr("هیچ ردیف معتبری برای ثبت وجود ندارد."),
            )
            self.toast.show(self.tr("هیچ ردیف فروش معتبری وجود ندارد"), "error")
            return

        preview_data = self._build_sales_preview_data(
            priced_lines, invalid + preview_summary.errors
        )
        preview_dialog = SalesInvoicePreviewDialog(dialog, preview_data)
        if preview_dialog.exec() != QDialog.Accepted:
            self.toast.show(self.tr("فاکتور فروش دستی لغو شد"), "info")
            return
        invoice_name = preview_dialog.invoice_name()

        admin = (
            self._current_admin_provider()
            if self._current_admin_provider
            else None
        )
        admin_username = admin.username if admin else None
        try:
            sales_lines = [
                SalesLine(
                    product_name=row.resolved_name or row.product_name,
                    price=row.sell_price,
                    quantity=row.quantity_sold,
                    cost_price=row.cost_price,
                )
                for row in preview_rows
                if row.status == "OK"
            ]
            invoice_id = self.invoice_service.create_sales_invoice(
                sales_lines,
                invoice_name=invoice_name,
                admin_id=admin.admin_id if admin else None,
                admin_username=admin_username,
                invoice_type="sales_manual",
            )
            if self._action_log_service:
                total_qty = sum(line.quantity for line in sales_lines)
                total_amount = sum(
                    line.price * line.quantity for line in sales_lines
                )
                details = self.tr(
                    "شماره فاکتور: {invoice_id}\n"
                    "تعداد ردیف‌ها: {line_count}\n"
                    "تعداد کل: {total_qty}\n"
                    "مبلغ کل: {total_amount}"
                ).format(
                    invoice_id=invoice_id,
                    line_count=len(sales_lines),
                    total_qty=total_qty,
                    total_amount=f"{total_amount:,.0f}",
                )
                self._action_log_service.log_action(
                    "sales_manual_invoice",
                    self.tr("ثبت فاکتور فروش دستی"),
                    details,
                    admin=admin,
                )
            self.inventory_service.load()
            self.on_inventory_updated()
            self.on_invoices_updated()
        except Exception as exc:  # noqa: BLE001
            dialogs.show_error(dialog, self.tr("فاکتور فروش دستی"), str(exc))
            self.toast.show(self.tr("ثبت فاکتور فروش دستی ناموفق بود"), "error")
            self._logger.exception("Failed to apply manual sales invoice")
            return

        if invalid:
            self.toast.show(
                self.tr(
                    "فاکتور فروش دستی ذخیره شد ({count} ردیف نامعتبر نادیده گرفته شد)."
                ).format(count=invalid),
                "success",
            )
        else:
            self.toast.show(self.tr("فاکتور فروش دستی ذخیره شد"), "success")
        dialog.accept()

    def _build_sales_preview_data(
        self,
        valid_lines: list[SalesManualLine],
        invalid_count: int,
    ) -> SalesInvoicePreviewData:
        preview_lines: list[SalesInvoicePreviewLine] = []
        total_qty = 0
        total_amount = 0.0

        for line in valid_lines:
            line_total = line.price * line.quantity
            total_qty += line.quantity
            total_amount += line_total
            preview_lines.append(
                SalesInvoicePreviewLine(
                    product_name=line.product_name,
                    price=line.price,
                    quantity=line.quantity,
                    line_total=line_total,
                )
            )

        return SalesInvoicePreviewData(
            lines=preview_lines,
            total_lines=len(valid_lines),
            total_quantity=total_qty,
            total_amount=total_amount,
            invalid_count=invalid_count,
            projections=[],
        )
