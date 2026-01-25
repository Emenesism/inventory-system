from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.controllers.inventory_controller import InventoryController
from app.controllers.purchase_controller import PurchaseInvoiceController
from app.controllers.sales_controller import SalesImportController
from app.core.config import AppConfig
from app.core.logging_setup import LOG_DIR
from app.models.errors import InventoryFileError
from app.services.inventory_service import InventoryService
from app.services.invoice_service import InvoiceService
from app.services.purchase_service import PurchaseService
from app.services.sales_import_service import SalesImportService
from app.ui.pages.inventory_page import InventoryPage
from app.ui.pages.invoices_page import InvoicesPage
from app.ui.pages.purchase_invoice_page import PurchaseInvoicePage
from app.ui.pages.reports_page import ReportsPage
from app.ui.pages.sales_import_page import SalesImportPage
from app.ui.theme import get_stylesheet
from app.ui.widgets.header import HeaderBar
from app.ui.widgets.sidebar import Sidebar
from app.ui.widgets.toast import ToastManager
from app.utils import dialogs


class MainWindow(QMainWindow):
    def __init__(
        self, inventory_service: InventoryService, config: AppConfig
    ) -> None:
        super().__init__()
        self.inventory_service = inventory_service
        self.config = config
        self._logger = logging.getLogger(self.__class__.__name__)
        self.setWindowTitle("Armkala Inventory Suite")
        self.resize(1280, 800)

        self.toast = ToastManager(self)

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.page_selected.connect(self._switch_page)
        layout.addWidget(self.sidebar, 1)

        main_area = QWidget()
        main_layout = QVBoxLayout(main_area)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.header = HeaderBar()
        self.header.inventory_requested.connect(self.choose_inventory_file)
        self.header.theme_toggle_requested.connect(self.toggle_theme)
        main_layout.addWidget(self.header)

        self.pages = QStackedWidget()
        main_layout.addWidget(self.pages, 1)
        layout.addWidget(main_area, 4)
        self.setCentralWidget(container)

        self.inventory_page = InventoryPage()
        self.sales_page = SalesImportPage()
        self.purchase_page = PurchaseInvoicePage()
        self.invoice_service = InvoiceService()
        self.invoices_page = InvoicesPage(self.invoice_service)
        self.reports_page = ReportsPage(LOG_DIR / "app.log")

        self.pages.addWidget(self.inventory_page)
        self.pages.addWidget(self.sales_page)
        self.pages.addWidget(self.purchase_page)
        self.pages.addWidget(self.invoices_page)
        self.pages.addWidget(self.reports_page)

        self.sidebar.set_active("Inventory")
        self.pages.setCurrentWidget(self.inventory_page)

        self.inventory_controller = InventoryController(
            self.inventory_page, self.inventory_service, self.toast, self
        )
        self.sales_controller = SalesImportController(
            self.sales_page,
            self.inventory_service,
            SalesImportService(),
            self.toast,
            self.refresh_inventory_views,
            self,
        )
        self.purchase_controller = PurchaseInvoiceController(
            self.purchase_page,
            self.inventory_service,
            PurchaseService(),
            self.invoice_service,
            self.toast,
            self.refresh_inventory_views,
            self.invoices_page.refresh,
            self,
        )

        self.purchase_page.set_product_provider(
            self.inventory_service.get_product_names
        )

        self.apply_theme(self.config.theme)
        self.initialize_inventory()

    def initialize_inventory(self) -> None:
        default_path = Path(__file__).resolve().parents[2] / "stock.xlsx"
        if not self.config.inventory_file and default_path.exists():
            self.config.inventory_file = str(default_path)
            self.config.save()

        if self.config.inventory_file:
            self.inventory_service.set_inventory_path(
                self.config.inventory_file
            )
            try:
                self.inventory_service.load()
                self.refresh_inventory_views()
                self.toast.show("Inventory loaded", "success")
                return
            except InventoryFileError as exc:
                dialogs.show_error(self, "Inventory Error", str(exc))
                self.toast.show("Inventory load failed", "error")
                self._logger.exception("Inventory load failed")
                self.inventory_service.set_inventory_path(None)

        self.choose_inventory_file()
        if not self.inventory_service.is_loaded():
            self.disable_inventory_features("No inventory file loaded")

    def choose_inventory_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Inventory File",
            "",
            "Excel Files (*.xlsx *.xlsm);;CSV Files (*.csv)",
        )
        if not file_path:
            return

        self.inventory_service.store.set_path(file_path)
        try:
            self.inventory_service.load()
        except InventoryFileError as exc:
            dialogs.show_error(self, "Inventory Error", str(exc))
            self.toast.show("Inventory load failed", "error")
            self._logger.exception("Inventory load failed")
            self.disable_inventory_features("Inventory file invalid")
            self.inventory_service.set_inventory_path(None)
            return

        self.inventory_service.set_inventory_path(file_path)
        self.refresh_inventory_views()
        self.toast.show("Inventory file loaded", "success")

    def refresh_inventory_views(self) -> None:
        if not self.inventory_service.is_loaded():
            self.disable_inventory_features("Inventory not loaded")
            return

        df = self.inventory_service.get_dataframe()
        self.inventory_page.set_inventory(df)
        self.purchase_page.set_product_provider(
            self.inventory_service.get_product_names
        )
        self.sales_page.set_enabled_state(True)
        self.purchase_page.set_enabled_state(True)
        self.inventory_page.set_enabled_state(True)
        self._update_status()

    def disable_inventory_features(self, status: str) -> None:
        self.sales_page.set_enabled_state(False)
        self.purchase_page.set_enabled_state(False)
        self.inventory_page.set_enabled_state(False)
        self.header.set_status(status)

    def _update_status(self) -> None:
        if not self.inventory_service.is_loaded():
            self.header.set_status("No inventory loaded")
            return
        df = self.inventory_service.get_dataframe()
        file_name = (
            Path(self.inventory_service.store.path).name
            if self.inventory_service.store.path
            else ""
        )
        file_name = (
            Path(self.inventory_service.store.path).name
            if self.inventory_service.store.path
            else ""
        )
        self.header.set_status(f"{file_name} | {len(df)} products")

    def _switch_page(self, name: str) -> None:
        pages = {
            "Inventory": self.inventory_page,
            "Sales Import": self.sales_page,
            "Purchase Invoice": self.purchase_page,
            "Invoices": self.invoices_page,
            "Reports/Logs": self.reports_page,
        }
        page = pages.get(name)
        if page:
            self.pages.setCurrentWidget(page)
            self.sidebar.set_active(name)

    def toggle_theme(self) -> None:
        self.config.theme = "dark" if self.config.theme == "light" else "light"
        self.config.save()
        self.apply_theme(self.config.theme)

    def apply_theme(self, theme: str) -> None:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app:
            app.setStyleSheet(get_stylesheet(theme))
        self.header.set_theme_label(theme)
