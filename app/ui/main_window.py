from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGraphicsBlurEffect,
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
from app.services.action_log_service import ActionLogService
from app.services.admin_service import AdminService, AdminUser
from app.services.inventory_service import InventoryService
from app.services.invoice_service import InvoiceService
from app.services.purchase_service import PurchaseService
from app.services.sales_import_service import SalesImportService
from app.ui.pages.actions_page import ActionsPage
from app.ui.pages.analytics_page import AnalyticsPage
from app.ui.pages.basalam_page import BasalamPage
from app.ui.pages.inventory_page import InventoryPage
from app.ui.pages.invoices_page import InvoicesPage
from app.ui.pages.low_stock_page import LowStockPage
from app.ui.pages.purchase_invoice_page import PurchaseInvoicePage
from app.ui.pages.reports_page import ReportsPage
from app.ui.pages.sales_import_page import SalesImportPage
from app.ui.pages.settings_page import SettingsPage
from app.ui.theme import get_stylesheet
from app.ui.widgets.header import HeaderBar
from app.ui.widgets.lock_dialog import LockDialog
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
        self._lock_shown = False
        self._lock_open = False
        self._current_admin: AdminUser | None = None
        self._last_activity = time.monotonic()

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
        self.header.lock_requested.connect(self.lock)
        main_layout.addWidget(self.header)

        self.pages = QStackedWidget()
        main_layout.addWidget(self.pages, 1)
        layout.addWidget(main_area, 4)
        self.setCentralWidget(container)

        self.inventory_page = InventoryPage()
        self.sales_page = SalesImportPage()
        self.purchase_page = PurchaseInvoicePage()
        backup_dir = (
            Path(self.config.backup_dir) if self.config.backup_dir else None
        )
        self.invoice_service = InvoiceService(backup_dir=backup_dir)
        self.admin_service = AdminService()
        self.action_log_service = ActionLogService()
        self.invoices_page = InvoicesPage(
            self.invoice_service,
            self.inventory_service,
            self.toast,
            self.refresh_inventory_views,
            self.refresh_history_views,
            self.action_log_service,
            self._get_current_admin,
        )
        self.analytics_page = AnalyticsPage(self.invoice_service)
        self.low_stock_page = LowStockPage(
            self.inventory_service,
            self.config,
            self.action_log_service,
            self._get_current_admin,
        )
        self.basalam_page = BasalamPage(
            self.config, self.action_log_service, self._get_current_admin
        )
        self.actions_page = ActionsPage(self.action_log_service)
        self.reports_page = ReportsPage(
            LOG_DIR / "app.log",
            self.action_log_service,
            self._get_current_admin,
        )
        self.settings_page = SettingsPage(
            self.config,
            self.invoice_service,
            self.admin_service,
            self.apply_theme,
            self._set_current_admin,
            self.action_log_service,
            self._get_current_admin,
        )

        self.pages.addWidget(self.inventory_page)
        self.pages.addWidget(self.sales_page)
        self.pages.addWidget(self.purchase_page)
        self.pages.addWidget(self.invoices_page)
        self.pages.addWidget(self.analytics_page)
        self.pages.addWidget(self.low_stock_page)
        self.pages.addWidget(self.basalam_page)
        self.pages.addWidget(self.actions_page)
        self.pages.addWidget(self.reports_page)
        self.pages.addWidget(self.settings_page)

        self.sidebar.set_active("Inventory")
        self.pages.setCurrentWidget(self.inventory_page)

        self.inventory_controller = InventoryController(
            self.inventory_page,
            self.inventory_service,
            self.toast,
            self.action_log_service,
            self._get_current_admin,
            self,
        )
        self.sales_controller = SalesImportController(
            self.sales_page,
            self.inventory_service,
            SalesImportService(),
            self.invoice_service,
            self.toast,
            self.refresh_inventory_views,
            self.refresh_history_views,
            self,
            current_admin_provider=self._get_current_admin,
            action_log_service=self.action_log_service,
        )
        self.purchase_controller = PurchaseInvoiceController(
            self.purchase_page,
            self.inventory_service,
            PurchaseService(),
            self.invoice_service,
            self.toast,
            self.refresh_inventory_views,
            self.refresh_history_views,
            self,
            current_admin_provider=self._get_current_admin,
            action_log_service=self.action_log_service,
        )

        self.purchase_page.set_product_provider(
            self.inventory_service.get_product_names
        )

        self.apply_theme(self.config.theme)
        self.initialize_inventory()

        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self._idle_timer = QTimer(self)
        self._idle_timer.setInterval(1000)
        self._idle_timer.timeout.connect(self._check_idle)
        self._idle_timer.start()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._lock_shown:
            self._lock_shown = True
            self._show_lock()

    def _show_lock(self) -> None:
        if self._lock_open:
            return
        self._lock_open = True
        if self._current_admin and self.action_log_service:
            self.action_log_service.log_action(
                "logout",
                "خروج از حساب",
                "قفل برنامه",
                admin=self._current_admin,
            )
        blur = QGraphicsBlurEffect(self)
        blur.setBlurRadius(12)
        if self.centralWidget():
            self.centralWidget().setGraphicsEffect(blur)
        username = self._current_admin.username if self._current_admin else ""
        dialog = LockDialog(self.admin_service, self, username=username)
        dialog.exec()
        if dialog.authenticated_admin is not None:
            self._set_current_admin(dialog.authenticated_admin)
            self._last_activity = time.monotonic()
        if self.centralWidget():
            self.centralWidget().setGraphicsEffect(None)
        self._lock_open = False

    def lock(self) -> None:
        self._show_lock()

    def _set_current_admin(self, admin: AdminUser) -> None:
        previous = self._current_admin
        self._current_admin = admin
        self.settings_page.set_current_admin(admin)
        self._apply_admin_permissions(admin)
        if self.action_log_service and (
            previous is None or previous.admin_id != admin.admin_id
        ):
            self.action_log_service.log_action(
                "login",
                "ورود به سیستم",
                f"کاربر: {admin.username}",
                admin=admin,
            )

    def _get_current_admin(self) -> AdminUser | None:
        return self._current_admin

    def _apply_admin_permissions(self, admin: AdminUser | None) -> None:
        if admin is None:
            return
        if admin.role == "employee":
            self.inventory_page.set_blocked_columns(
                ["quantity", "avg_buy_price"]
            )
            self.invoices_page.set_price_visibility(False)
            self.invoices_page.set_edit_enabled(True)
            self.actions_page.set_accessible(False)
            self.reports_page.set_accessible(False)
        else:
            self.inventory_page.set_blocked_columns(None)
            self.invoices_page.set_price_visibility(True)
            self.invoices_page.set_edit_enabled(True)
            self.actions_page.set_accessible(True)
            self.reports_page.set_accessible(True)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if not self._lock_open and event.type() in (
            QEvent.KeyPress,
            QEvent.MouseButtonPress,
            QEvent.MouseButtonDblClick,
            QEvent.MouseMove,
            QEvent.Wheel,
            QEvent.TouchBegin,
        ):
            self._last_activity = time.monotonic()
        return super().eventFilter(obj, event)

    def _check_idle(self) -> None:
        if self._lock_open or self._current_admin is None:
            return
        timeout_minutes = max(1, self._current_admin.auto_lock_minutes)
        if time.monotonic() - self._last_activity >= timeout_minutes * 60:
            self._show_lock()

    def initialize_inventory(self) -> None:
        config_path = (
            Path(self.config.inventory_file)
            if self.config.inventory_file
            else None
        )
        if config_path and not config_path.exists():
            self._logger.warning(
                "Configured inventory file missing: %s", config_path
            )
            self.config.inventory_file = None
            self.config.save()
            config_path = None

        if not config_path:
            default_path = self._find_default_inventory_path()
            if default_path is not None:
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

    @staticmethod
    def _find_default_inventory_path() -> Path | None:
        candidates: list[Path] = []
        if getattr(sys, "frozen", False):
            candidates.append(
                Path(sys.executable).resolve().parent / "stock.xlsx"
            )
        argv_path = Path(sys.argv[0]).resolve()
        candidates.append(argv_path.parent / "stock.xlsx")
        candidates.append(Path.cwd() / "stock.xlsx")
        candidates.append(Path(__file__).resolve().parents[2] / "stock.xlsx")
        for path in candidates:
            if path.exists():
                return path
        return None

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
        self.low_stock_page.set_enabled_state(True)
        self.low_stock_page.refresh()
        self._update_status()

    def disable_inventory_features(self, status: str) -> None:
        self.sales_page.set_enabled_state(False)
        self.purchase_page.set_enabled_state(False)
        self.inventory_page.set_enabled_state(False)
        self.low_stock_page.set_enabled_state(False)
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
            "Analytics": self.analytics_page,
            "Low Stock": self.low_stock_page,
            "Basalam": self.basalam_page,
            "Actions": self.actions_page,
            "Reports/Logs": self.reports_page,
            "Settings": self.settings_page,
        }
        page = pages.get(name)
        if page:
            self.pages.setCurrentWidget(page)
            self.sidebar.set_active(name)

    def refresh_history_views(self) -> None:
        self.invoices_page.refresh()
        self.analytics_page.load_analytics()

    def apply_theme(self, theme: str) -> None:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app:
            app.setStyleSheet(get_stylesheet(theme))
        self.header.set_theme_label(theme)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._logger.warning(
            "Main window closeEvent: accepted=%s spontaneous=%s",
            event.isAccepted(),
            event.spontaneous(),
        )
        super().closeEvent(event)
