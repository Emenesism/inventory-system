from __future__ import annotations

from PySide6.QtCore import QObject, QPoint, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.action_log_service import ActionLogService
from app.services.inventory_service import InventoryService
from app.services.invoice_service import InvoiceService, InvoiceSummary
from app.ui.widgets.invoice_batch_export_dialog import InvoiceBatchExportDialog
from app.ui.widgets.invoice_edit_dialog import InvoiceEditDialog
from app.ui.widgets.toast import ToastManager
from app.utils import dialogs
from app.utils.dates import to_jalali_datetime
from app.utils.excel import export_invoice_excel
from app.utils.numeric import format_amount, format_number
from app.utils.pdf import export_invoice_pdf
from app.utils.text import normalize_text


class _InvoicesListWorker(QObject):
    loaded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        invoice_service: InvoiceService,
        *,
        limit: int,
        offset: int,
        invoice_type: str,
        refresh: bool,
        request_id: int,
    ) -> None:
        super().__init__()
        self._invoice_service = invoice_service
        self._limit = limit
        self._offset = offset
        self._invoice_type = invoice_type
        self._refresh = refresh
        self._request_id = request_id

    @Slot()
    def run(self) -> None:
        try:
            page = self._invoice_service.list_invoices_page(
                limit=self._limit,
                offset=self._offset,
                invoice_type=self._invoice_type,
            )
            self.loaded.emit(
                {
                    "request_id": self._request_id,
                    "refresh": self._refresh,
                    "items": page.items,
                    "total_count": page.total_count,
                    "total_amount": page.total_amount,
                }
            )
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()


class _InvoiceLinesWorker(QObject):
    loaded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        invoice_service: InvoiceService,
        *,
        invoice_id: int,
        request_id: int,
    ) -> None:
        super().__init__()
        self._invoice_service = invoice_service
        self._invoice_id = invoice_id
        self._request_id = request_id

    @Slot()
    def run(self) -> None:
        try:
            lines = self._invoice_service.get_invoice_lines(self._invoice_id)
            self.loaded.emit(
                {
                    "request_id": self._request_id,
                    "invoice_id": self._invoice_id,
                    "lines": lines,
                }
            )
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()


