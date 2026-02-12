from __future__ import annotations

import logging

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QDialog

from app.services.action_log_service import ActionLogService
from app.services.inventory_service import InventoryService
from app.services.invoice_service import InvoiceService
from app.services.purchase_service import PurchaseLine, PurchaseService
from app.ui.pages.purchase_invoice_page import PurchaseInvoicePage
from app.ui.widgets.purchase_invoice_preview_dialog import (
    PurchaseInvoicePreviewData,
    PurchaseInvoicePreviewDialog,
    PurchaseInvoicePreviewLine,
)
from app.ui.widgets.toast import ToastManager
from app.utils import dialogs


class PurchaseInvoiceController(QObject):
    def __init__(
        self,
        page: PurchaseInvoicePage,
        inventory_service: InventoryService,
        purchase_service: PurchaseService,
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
        self.purchase_service = purchase_service
        self.invoice_service = invoice_service
        self.toast = toast
        self.on_inventory_updated = on_inventory_updated
        self.on_invoices_updated = on_invoices_updated
        self._current_admin_provider = current_admin_provider
        self._logger = logging.getLogger(self.__class__.__name__)
        self._action_log_service = action_log_service

        self.page.submit_requested.connect(self.submit)

    def submit(self, lines: list[PurchaseLine]) -> None:
        if not self.inventory_service.is_loaded():
            dialogs.show_error(
                self.page, "Inventory Error", "Load inventory first."
            )
            self.toast.show("Inventory not loaded", "error")
            return
        valid_lines: list[PurchaseLine] = []
        invalid = 0
        for line in lines:
            if not line.product_name:
                invalid += 1
                continue
            if line.price <= 0 or line.quantity <= 0:
                invalid += 1
                continue
            valid_lines.append(line)

        if not valid_lines:
            dialogs.show_error(
                self.page, "Purchase Invoice", "Add at least one valid line."
            )
            self.toast.show("No valid purchase lines", "error")
            return

        preview_data = self._build_preview_data(valid_lines, invalid)
        dialog = PurchaseInvoicePreviewDialog(self.page, preview_data)
        if dialog.exec() != QDialog.Accepted:
            self.toast.show("Purchase invoice canceled", "info")
            return
        invoice_name = dialog.invoice_name()

        admin = (
            self._current_admin_provider()
            if self._current_admin_provider
            else None
        )
        admin_username = admin.username if admin else None
        try:
            invoice_id = self.invoice_service.create_purchase_invoice(
                valid_lines,
                invoice_name=invoice_name,
                admin_id=admin.admin_id if admin else None,
                admin_username=admin_username,
            )
            self.inventory_service.load()
            self.on_inventory_updated()
            if self._action_log_service:
                total_qty = sum(line.quantity for line in valid_lines)
                total_amount = sum(
                    line.price * line.quantity for line in valid_lines
                )
                details = (
                    f"شماره فاکتور: {invoice_id}\n"
                    f"تعداد ردیف‌ها: {len(valid_lines)}\n"
                    f"تعداد کل: {total_qty}\n"
                    f"مبلغ کل: {total_amount:,.0f}"
                )
                self._action_log_service.log_action(
                    "purchase_invoice",
                    "ثبت فاکتور خرید",
                    details,
                    admin=admin,
                )
            self.on_invoices_updated()
        except Exception as exc:  # noqa: BLE001
            dialogs.show_error(self.page, "Purchase Invoice", str(exc))
            self.toast.show("Purchase invoice failed", "error")
            self._logger.exception("Failed to create purchase invoice")
            return

        message = "Purchase invoice saved."
        if invalid:
            message += f" Skipped {invalid} invalid lines."
        self.toast.show(message, "success")
        self.page.reset_after_submit()

    def _build_preview_data(
        self,
        valid_lines: list[PurchaseLine],
        invalid_count: int,
    ) -> PurchaseInvoicePreviewData:
        preview_lines: list[PurchaseInvoicePreviewLine] = []
        total_qty = 0
        total_cost = 0.0

        for line in valid_lines:
            line_total = line.price * line.quantity
            total_qty += line.quantity
            total_cost += line_total
            preview_lines.append(
                PurchaseInvoicePreviewLine(
                    product_name=line.product_name,
                    price=line.price,
                    quantity=line.quantity,
                    line_total=line_total,
                )
            )

        return PurchaseInvoicePreviewData(
            lines=preview_lines,
            total_lines=len(valid_lines),
            total_quantity=total_qty,
            total_cost=total_cost,
            invalid_count=invalid_count,
            projections=[],
        )
