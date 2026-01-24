from __future__ import annotations

import logging

from PySide6.QtCore import QObject

from app.services.inventory_service import InventoryService
from app.services.purchase_service import PurchaseLine, PurchaseService
from app.ui.pages.purchase_invoice_page import PurchaseInvoicePage
from app.ui.widgets.toast import ToastManager
from app.utils import dialogs


class PurchaseInvoiceController(QObject):
    def __init__(
        self,
        page: PurchaseInvoicePage,
        inventory_service: InventoryService,
        purchase_service: PurchaseService,
        toast: ToastManager,
        on_inventory_updated,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.page = page
        self.inventory_service = inventory_service
        self.purchase_service = purchase_service
        self.toast = toast
        self.on_inventory_updated = on_inventory_updated
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

        allow_create = True
        if missing:
            allow_create = dialogs.ask_yes_no(
                self.page,
                "Create Products",
                "The following products are new:\n\n"
                + "\n".join(sorted(set(missing)))
                + "\n\nCreate them?",
            )

        try:
            updated_df, summary, errors = self.purchase_service.apply_purchases(
                valid_lines, inventory_df, allow_create=allow_create
            )
            self.inventory_service.save(updated_df)
            self.on_inventory_updated()
        except Exception as exc:  # noqa: BLE001
            dialogs.show_error(self.page, "Purchase Invoice", str(exc))
            self.toast.show("Purchase invoice failed", "error")
            self._logger.exception("Failed to apply purchase invoice")
            return

        message = f"Updated {summary.updated} items, created {summary.created} new items."
        if invalid:
            message += f" Skipped {invalid} invalid lines."
        if errors:
            message += f" Skipped {len(errors)} new items (not created)."
        self.toast.show(message, "success")
