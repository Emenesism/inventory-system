from __future__ import annotations

import logging

from PySide6.QtCore import QObject

from app.models.errors import InventoryFileError
from app.services.inventory_service import InventoryService
from app.ui.pages.batch_price_page import BatchPricePage
from app.ui.widgets.toast import ToastManager
from app.utils import dialogs


class BatchPriceController(QObject):
    def __init__(
        self,
        page: BatchPricePage,
        inventory_service: InventoryService,
        toast: ToastManager,
        on_inventory_updated,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.page = page
        self.inventory_service = inventory_service
        self.toast = toast
        self.on_inventory_updated = on_inventory_updated
        self._logger = logging.getLogger(self.__class__.__name__)

        self.page.apply_requested.connect(self.apply)

    def apply(self, mode: str, direction: str, value: float) -> None:
        if not self.inventory_service.is_loaded():
            dialogs.show_error(
                self.page, "Inventory Error", "Load inventory first."
            )
            self.toast.show("Inventory not loaded", "error")
            return

        change_text = f"{value:.2f}%" if mode == "percent" else f"{value:.2f}"
        question = f"{direction.title()} all buy prices by {change_text}?"
        if not dialogs.ask_yes_no(self.page, "Batch Price Update", question):
            return

        try:
            df = self.inventory_service.get_dataframe().copy()
            prices = df["avg_buy_price"].astype(float)

            if mode == "percent":
                factor = value / 100.0
                if direction == "increase":
                    prices = prices * (1 + factor)
                else:
                    prices = prices * (1 - factor)
            else:
                if direction == "increase":
                    prices = prices + value
                else:
                    prices = prices - value

            prices = prices.clip(lower=0)
            df["avg_buy_price"] = prices.round(4)

            self.inventory_service.save(df)
            self.on_inventory_updated()
        except (InventoryFileError, KeyError, ValueError) as exc:
            dialogs.show_error(self.page, "Batch Price Update", str(exc))
            self.toast.show("Price update failed", "error")
            self._logger.exception("Batch price update failed")
            return

        self.toast.show("Prices updated", "success")