class InvoicesPage(QWidget):
    def __init__(
        self,
        invoice_service: InvoiceService,
        inventory_service: InventoryService,
        toast: ToastManager | None = None,
        on_inventory_updated=None,
        on_invoices_updated=None,
        action_log_service: ActionLogService | None = None,
        current_admin_provider=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.invoice_service = invoice_service
        self.inventory_service = inventory_service
        self.toast = toast
        self._on_inventory_updated = on_inventory_updated
        self._on_invoices_updated = on_invoices_updated
        self._action_log_service = action_log_service
        self._current_admin_provider = current_admin_provider
        self.invoices: list[InvoiceSummary] = []
        self._page_size = 100
        self._loaded_count = 0
        self._total_count = 0
        self._total_amount = 0.0
        self._loading_more = False
        self._show_prices = True
        self._can_edit = False
        self._list_thread: QThread | None = None
        self._list_worker: _InvoicesListWorker | None = None
        self._list_request_id = 0
        self._pending_refresh = False
        self._pending_load_more = False
        self._lines_thread: QThread | None = None
        self._lines_worker: _InvoiceLinesWorker | None = None
        self._lines_request_id = 0
        self._pending_lines_invoice_id: int | None = None
        self._active_lines_invoice_id: int | None = None
        self._invoice_filters: list[tuple[str, str, str]] = [
            ("all", self.tr("همه"), ""),
            ("sales_all", self.tr("همه فروش‌ها"), "sales"),
            ("purchase", self.tr("همه خریدها"), "purchase"),
            ("sales_manual", self.tr("فروش دستی"), "sales_manual"),
            ("sales_site", self.tr("فروش سایت"), "sales_site"),
            ("sales_basalam", self.tr("فروش باسلام"), "sales_basalam"),
        ]
        self._active_filter_key = "all"
        self._active_filter_type = ""
        self._filter_buttons: dict[str, QPushButton] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel(self.tr("فاکتورها"))
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        header.addWidget(title)
        header.addStretch(1)

        self.factor_button = QPushButton(self.tr("خروجی فاکتور"))
        self.factor_button.clicked.connect(self._open_factor_export)
        header.addWidget(self.factor_button)

        self.refresh_button = QPushButton(self.tr("بروزرسانی"))
        self.refresh_button.clicked.connect(self.refresh)
        header.addWidget(self.refresh_button)

        self.edit_button = QPushButton(self.tr("ویرایش فاکتور"))
        self.edit_button.clicked.connect(self._edit_selected_invoice)
        self.edit_button.setEnabled(False)
        self.edit_button.setVisible(False)
        self.edit_button.setToolTip(
            self.tr("فقط فاکتورهای خرید قابل ویرایش هستند.")
        )
        header.addWidget(self.edit_button)

        self.delete_button = QPushButton(self.tr("حذف فاکتور"))
        self.delete_button.setStyleSheet(
            "QPushButton { background: #DC2626; }"
            "QPushButton:hover { background: #B91C1C; }"
            "QPushButton:disabled { background: #9CA3AF; }"
        )
        self.delete_button.clicked.connect(self._delete_selected_invoice)
        self.delete_button.setEnabled(False)
        self.delete_button.setVisible(False)
        header.addWidget(self.delete_button)

        self.load_more_button = QPushButton(self.tr("موارد بیشتر"))
        self.load_more_button.clicked.connect(self._load_more)
        self.load_more_button.setEnabled(False)
        header.addWidget(self.load_more_button)
        layout.addLayout(header)

        summary_card = QFrame()
        summary_card.setObjectName("Card")
        summary_layout = QHBoxLayout(summary_card)
        summary_layout.setContentsMargins(16, 16, 16, 16)
        summary_layout.setSpacing(24)

        self.total_invoices_label = QLabel(self.tr("تعداد فاکتورها: 0"))
        self.total_amount_label = QLabel(self.tr("مبلغ کل: 0"))
        summary_layout.addWidget(self.total_invoices_label)
        summary_layout.addWidget(self.total_amount_label)
        summary_layout.addStretch(1)
        layout.addWidget(summary_card)

        filter_card = QFrame()
        filter_card.setObjectName("Card")
        filter_layout = QVBoxLayout(filter_card)
        filter_layout.setContentsMargins(16, 12, 16, 12)
        filter_layout.setSpacing(8)

        filter_title = QLabel(self.tr("فیلتر نمایش"))
        filter_title.setStyleSheet("font-weight: 600;")
        filter_layout.addWidget(filter_title)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        for key, label, _ in self._invoice_filters:
            button = QPushButton(label)
            button.setProperty("chip", True)
            button.clicked.connect(
                lambda _=False, selected=key: self._set_filter(selected)
            )
            filter_row.addWidget(button)
            self._filter_buttons[key] = button
        filter_row.addStretch(1)
        filter_layout.addLayout(filter_row)

        self.filter_hint_label = QLabel("")
        self.filter_hint_label.setProperty("textRole", "muted")
        filter_layout.addWidget(self.filter_hint_label)
        layout.addWidget(filter_card)
        self._update_filter_buttons()

        list_card = QFrame()
        list_card.setObjectName("Card")
        list_layout = QVBoxLayout(list_card)
        list_layout.setContentsMargins(16, 16, 16, 16)

        self.invoices_table = QTableWidget(0, 9)
        self.invoices_table.setHorizontalHeaderLabels(
            [
                self.tr("تاریخ"),
                self.tr("شماره فاکتور"),
                self.tr("نام"),
                self.tr("نوع"),
                self.tr("ردیف"),
                self.tr("تعداد"),
                self.tr("مدیر"),
                self.tr("مبلغ کل"),
                self.tr("خروجی"),
            ]
        )
        header_view = self.invoices_table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.Interactive)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.Stretch)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(7, QHeaderView.Interactive)
        header_view.setSectionResizeMode(8, QHeaderView.Fixed)
        self.invoices_table.setColumnWidth(0, 190)
        self.invoices_table.setColumnWidth(7, 140)
        self.invoices_table.setColumnWidth(8, 90)
        self.invoices_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.invoices_table.setAlternatingRowColors(True)
        if hasattr(self.invoices_table, "setUniformRowHeights"):
            self.invoices_table.setUniformRowHeights(True)
        self.invoices_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.invoices_table.horizontalHeader().setStretchLastSection(False)
        self.invoices_table.verticalHeader().setDefaultSectionSize(34)
        self.invoices_table.setMinimumHeight(240)
        self.invoices_table.itemSelectionChanged.connect(
            self._show_selected_details
        )
        self.invoices_table.itemSelectionChanged.connect(
            self._update_action_buttons
        )
        self.invoices_table.verticalScrollBar().valueChanged.connect(
            self._maybe_load_more
        )
        list_layout.addWidget(self.invoices_table)
        layout.addWidget(list_card)

        details_card = QFrame()
        details_card.setObjectName("Card")
        details_layout = QVBoxLayout(details_card)
        details_layout.setContentsMargins(16, 16, 16, 16)
        details_layout.setSpacing(12)

        self.details_label = QLabel(
            self.tr("برای مشاهده جزئیات یک فاکتور را انتخاب کنید.")
        )
        details_layout.addWidget(self.details_label)

        self.lines_table = QTableWidget(0, 4)
        self.lines_table.setHorizontalHeaderLabels(
            [
                self.tr("کالا"),
                self.tr("قیمت"),
                self.tr("تعداد"),
                self.tr("جمع خط"),
            ]
        )
        lines_header = self.lines_table.horizontalHeader()
        lines_header.setDefaultAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        lines_header.setSectionResizeMode(0, QHeaderView.Stretch)
        lines_header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        lines_header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        lines_header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        for col in range(self.lines_table.columnCount()):
            header_item = self.lines_table.horizontalHeaderItem(col)
            if header_item is None:
                continue
            if col == 0:
                header_item.setTextAlignment(
                    Qt.AlignVCenter | Qt.AlignRight | Qt.AlignAbsolute
                )
            else:
                header_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignCenter)
        self.lines_table.setAlternatingRowColors(True)
        if hasattr(self.lines_table, "setUniformRowHeights"):
            self.lines_table.setUniformRowHeights(True)
        self.lines_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.lines_table.horizontalHeader().setStretchLastSection(True)
        self.lines_table.verticalHeader().setDefaultSectionSize(32)
        self.lines_table.setMinimumHeight(200)
        details_layout.addWidget(self.lines_table)

        layout.addWidget(details_card)
        self._apply_price_visibility()
        self.refresh()

    def refresh(self) -> None:
        if self._list_thread is not None and self._list_thread.isRunning():
            self._pending_refresh = True
            self._pending_load_more = False
            return
        self._pending_refresh = False
        self._pending_load_more = False
        self._lines_request_id += 1
        self._active_lines_invoice_id = None
        self._pending_lines_invoice_id = None
        self.invoices = []
        self._loaded_count = 0
        self._total_count = 0
        self._total_amount = 0.0
        self._loading_more = False
        self.total_invoices_label.setText(
            self.tr("تعداد فاکتورها: {count}").format(count=self._total_count)
        )
        self._set_total_amount_label()
        self._set_filter_hint()
        self.invoices_table.blockSignals(True)
        self.invoices_table.setRowCount(0)
        self.invoices_table.blockSignals(False)
        self.details_label.setText(
            self.tr("برای مشاهده جزئیات یک فاکتور را انتخاب کنید.")
        )
        self.lines_table.setRowCount(0)
        self._set_list_controls_enabled(False)
        self.load_more_button.setEnabled(False)
        self._update_action_buttons()
        self._start_list_worker(refresh=True, offset=0)

    def _set_filter(self, filter_key: str) -> None:
        if filter_key == self._active_filter_key:
            return
        if self._filter_meta(filter_key) is None:
            return
        self._active_filter_key = filter_key
        self._active_filter_type = self._filter_type(filter_key)
        self._update_filter_buttons()
        self.refresh()

    def _filter_meta(self, filter_key: str) -> tuple[str, str, str] | None:
        for key, label, invoice_type in self._invoice_filters:
            if key == filter_key:
                return key, label, invoice_type
        return None

    def _filter_label(self, filter_key: str) -> str:
        meta = self._filter_meta(filter_key)
        if meta is None:
            return self.tr("همه")
        return meta[1]

    def _filter_type(self, filter_key: str) -> str:
        meta = self._filter_meta(filter_key)
        if meta is None:
            return ""
        return meta[2]

    def _set_filter_hint(self) -> None:
        self.filter_hint_label.setText(
            self.tr("فیلتر فعال: {label} | نتیجه: {count}").format(
                label=self._filter_label(self._active_filter_key),
                count=self._total_count,
            )
        )

    def _update_filter_buttons(self) -> None:
        for key, button in self._filter_buttons.items():
            button.setProperty("active", key == self._active_filter_key)
            self._refresh_widget_style(button)

    @staticmethod
    def _refresh_widget_style(widget: QWidget) -> None:
        style = widget.style()
        if style is None:
            return
        style.unpolish(widget)
        style.polish(widget)
        widget.update()

    def _show_selected_details(self) -> None:
        row = self.invoices_table.currentRow()
        if row < 0:
            self._active_lines_invoice_id = None
            self._pending_lines_invoice_id = None
            self.lines_table.setRowCount(0)
            return
        item = self.invoices_table.item(row, 0)
        if not item:
            return
        invoice_id = item.data(Qt.UserRole)
        if invoice_id is None:
            return
        invoice_id_int = int(invoice_id)
        self._pending_lines_invoice_id = None
        self._active_lines_invoice_id = invoice_id_int
        self.lines_table.setRowCount(0)
        self.lines_table.setEnabled(False)

        inv = next(
            (inv for inv in self.invoices if inv.invoice_id == invoice_id_int),
            None,
        )
        invoice_type = inv.invoice_type if inv else ""
        show_price = self._should_show_prices(invoice_type)
        self.lines_table.setColumnHidden(1, not show_price)
        self.lines_table.setColumnHidden(3, not show_price)
        if inv:
            header_parts = [
                self.tr("شماره فاکتور {id}").format(id=inv.invoice_id),
                self._format_type(invoice_type),
                self._format_invoice_datetime(inv.created_at),
            ]
            if inv.invoice_name:
                header_parts.insert(
                    1,
                    self.tr("نام: {name}").format(name=inv.invoice_name),
                )
            header_parts.append(
                self.tr("مدیر: {admin}").format(
                    admin=self._format_admin(inv.admin_id, inv.admin_username)
                )
            )
            if show_price:
                header_parts.append(
                    self.tr("مبلغ کل: {amount}").format(
                        amount=self._format_amount(inv.total_amount)
                    )
                )
            header = " | ".join(header_parts)
        else:
            header = self.tr("جزئیات فاکتور")
        self.details_label.setText(header)
        self._start_lines_worker(invoice_id_int)

    def _maybe_load_more(self) -> None:
        if self._loading_more or self._loaded_count >= self._total_count:
            return
        bar = self.invoices_table.verticalScrollBar()
        if bar.maximum() == 0:
            return
        if bar.value() >= bar.maximum() - 20:
            self._load_more()

    def _load_more(self) -> None:
        if self._list_thread is not None and self._list_thread.isRunning():
            self._pending_load_more = True
            return
        if self._loading_more or self._loaded_count >= self._total_count:
            self.load_more_button.setEnabled(False)
            return
        self._pending_load_more = False
        self._set_list_controls_enabled(False)
        self.load_more_button.setEnabled(False)
        self._start_list_worker(refresh=False, offset=self._loaded_count)

    def _set_list_controls_enabled(self, enabled: bool) -> None:
        self.refresh_button.setEnabled(enabled)
        for button in self._filter_buttons.values():
            button.setEnabled(enabled)

    def _start_list_worker(self, *, refresh: bool, offset: int) -> None:
        if self._list_thread is not None and self._list_thread.isRunning():
            if refresh:
                self._pending_refresh = True
            else:
                self._pending_load_more = True
            return
        self._loading_more = True
        self._list_request_id += 1
        worker = _InvoicesListWorker(
            self.invoice_service,
            limit=self._page_size,
            offset=offset,
            invoice_type=self._active_filter_type,
            refresh=refresh,
            request_id=self._list_request_id,
        )
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.loaded.connect(self._on_list_loaded)
        worker.failed.connect(self._on_list_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_list_finished)
        thread.finished.connect(thread.deleteLater)
        self._list_worker = worker
        self._list_thread = thread
        thread.start()

    @Slot(object)
    def _on_list_loaded(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        request_id = int(payload.get("request_id", 0) or 0)
        if request_id != self._list_request_id:
            return
        refresh = bool(payload.get("refresh"))
        items = payload.get("items", [])
        batch = [item for item in items if isinstance(item, InvoiceSummary)]
        self._total_count = int(payload.get("total_count", 0) or 0)
        self._total_amount = float(payload.get("total_amount", 0.0) or 0.0)
        self.total_invoices_label.setText(
            self.tr("تعداد فاکتورها: {count}").format(count=self._total_count)
        )
        self._set_total_amount_label()
        self._set_filter_hint()
        if refresh:
            self.invoices = []
            self._loaded_count = 0
            self.invoices_table.blockSignals(True)
            self.invoices_table.setRowCount(0)
            self.invoices_table.blockSignals(False)
            self.details_label.setText(
                self.tr("برای مشاهده جزئیات یک فاکتور را انتخاب کنید.")
            )
            self.lines_table.setRowCount(0)
        if batch:
            self._append_invoice_batch(batch)
        elif refresh:
            self.details_label.setText(self.tr("فاکتوری ثبت نشده است."))
        self.load_more_button.setEnabled(self._loaded_count < self._total_count)

    @Slot(str)
    def _on_list_failed(self, _error: str) -> None:
        self.load_more_button.setEnabled(False)
        if not self.invoices:
            self.details_label.setText(self.tr("خطا در دریافت فاکتورها."))

    def _on_list_finished(self) -> None:
        self._list_worker = None
        self._list_thread = None
        self._loading_more = False
        self._set_list_controls_enabled(True)
        self.load_more_button.setEnabled(self._loaded_count < self._total_count)
        if self._pending_refresh:
            self._pending_refresh = False
            self._pending_load_more = False
            self.refresh()
            return
        if self._pending_load_more:
            self._pending_load_more = False
            self._load_more()

    def _start_lines_worker(self, invoice_id: int) -> None:
        if self._lines_thread is not None and self._lines_thread.isRunning():
            self._pending_lines_invoice_id = invoice_id
            return
        self._lines_request_id += 1
        worker = _InvoiceLinesWorker(
            self.invoice_service,
            invoice_id=invoice_id,
            request_id=self._lines_request_id,
        )
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.loaded.connect(self._on_lines_loaded)
        worker.failed.connect(self._on_lines_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_lines_finished)
        thread.finished.connect(thread.deleteLater)
        self._lines_worker = worker
        self._lines_thread = thread
        thread.start()

    @Slot(object)
    def _on_lines_loaded(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        request_id = int(payload.get("request_id", 0) or 0)
        if request_id != self._lines_request_id:
            return
        invoice_id = int(payload.get("invoice_id", 0) or 0)
        selected_invoice_id = self._selected_invoice_id()
        if selected_invoice_id is None or selected_invoice_id != invoice_id:
            return
        lines = payload.get("lines", [])
        if not isinstance(lines, list):
            lines = []
        inv = next(
            (
                invoice
                for invoice in self.invoices
                if invoice.invoice_id == invoice_id
            ),
            None,
        )
        invoice_type = inv.invoice_type if inv else ""
        show_price = self._should_show_prices(invoice_type)
        self.lines_table.setColumnHidden(1, not show_price)
        self.lines_table.setColumnHidden(3, not show_price)

        self.lines_table.setRowCount(len(lines))
        for row_idx, line in enumerate(lines):
            product_item = QTableWidgetItem(line.product_name)
            product_item.setTextAlignment(
                Qt.AlignVCenter | Qt.AlignRight | Qt.AlignAbsolute
            )
            self.lines_table.setItem(row_idx, 0, product_item)
            price_text = self._format_amount(line.price) if show_price else ""
            price_item = QTableWidgetItem(price_text)
            price_item.setTextAlignment(Qt.AlignCenter)
            self.lines_table.setItem(row_idx, 1, price_item)

            qty_item = QTableWidgetItem(format_number(line.quantity))
            qty_item.setTextAlignment(Qt.AlignCenter)
            self.lines_table.setItem(row_idx, 2, qty_item)

            total_text = (
                self._format_amount(line.line_total) if show_price else ""
            )
            total_item = QTableWidgetItem(total_text)
            total_item.setTextAlignment(Qt.AlignCenter)
            self.lines_table.setItem(row_idx, 3, total_item)

    @Slot(str)
    def _on_lines_failed(self, _error: str) -> None:
        selected_invoice_id = self._selected_invoice_id()
        if selected_invoice_id is None:
            return
        self.lines_table.setRowCount(0)
        self.details_label.setText(self.tr("خطا در دریافت جزئیات فاکتور."))

    def _on_lines_finished(self) -> None:
        self._lines_worker = None
        self._lines_thread = None
        self.lines_table.setEnabled(True)
        next_invoice_id = self._pending_lines_invoice_id
        self._pending_lines_invoice_id = None
        if next_invoice_id is not None:
            self._start_lines_worker(next_invoice_id)

    def _append_invoice_batch(self, batch: list[InvoiceSummary]) -> None:
        if not batch:
            return
        start_row = self.invoices_table.rowCount()
        self.invoices_table.setUpdatesEnabled(False)
        self.invoices_table.blockSignals(True)
        self.invoices_table.setRowCount(start_row + len(batch))
        try:
            for row_offset, invoice in enumerate(batch):
                row_idx = start_row + row_offset
                date_item = QTableWidgetItem(
                    self._format_invoice_datetime(invoice.created_at)
                )
                date_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                date_item.setData(Qt.UserRole, invoice.invoice_id)
                self.invoices_table.setItem(row_idx, 0, date_item)
                invoice_item = QTableWidgetItem(
                    format_number(invoice.invoice_id)
                )
                invoice_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.invoices_table.setItem(row_idx, 1, invoice_item)
                self.invoices_table.setItem(
                    row_idx,
                    2,
                    QTableWidgetItem(invoice.invoice_name or ""),
                )
                self.invoices_table.setItem(
                    row_idx,
                    3,
                    QTableWidgetItem(self._format_type(invoice.invoice_type)),
                )
                lines_item = QTableWidgetItem(
                    format_number(invoice.total_lines)
                )
                lines_item.setTextAlignment(Qt.AlignCenter)
                self.invoices_table.setItem(row_idx, 4, lines_item)

                qty_item = QTableWidgetItem(format_number(invoice.total_qty))
                qty_item.setTextAlignment(Qt.AlignCenter)
                self.invoices_table.setItem(row_idx, 5, qty_item)

                admin_item = QTableWidgetItem(
                    self._format_admin(invoice.admin_id, invoice.admin_username)
                )
                self.invoices_table.setItem(row_idx, 6, admin_item)

                show_price = self._should_show_prices(invoice.invoice_type)
                total_value = (
                    self._format_amount(invoice.total_amount)
                    if show_price
                    else ""
                )
                total_item = QTableWidgetItem(total_value)
                total_item.setTextAlignment(Qt.AlignCenter)
                self.invoices_table.setItem(row_idx, 7, total_item)

                export_button = QPushButton(self.tr("خروجی"))
                export_button.setProperty("compact", True)
                export_button.clicked.connect(
                    lambda _=False, inv_id=invoice.invoice_id, btn=export_button: (
                        self._open_invoice_export_menu(btn, inv_id)
                    )
                )
                self.invoices_table.setCellWidget(row_idx, 8, export_button)
        finally:
            self.invoices_table.blockSignals(False)
            self.invoices_table.setUpdatesEnabled(True)

        self.invoices.extend(batch)
        self._loaded_count += len(batch)
        if start_row == 0 and self.invoices:
            self.invoices_table.selectRow(0)

    def _format_type(self, value: str) -> str:
        if value == "purchase":
            return self.tr("خرید")
        if value == "sales_manual":
            return self.tr("فروش دستی")
        if value == "sales_basalam":
            return self.tr("فروش باسلام")
        if value == "sales_site":
            return self.tr("فروش سایت")
        if value.startswith("sales"):
            return self.tr("فروش")
        return value.title()

    @staticmethod
    def _format_amount(value: float) -> str:
        return format_amount(value)

    @staticmethod
    def _format_invoice_datetime(value: str) -> str:
        text = to_jalali_datetime(value)
        if not text:
            return ""
        return f"\u200e{text}\u200e"

    def _format_admin(
        self, admin_id: int | None, admin_username: str | None
    ) -> str:
        if admin_username:
            return admin_username
        if admin_id is not None:
            return self.tr("شناسه {id}").format(id=admin_id)
        return self.tr("نامشخص")

    def set_price_visibility(self, show: bool) -> None:
        self._show_prices = bool(show)
        self._apply_price_visibility()
        self._set_total_amount_label()
        if self.invoices_table.currentRow() >= 0:
            self._show_selected_details()

    def _apply_price_visibility(self) -> None:
        self.invoices_table.setColumnHidden(7, False)
        self.lines_table.setColumnHidden(1, False)
        self.lines_table.setColumnHidden(3, False)

    def _set_total_amount_label(self) -> None:
        if self._show_prices:
            self.total_amount_label.setText(
                self.tr("مبلغ کل: {amount}").format(
                    amount=self._format_amount(self._total_amount)
                )
            )
        else:
            self.total_amount_label.setText(self.tr("مبلغ کل: "))

    def _should_show_prices(self, invoice_type: str) -> bool:
        if invoice_type.startswith("sales"):
            return False
        return self._show_prices

    def set_edit_enabled(self, enabled: bool) -> None:
        self._can_edit = bool(enabled)
        self.edit_button.setVisible(self._can_edit)
        self.delete_button.setVisible(self._can_edit)
        self._update_action_buttons()

    def _update_action_buttons(self) -> None:
        has_selection = self._selected_invoice_id() is not None
        edit_allowed = False
        if has_selection:
            summary = self._selected_invoice_summary()
            edit_allowed = summary is not None and (
                summary.invoice_type == "purchase"
                or summary.invoice_type.startswith("sales")
            )
        self.edit_button.setEnabled(self._can_edit and edit_allowed)
        self.delete_button.setEnabled(self._can_edit and has_selection)

    def _selected_invoice_id(self) -> int | None:
        row = self.invoices_table.currentRow()
        if row < 0:
            return None
        item = self.invoices_table.item(row, 0)
        if not item:
            return None
        invoice_id = item.data(Qt.UserRole)
        if invoice_id is None:
            return None
        return int(invoice_id)

    def _selected_invoice_summary(self) -> InvoiceSummary | None:
        invoice_id = self._selected_invoice_id()
        if invoice_id is None:
            return None
        summary = next(
            (inv for inv in self.invoices if inv.invoice_id == invoice_id),
            None,
        )
        if summary is not None:
            return summary
        return self.invoice_service.get_invoice(invoice_id)

    def _edit_selected_invoice(self) -> None:
        if not self._can_edit:
            return
        invoice_id = self._selected_invoice_id()
        if invoice_id is None:
            return
        invoice = self.invoice_service.get_invoice(invoice_id)
        if invoice is None:
            dialogs.show_error(
                self, self.tr("فاکتورها"), self.tr("فاکتور پیدا نشد.")
            )
            return
        lines = self.invoice_service.get_invoice_lines(invoice_id)
        if not lines:
            dialogs.show_error(
                self, self.tr("فاکتورها"), self.tr("فاکتور هیچ ردیفی ندارد.")
            )
            return
        if not self.inventory_service.is_loaded():
            dialogs.show_error(
                self, self.tr("موجودی"), self.tr("موجودی بارگذاری نشده است.")
            )
            return
        inventory_df = self.inventory_service.get_dataframe()
        product_names = self.inventory_service.get_product_names()
        cost_map = {
            normalize_text(name): float(inventory_df.at[idx, "avg_buy_price"])
            for idx, name in inventory_df["product_name"].items()
        }
        dialog = InvoiceEditDialog(
            invoice, lines, product_names, cost_map, self
        )
        if dialog.exec() != QDialog.Accepted or dialog.updated_lines is None:
            return
        new_lines = dialog.updated_lines
        new_name = dialog.updated_name
        name_changed = (new_name or None) != (invoice.invoice_name or None)
        lines_changed = not self._lines_equal(lines, new_lines)
        if not lines_changed and not name_changed:
            return
        if not lines_changed and name_changed:
            admin = (
                self._current_admin_provider()
                if self._current_admin_provider
                else None
            )
            admin_username = admin.username if admin else None
            try:
                self.invoice_service.update_invoice_name(
                    invoice.invoice_id,
                    new_name,
                    admin_username=admin_username,
                )
            except Exception as exc:  # noqa: BLE001
                dialogs.show_error(self, self.tr("ویرایش فاکتور"), str(exc))
                return
            if self._action_log_service:
                title = (
                    self.tr("ویرایش نام فاکتور فروش")
                    if invoice.invoice_type.startswith("sales")
                    else self.tr("ویرایش نام فاکتور خرید")
                )
                details = self._build_invoice_before_after_log(
                    invoice=invoice,
                    before_lines=lines,
                    after_lines=lines,
                    before_name=invoice.invoice_name,
                    after_name=new_name,
                    inventory_note=self.tr("تغییر موجودی: ندارد"),
                )
                self._action_log_service.log_action(
                    "invoice_edit",
                    title,
                    details,
                    admin=admin,
                )
            if self.toast:
                self.toast.show(self.tr("فاکتور به‌روزرسانی شد"), "success")
            else:
                dialogs.show_info(
                    self,
                    self.tr("فاکتورها"),
                    self.tr("فاکتور به‌روزرسانی شد."),
                )
            self._after_invoice_change()
            return
        confirm_message = (
            self.tr("تغییرات فاکتور #{id} ذخیره شود؟\n").format(
                id=invoice.invoice_id
            )
            + self.tr("نوع: {type}\n").format(
                type=self._format_type(invoice.invoice_type)
            )
            + self.tr("تاریخ: {date}\n").format(
                date=self._format_invoice_datetime(invoice.created_at)
            )
        )
        if name_changed:
            confirm_message += self.tr("نام: {old} → {new}\n").format(
                old=invoice.invoice_name or "",
                new=new_name or "",
            )
        confirm_message += self.tr("ردیف‌ها: {old} → {new}\n").format(
            old=len(lines), new=len(new_lines)
        ) + self.tr("تطبیق موجودی توسط بک‌اند انجام می‌شود.")
        confirm = dialogs.ask_yes_no(
            self,
            self.tr("ویرایش فاکتور"),
            confirm_message,
        )
        if not confirm:
            return
        admin = (
            self._current_admin_provider()
            if self._current_admin_provider
            else None
        )
        admin_username = admin.username if admin else None
        try:
            self.invoice_service.update_invoice_lines(
                invoice.invoice_id,
                invoice.invoice_type,
                new_lines,
                new_name,
                admin_username=admin_username,
            )
        except Exception as exc:  # noqa: BLE001
            dialogs.show_error(self, self.tr("ویرایش فاکتور"), str(exc))
            return
        if self._action_log_service:
            title = (
                self.tr("ویرایش فاکتور فروش")
                if invoice.invoice_type.startswith("sales")
                else self.tr("ویرایش فاکتور خرید")
            )
            details = self._build_invoice_before_after_log(
                invoice=invoice,
                before_lines=lines,
                after_lines=new_lines,
                before_name=invoice.invoice_name,
                after_name=new_name,
                inventory_note=self.tr("تغییر موجودی: اعمال در بک‌اند"),
            )
            self._action_log_service.log_action(
                "invoice_edit",
                title,
                details,
                admin=admin,
            )
        if self.toast:
            self.toast.show(self.tr("فاکتور به‌روزرسانی شد"), "success")
        else:
            dialogs.show_info(
                self,
                self.tr("فاکتورها"),
                self.tr("فاکتور به‌روزرسانی شد."),
            )
        self._after_invoice_change()

    def _delete_selected_invoice(self) -> None:
        if not self._can_edit:
            return
        invoice_id = self._selected_invoice_id()
        if invoice_id is None:
            return
        invoice = self.invoice_service.get_invoice(invoice_id)
        if invoice is None:
            dialogs.show_error(
                self, self.tr("فاکتورها"), self.tr("فاکتور پیدا نشد.")
            )
            return
        try:
            lines = self.invoice_service.get_invoice_lines(invoice_id)
        except Exception as exc:  # noqa: BLE001
            dialogs.show_error(self, self.tr("حذف فاکتور"), str(exc))
            return
        line_count = len(lines) if lines else invoice.total_lines
        confirm = dialogs.ask_yes_no(
            self,
            self.tr("حذف فاکتور"),
            (
                self.tr("فاکتور #{id} حذف شود؟\n").format(id=invoice.invoice_id)
                + self.tr("نوع: {type}\n").format(
                    type=self._format_type(invoice.invoice_type)
                )
                + self.tr("تاریخ: {date}\n").format(
                    date=self._format_invoice_datetime(invoice.created_at)
                )
                + self.tr("تعداد ردیف: {count}\n").format(count=line_count)
                + self.tr("تطبیق موجودی توسط بک‌اند انجام می‌شود.")
            ),
        )
        if not confirm:
            return
        admin = (
            self._current_admin_provider()
            if self._current_admin_provider
            else None
        )
        admin_username = admin.username if admin else None
        try:
            self.invoice_service.delete_invoice(
                invoice.invoice_id, admin_username=admin_username
            )
        except Exception as exc:  # noqa: BLE001
            dialogs.show_error(self, self.tr("حذف فاکتور"), str(exc))
            return
        if self._action_log_service:
            title = (
                self.tr("حذف فاکتور فروش")
                if invoice.invoice_type.startswith("sales")
                else self.tr("حذف فاکتور خرید")
            )
            details = self._build_invoice_delete_log(
                invoice=invoice,
                before_lines=lines,
                before_name=invoice.invoice_name,
            )
            self._action_log_service.log_action(
                "invoice_delete",
                title,
                details,
                admin=admin,
            )
        if self.toast:
            self.toast.show(self.tr("فاکتور حذف شد"), "success")
        else:
            dialogs.show_info(
                self,
                self.tr("فاکتورها"),
                self.tr("فاکتور حذف شد."),
            )
        self._after_invoice_change()

    def _open_invoice_export_menu(
        self, button: QPushButton, invoice_id: int
    ) -> None:
        menu = QMenu(button)
        excel_action = menu.addAction(self.tr("اکسل (.xlsx)"))
        pdf_action = menu.addAction(self.tr("پی‌دی‌اف (.pdf)"))
        action = menu.exec(button.mapToGlobal(QPoint(0, button.height())))
        if action == excel_action:
            self._export_invoice(invoice_id, "excel")
        elif action == pdf_action:
            self._export_invoice(invoice_id, "pdf")

    def _export_invoice(self, invoice_id: int, file_format: str) -> None:
        invoice = self.invoice_service.get_invoice(invoice_id)
        if invoice is None:
            dialogs.show_error(
                self, self.tr("خروجی فاکتور"), self.tr("فاکتور پیدا نشد.")
            )
            return
        lines = self.invoice_service.get_invoice_lines(invoice_id)
        if not lines:
            dialogs.show_error(
                self,
                self.tr("خروجی فاکتور"),
                self.tr("فاکتور هیچ ردیفی ندارد."),
            )
            return

        if file_format == "pdf":
            default_name = f"invoice_{invoice.invoice_id}.pdf"
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                self.tr("خروجی فاکتور"),
                default_name,
                self.tr("فایل‌های PDF (*.pdf)"),
            )
            if not file_path:
                return
            if not file_path.lower().endswith(".pdf"):
                file_path = f"{file_path}.pdf"
            export_invoice_pdf(file_path, invoice, lines)
            log_title = self.tr("خروجی PDF فاکتور")
        else:
            default_name = f"invoice_{invoice.invoice_id}.xlsx"
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                self.tr("خروجی فاکتور"),
                default_name,
                self.tr("فایل‌های اکسل (*.xlsx)"),
            )
            if not file_path:
                return
            if not file_path.lower().endswith(".xlsx"):
                file_path = f"{file_path}.xlsx"
            export_invoice_excel(file_path, invoice, lines)
            log_title = self.tr("خروجی اکسل فاکتور")

        if self._action_log_service:
            admin = (
                self._current_admin_provider()
                if self._current_admin_provider
                else None
            )
            self._action_log_service.log_action(
                "invoice_export",
                log_title,
                self.tr("شماره فاکتور: {invoice_id}\nمسیر: {path}").format(
                    invoice_id=invoice.invoice_id,
                    path=file_path,
                ),
                admin=admin,
            )
        if self.toast:
            self.toast.show(self.tr("خروجی فاکتور انجام شد"), "success")
        else:
            dialogs.show_info(
                self,
                self.tr("خروجی فاکتور"),
                self.tr("خروجی فاکتور انجام شد."),
            )

    def _open_factor_export(self) -> None:
        dialog = InvoiceBatchExportDialog(
            self.invoice_service,
            self.inventory_service,
            self._action_log_service,
            self._current_admin_provider,
            self.toast,
            self,
        )
        dialog.exec()

    def _after_invoice_change(self) -> None:
        if self._on_inventory_updated:
            self._on_inventory_updated()
        if self._on_invoices_updated:
            self._on_invoices_updated()
        else:
            self.refresh()

    @staticmethod
    def _lines_equal(old_lines, new_lines) -> bool:
        if len(old_lines) != len(new_lines):
            return False
        for old, new in zip(old_lines, new_lines):
            if normalize_text(old.product_name) != normalize_text(
                new.product_name
            ):
                return False
            if int(old.quantity) != int(new.quantity):
                return False
            if abs(float(old.price) - float(new.price)) > 0.0001:
                return False
        return True

    def _format_lines_for_log(self, lines) -> str:  # noqa: ANN001
        if not lines:
            return self.tr("(هیچ)")
        rows = []
        for idx, line in enumerate(lines, start=1):
            total = float(line.price) * int(line.quantity)
            rows.append(
                self.tr(
                    "{idx}) {name} | قیمت: {price} | تعداد: {qty} | جمع: {total}"
                ).format(
                    idx=idx,
                    name=line.product_name,
                    price=line.price,
                    qty=line.quantity,
                    total=f"{total:,.0f}",
                )
            )
        return "\n".join(rows)

    @staticmethod
    def _invoice_totals(lines) -> tuple[int, float]:  # noqa: ANN001
        total_qty = sum(int(line.quantity) for line in lines)
        total_amount = sum(
            float(line.price) * int(line.quantity) for line in lines
        )
        return total_qty, total_amount

    def _format_invoice_snapshot_for_log(
        self,
        invoice: InvoiceSummary,
        lines,
        invoice_name: str | None,
        label: str,
    ) -> str:  # noqa: ANN001
        total_qty, total_amount = self._invoice_totals(lines)
        return self.tr(
            "{label}:\n"
            "شماره فاکتور: {invoice_id}\n"
            "نوع: {invoice_type}\n"
            "نام: {invoice_name}\n"
            "تعداد ردیف‌ها: {line_count}\n"
            "تعداد کل: {total_qty}\n"
            "مبلغ کل: {total_amount}\n"
            "ردیف‌ها:\n"
            "{lines_block}"
        ).format(
            label=label,
            invoice_id=invoice.invoice_id,
            invoice_type=self._format_type(invoice.invoice_type),
            invoice_name=invoice_name or "-",
            line_count=len(lines),
            total_qty=total_qty,
            total_amount=self._format_amount(total_amount),
            lines_block=self._format_lines_for_log(lines),
        )

    def _format_deleted_invoice_snapshot_for_log(
        self, invoice: InvoiceSummary, label: str
    ) -> str:
        return self.tr(
            "{label}:\n"
            "شماره فاکتور: {invoice_id}\n"
            "نوع: {invoice_type}\n"
            "نام: (حذف شد)\n"
            "وضعیت: حذف شده\n"
            "تعداد ردیف‌ها: 0\n"
            "تعداد کل: 0\n"
            "مبلغ کل: {total_amount}\n"
            "ردیف‌ها:\n"
            "(هیچ)"
        ).format(
            label=label,
            invoice_id=invoice.invoice_id,
            invoice_type=self._format_type(invoice.invoice_type),
            total_amount=self._format_amount(0),
        )

    def _build_invoice_before_after_log(
        self,
        invoice: InvoiceSummary,
        before_lines,
        after_lines,
        before_name: str | None,
        after_name: str | None,
        inventory_note: str,
    ) -> str:  # noqa: ANN001
        before_block = self._format_invoice_snapshot_for_log(
            invoice=invoice,
            lines=before_lines,
            invoice_name=before_name,
            label=self.tr("قبل"),
        )
        after_block = self._format_invoice_snapshot_for_log(
            invoice=invoice,
            lines=after_lines,
            invoice_name=after_name,
            label=self.tr("بعد"),
        )
        return before_block + "\n\n" + after_block + "\n\n" + inventory_note

    def _build_invoice_delete_log(
        self,
        invoice: InvoiceSummary,
        before_lines,
        before_name: str | None,
    ) -> str:  # noqa: ANN001
        before_block = self._format_invoice_snapshot_for_log(
            invoice=invoice,
            lines=before_lines,
            invoice_name=before_name,
            label=self.tr("قبل"),
        )
        after_block = self._format_deleted_invoice_snapshot_for_log(
            invoice=invoice,
            label=self.tr("بعد"),
        )
        return (
            before_block
            + "\n\n"
            + after_block
            + "\n\n"
            + self.tr("تغییر موجودی: اعمال در بک‌اند")
        )
