from __future__ import annotations

import logging

from PySide6.QtCore import QObject

from app.services.inventory_service import InventoryService
from app.services.invoice_service import InvoiceService
from app.services.purchase_service import PurchaseLine, PurchaseService
from app.ui.pages.purchase_invoice_page import PurchaseInvoicePage
from app.ui.widgets.toast import ToastManager
from app.utils import dialogs
from app.utils.numeric import format_amount


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
    ) -> None:
        super().__init__(parent)
        self.page = page
        self.inventory_service = inventory_service
        self.purchase_service = purchase_service
        self.invoice_service = invoice_service
        self.toast = toast
        self.on_inventory_updated = on_inventory_updated
        self.on_invoices_updated = on_invoices_updated
        self._logger = logging.getLogger(self.__class__.__name__)

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

        inventory_df = self.inventory_service.get_dataframe()
        missing = [
            line.product_name
            for line in valid_lines
            if self.inventory_service.find_index(line.product_name) is None
        ]

        if missing:
            dialogs.show_error(
                self.page,
                "Purchase Invoice",
                "Product(s) not found:\n\n" + "\n".join(sorted(set(missing))),
            )
            self.toast.show("Product(s) not found", "error")
            return

        preview_message = self._build_preview_message(
            valid_lines, inventory_df, invalid
        )
        if not dialogs.ask_yes_no(
            self.page, "Purchase Invoice Preview", preview_message
        ):
            self.toast.show("Purchase invoice canceled", "info")
            return

        try:
            updated_df, summary, errors = self.purchase_service.apply_purchases(
                valid_lines, inventory_df, allow_create=False
            )
            self.inventory_service.save(updated_df)
            self.on_inventory_updated()
        except Exception as exc:  # noqa: BLE001
            dialogs.show_error(self.page, "Purchase Invoice", str(exc))
            self.toast.show("Purchase invoice failed", "error")
            self._logger.exception("Failed to apply purchase invoice")
            return

        try:
            self.invoice_service.create_purchase_invoice(valid_lines)
            self.on_invoices_updated()
        except Exception as exc:  # noqa: BLE001
            self.toast.show("Invoice saved, history not updated", "error")
            self._logger.exception("Failed to store invoice history")

        message = f"Updated {summary.updated} items, created {summary.created} new items."
        if invalid:
            message += f" Skipped {invalid} invalid lines."
        if errors:
            message += f" Skipped {len(errors)} new items (not created)."
        self.toast.show(message, "success")
        self.page.reset_after_submit()

    def _build_preview_message(
        self,
        valid_lines: list[PurchaseLine],
        inventory_df,
        invalid_count: int,
    ) -> str:
        lines_out: list[str] = []
        total_qty = 0
        total_cost = 0.0
        aggregated: dict[str, int] = {}

        for idx, line in enumerate(valid_lines, start=1):
            line_total = line.price * line.quantity
            total_qty += line.quantity
            total_cost += line_total
            aggregated[line.product_name] = (
                aggregated.get(line.product_name, 0) + line.quantity
            )
            lines_out.append(
                f"{idx}) {line.product_name} | Buy price: {format_amount(line.price)} | "
                f"Qty: {line.quantity} | Line total: {format_amount(line_total)}"
            )

        totals = [
            f"Total lines: {len(valid_lines)}",
            f"Total quantity: {total_qty}",
            f"Total cost: {format_amount(total_cost)}",
        ]
        if invalid_count:
            totals.append(f"Skipped invalid lines: {invalid_count}")

        stock_lines: list[str] = []
        for product_name, add_qty in aggregated.items():
            index = self.inventory_service.find_index(product_name)
            current_qty = int(inventory_df.loc[index, "quantity"])
            new_qty = current_qty + add_qty
            stock_lines.append(
                f"{product_name}: current {current_qty} + add {add_qty} = {new_qty}"
            )

        message_parts = [
            "Please review the purchase invoice before submitting.",
            "",
            "Lines:",
            *lines_out,
            "",
            "Totals:",
            *totals,
            "",
            "Projected stock after submit:",
            *stock_lines,
            "",
            "Submit this invoice?",
        ]
        return "\n".join(message_parts)
