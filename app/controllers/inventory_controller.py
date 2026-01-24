from __future__ import annotations

import logging

from PySide6.QtCore import QObject

from app.models.errors import InventoryFileError
from app.services.inventory_service import InventoryService
from app.ui.pages.inventory_page import InventoryPage
from app.ui.widgets.toast import ToastManager
from app.utils import dialogs


class InventoryController(QObject):
    def __init__(
        self,
        page: InventoryPage,
        inventory_service: InventoryService,
        toast: ToastManager,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.page = page
        self.inventory_service = inventory_service
        self.toast = toast
        self._logger = logging.getLogger(self.__class__.__name__)

        self.page.reload_requested.connect(self.reload)
        self.page.save_requested.connect(self.save)

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
            self.inventory_service.save(df)
        except InventoryFileError as exc:
            dialogs.show_error(self.page, "Inventory Error", str(exc))
            self.toast.show("Inventory save failed", "error")
            self._logger.exception("Failed to save inventory")
            return
        self.toast.show("Inventory saved", "success")
