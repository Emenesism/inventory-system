from __future__ import annotations

import logging

from PySide6.QtCore import QObject

from app.models.errors import InventoryFileError
from app.services.inventory_service import InventoryService
from app.services.sales_import_service import SalesImportService
from app.ui.pages.sales_import_page import SalesImportPage
from app.ui.widgets.toast import ToastManager
from app.utils import dialogs


class SalesImportController(QObject):
    def __init__(
        self,
        page: SalesImportPage,
        inventory_service: InventoryService,
        sales_service: SalesImportService,
        toast: ToastManager,
        on_inventory_updated,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.page = page
        self.inventory_service = inventory_service
        self.sales_service = sales_service
        self.toast = toast
        self.on_inventory_updated = on_inventory_updated
        self._logger = logging.getLogger(self.__class__.__name__)

        self.page.preview_requested.connect(self.preview)
        self.page.apply_requested.connect(self.apply)

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

        self.toast.show("Sales import applied", "success")
