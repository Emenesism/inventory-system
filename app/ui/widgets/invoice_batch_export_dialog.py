from __future__ import annotations

from datetime import datetime, timedelta
from html import escape
from zoneinfo import ZoneInfo

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import (
    QIntValidator,
    QTextBlockFormat,
    QTextCursor,
    QTextOption,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.services.action_log_service import ActionLogService
from app.services.inventory_service import InventoryService
from app.services.invoice_service import (
    InvoiceProductMatch,
    InvoiceService,
    InvoiceSummary,
)
from app.ui.widgets.toast import ToastManager
from app.utils import dialogs
from app.utils.dates import (
    jalali_month_days,
    jalali_to_gregorian,
    jalali_today,
    to_jalali_datetime,
)
from app.utils.excel import export_invoices_excel
from app.utils.numeric import format_amount
from app.utils.pdf import export_invoices_pdf
from app.utils.text import normalize_text


class JalaliDatePicker(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.year_combo = QComboBox()
        self.month_combo = QComboBox()
        self.day_combo = QComboBox()
        self.year_combo.setMinimumWidth(84)
        self.month_combo.setMinimumWidth(58)
        self.day_combo.setMinimumWidth(58)
        self.year_combo.setMinimumHeight(32)
        self.month_combo.setMinimumHeight(32)
        self.day_combo.setMinimumHeight(32)

        for year in range(1390, 1451):
            self.year_combo.addItem(str(year), year)
        for month in range(1, 13):
            self.month_combo.addItem(f"{month:02d}", month)

        layout.addWidget(self.year_combo)
        layout.addWidget(self.month_combo)
        layout.addWidget(self.day_combo)

        self.year_combo.currentIndexChanged.connect(self._refresh_days)
        self.month_combo.currentIndexChanged.connect(self._refresh_days)

        jy, jm, jd = jalali_today()
        self.set_jalali_date(jy, jm, jd)

    def set_jalali_date(self, jy: int, jm: int, jd: int) -> None:
        self.year_combo.setCurrentText(str(jy))
        month_index = max(1, min(jm, 12)) - 1
        self.month_combo.setCurrentIndex(month_index)
        self._refresh_days()
        day_index = max(1, min(jd, self.day_combo.count())) - 1
        self.day_combo.setCurrentIndex(day_index)

    def _refresh_days(self) -> None:
        jy = int(self.year_combo.currentData())
        jm = int(self.month_combo.currentData())
        current_day = self.day_combo.currentData()
        max_day = jalali_month_days(jy, jm)

        self.day_combo.blockSignals(True)
        self.day_combo.clear()
        for day in range(1, max_day + 1):
            self.day_combo.addItem(f"{day:02d}", day)
        if isinstance(current_day, int) and 1 <= current_day <= max_day:
            self.day_combo.setCurrentIndex(current_day - 1)
        self.day_combo.blockSignals(False)

    def jalali_date(self) -> tuple[int, int, int]:
        jy = int(self.year_combo.currentData())
        jm = int(self.month_combo.currentData())
        jd = int(self.day_combo.currentData())
        return jy, jm, jd

    def to_gregorian_datetime(self, end_of_day: bool = False) -> datetime:
        jy, jm, jd = self.jalali_date()
        gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
        if end_of_day:
            return datetime(
                gy, gm, gd, 23, 59, 59, tzinfo=ZoneInfo("Asia/Tehran")
            )
        return datetime(gy, gm, gd, 0, 0, 0, tzinfo=ZoneInfo("Asia/Tehran"))


class InvoiceBatchExportDialog(QDialog):
    def __init__(
        self,
        invoice_service: InvoiceService,
        inventory_service: InventoryService | None = None,
        action_log_service: ActionLogService | None = None,
        current_admin_provider=None,
        toast: ToastManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.invoice_service = invoice_service
        self.inventory_service = inventory_service
        self.action_log_service = action_log_service
        self._current_admin_provider = current_admin_provider
        self.toast = toast
        self._invoices: list[InvoiceSummary] = []
        self._product_map: dict[str, str] = {}
        self._current_product_filter: str | None = None
        self._current_filter_fuzzy = False
        self._current_detail_matches: list[InvoiceProductMatch] = []
        self._action_cache: dict[str, str] = {}

        self.setWindowTitle(self.tr("خروجی گروهی فاکتورها"))
        self.setModal(True)
        self.setLayoutDirection(Qt.RightToLeft)
        if parent is not None:
            self.resize(parent.size())
        else:
            self.resize(1100, 720)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel(self.tr("خروجی فاکتورها"))
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(title)

        date_card = QFrame()
        date_card.setObjectName("Card")
        date_layout = QVBoxLayout(date_card)
        date_layout.setContentsMargins(16, 16, 16, 16)
        date_layout.setSpacing(12)

        self.from_date = JalaliDatePicker()
        self.to_date = JalaliDatePicker()
        self.invoice_id_from = QLineEdit()
        self.invoice_id_from.setPlaceholderText(self.tr("از (اختیاری)"))
        self.invoice_id_from.setValidator(QIntValidator(1, 999999999, self))
        self.invoice_id_from.setMaximumWidth(280)
        self.invoice_id_to = QLineEdit()
        self.invoice_id_to.setPlaceholderText(self.tr("تا (اختیاری)"))
        self.invoice_id_to.setValidator(QIntValidator(1, 999999999, self))
        self.invoice_id_to.setMaximumWidth(280)
        self.product_input = QLineEdit()
        self.product_input.setPlaceholderText(self.tr("کالا (اختیاری)"))

        filters_grid = QGridLayout()
        filters_grid.setContentsMargins(0, 0, 0, 0)
        filters_grid.setHorizontalSpacing(14)
        filters_grid.setVerticalSpacing(10)
        filters_grid.addWidget(
            self._create_filter_field(self.tr("از تاریخ"), self.from_date), 0, 0
        )
        filters_grid.addWidget(
            self._create_filter_field(self.tr("تا تاریخ"), self.to_date), 0, 1
        )
        filters_grid.addWidget(
            self._create_filter_field(
                self.tr("شماره فاکتور از"), self.invoice_id_from
            ),
            1,
            0,
        )
        filters_grid.addWidget(
            self._create_filter_field(
                self.tr("شماره فاکتور تا"), self.invoice_id_to
            ),
            1,
            1,
        )
        filters_grid.addWidget(
            self._create_filter_field(self.tr("کالا"), self.product_input),
            2,
            0,
            1,
            2,
        )
        filters_grid.setColumnStretch(0, 1)
        filters_grid.setColumnStretch(1, 1)
        date_layout.addLayout(filters_grid)

        self.product_hint = QLabel("")
        self.product_hint.setProperty("textRole", "muted")
        self.product_hint.setProperty("size", "small")
        date_layout.addWidget(self.product_hint)

        self.summary_label = QLabel(self.tr("فاکتورها: 0"))
        self.summary_label.setStyleSheet("font-weight: 600;")
        date_layout.addWidget(self.summary_label)

        layout.addWidget(date_card)

        table_card = QFrame()
        table_card.setObjectName("Card")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(16, 16, 16, 16)
        table_layout.setSpacing(8)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            [
                self.tr("شناسه"),
                self.tr("تاریخ"),
                self.tr("نوع"),
                self.tr("ردیف کالا"),
                self.tr("ردیف"),
                self.tr("تعداد"),
                self.tr("مبلغ کل"),
            ]
        )
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.itemSelectionChanged.connect(
            self._show_selected_product_details
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        for col in range(self.table.columnCount()):
            header_item = self.table.horizontalHeaderItem(col)
            if header_item is not None:
                header_item.setTextAlignment(Qt.AlignCenter)
        self.table.verticalHeader().setDefaultSectionSize(30)
        table_layout.addWidget(self.table)

        details_card = QFrame()
        details_card.setObjectName("Card")
        details_layout = QVBoxLayout(details_card)
        details_layout.setContentsMargins(16, 16, 16, 16)
        details_layout.setSpacing(10)

        self.details_label = QLabel(
            self.tr("برای نمایش جزئیات، یک ردیف از نتیجه را انتخاب کنید.")
        )
        self.details_label.setStyleSheet("font-weight: 600;")
        details_layout.addWidget(self.details_label)

        self.product_details_table = QTableWidget(0, 6)
        self.product_details_table.setHorizontalHeaderLabels(
            [
                self.tr("ردیف فاکتور"),
                self.tr("کالا"),
                self.tr("تعداد"),
                self.tr("قیمت"),
                self.tr("جمع خط"),
                self.tr("بهای خرید"),
            ]
        )
        self.product_details_table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        self.product_details_table.setSelectionBehavior(
            QAbstractItemView.SelectRows
        )
        self.product_details_table.setAlternatingRowColors(True)
        self.product_details_table.itemSelectionChanged.connect(
            self._show_selected_inventory_match
        )
        detail_header = self.product_details_table.horizontalHeader()
        detail_header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        detail_header.setSectionResizeMode(1, QHeaderView.Stretch)
        detail_header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        detail_header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        detail_header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        detail_header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        for col in range(self.product_details_table.columnCount()):
            header_item = self.product_details_table.horizontalHeaderItem(col)
            if header_item is not None:
                header_item.setTextAlignment(Qt.AlignCenter)
        self.product_details_table.verticalHeader().setDefaultSectionSize(30)
        details_layout.addWidget(self.product_details_table, 1)

        inventory_title = QLabel(self.tr("جزئیات موجودی"))
        inventory_title.setStyleSheet("font-weight: 600;")
        details_layout.addWidget(inventory_title)

        self.inventory_details_label = QTextEdit()
        self._init_rtl_text_edit(self.inventory_details_label)
        self.inventory_details_label.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )
        self.inventory_details_label.setVerticalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )
        self.inventory_details_label.setAcceptRichText(True)
        self._set_inventory_html(
            self._muted_html(
                self.tr("پس از انتخاب کالا، خلاصه موجودی نمایش داده می‌شود.")
            )
        )
        self.inventory_details_label.setStyleSheet(
            "QTextEdit {"
            "background: #f8fafc;"
            "border: 1px solid #e2e8f0;"
            "border-radius: 8px;"
            "padding: 10px;"
            "direction: rtl;"
            "text-align: right;"
            "}"
        )
        details_layout.addWidget(self.inventory_details_label)

        action_title = QLabel(self.tr("آخرین تغییر موجودی"))
        action_title.setStyleSheet("font-weight: 600;")
        details_layout.addWidget(action_title)

        self.action_details_label = QTextEdit()
        self._init_rtl_text_edit(self.action_details_label)
        self.action_details_label.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )
        self.action_details_label.setAcceptRichText(True)
        self._set_action_html(
            self._muted_html(
                self.tr(
                    "برای مشاهده تغییرات موجودی، یک ردیف کالا را انتخاب کنید."
                )
            )
        )
        self.action_details_label.setStyleSheet(
            "QTextEdit {"
            "background: #f8fafc;"
            "border: 1px solid #e2e8f0;"
            "border-radius: 8px;"
            "padding: 10px;"
            "direction: rtl;"
            "text-align: right;"
            "}"
        )
        details_layout.addWidget(self.action_details_label)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(table_card)
        split.addWidget(details_card)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setChildrenCollapsible(False)
        layout.addWidget(split, 1)

        action_row = QHBoxLayout()
        action_row.addStretch(1)
        self.close_button = QPushButton(self.tr("بستن"))
        self.close_button.clicked.connect(self.reject)
        action_row.addWidget(self.close_button)
        self.export_button = QPushButton(self.tr("خروجی"))
        self.export_button.clicked.connect(self._open_export_menu)
        action_row.addWidget(self.export_button)
        layout.addLayout(action_row)

        today_dt = datetime.now(ZoneInfo("Asia/Tehran"))
        start_dt = today_dt - timedelta(days=30)
        self._set_picker_from_gregorian(self.from_date, start_dt)
        self._set_picker_from_gregorian(self.to_date, today_dt)
        self.from_date.year_combo.currentIndexChanged.connect(self._reload)
        self.from_date.month_combo.currentIndexChanged.connect(self._reload)
        self.from_date.day_combo.currentIndexChanged.connect(self._reload)
        self.to_date.year_combo.currentIndexChanged.connect(self._reload)
        self.to_date.month_combo.currentIndexChanged.connect(self._reload)
        self.to_date.day_combo.currentIndexChanged.connect(self._reload)
        self.invoice_id_from.textChanged.connect(self._reload)
        self.invoice_id_to.textChanged.connect(self._reload)
        self.product_input.textChanged.connect(self._reload)
        self._setup_product_completer()
        self._reload()

    def _create_filter_field(self, label_text: str, field: QWidget) -> QWidget:
        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(6)
        label = QLabel(label_text)
        label.setProperty("fieldLabel", True)
        wrapper_layout.addWidget(label)
        wrapper_layout.addWidget(field)
        return wrapper

    def _reload(self) -> None:
        start_dt = self.from_date.to_gregorian_datetime(end_of_day=False)
        end_dt = self.to_date.to_gregorian_datetime(end_of_day=True)
        if end_dt < start_dt:
            self.summary_label.setText(
                self.tr("تاریخ پایان باید بعد از تاریخ شروع باشد.")
            )
            self.export_button.setEnabled(False)
            self._invoices = []
            self.table.setRowCount(0)
            self._clear_product_details(self.tr("فیلتر تاریخ نامعتبر است."))
            return
        id_from, id_to, id_error = self._parse_invoice_id_range()
        if id_error:
            self.summary_label.setText(id_error)
            self.export_button.setEnabled(False)
            self._invoices = []
            self.table.setRowCount(0)
            self._clear_product_details(id_error)
            return
        start_iso = start_dt.isoformat(timespec="seconds")
        end_iso = end_dt.isoformat(timespec="seconds")
        product_filter, fuzzy = self._resolve_product_filter()
        self._current_product_filter = product_filter
        self._current_filter_fuzzy = fuzzy
        self._invoices = self.invoice_service.list_invoices_between(
            start_iso,
            end_iso,
            product_filter=product_filter,
            fuzzy=fuzzy,
            id_from=id_from,
            id_to=id_to,
        )
        self._populate_table()
        self.export_button.setEnabled(bool(self._invoices))
        if self._invoices:
            self.table.selectRow(0)
        else:
            self._clear_product_details(
                self.tr("هیچ فاکتوری با این فیلتر پیدا نشد.")
            )

    @staticmethod
    def _set_picker_from_gregorian(
        picker: JalaliDatePicker, dt: datetime
    ) -> None:
        jalali_text = to_jalali_datetime(
            dt.isoformat(timespec="seconds")
        ).split(" ")[0]
        try:
            jy, jm, jd = (int(part) for part in jalali_text.split("/"))
        except ValueError:
            return
        picker.set_jalali_date(jy, jm, jd)

    def _populate_table(self) -> None:
        self.table.setRowCount(len(self._invoices))
        total_matches = 0
        for row_idx, invoice in enumerate(self._invoices):
            id_item = QTableWidgetItem(str(invoice.invoice_id))
            id_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, 0, id_item)

            date_item = QTableWidgetItem(to_jalali_datetime(invoice.created_at))
            date_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, 1, date_item)

            type_item = QTableWidgetItem(
                self._format_invoice_type(invoice.invoice_type)
            )
            type_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, 2, type_item)

            rows_item = QTableWidgetItem(self._format_match_rows(invoice))
            rows_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, 3, rows_item)

            lines_item = QTableWidgetItem(str(invoice.total_lines))
            lines_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, 4, lines_item)
            qty_item = QTableWidgetItem(str(invoice.total_qty))
            qty_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, 5, qty_item)
            total_item = QTableWidgetItem(format_amount(invoice.total_amount))
            total_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, 6, total_item)
            total_matches += len(invoice.product_matches)
        if self._current_product_filter:
            self.summary_label.setText(
                self.tr("فاکتورها: {count} | ردیف‌های مطابق: {matches}").format(
                    count=len(self._invoices),
                    matches=total_matches,
                )
            )
        else:
            self.summary_label.setText(
                self.tr("فاکتورها: {count}").format(count=len(self._invoices))
            )

    def _format_invoice_type(self, value: str) -> str:
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

    def _format_match_rows(self, invoice: InvoiceSummary) -> str:
        if not self._current_product_filter:
            return "-"
        rows: list[str] = []
        seen: set[int] = set()
        for match in invoice.product_matches:
            if match.row_number <= 0 or match.row_number in seen:
                continue
            seen.add(match.row_number)
            rows.append(str(match.row_number))
        return "، ".join(rows) if rows else "-"

    def _show_selected_product_details(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._invoices):
            self._clear_product_details(
                self.tr("برای نمایش جزئیات، یک ردیف از نتیجه را انتخاب کنید.")
            )
            return
        if not self._current_product_filter:
            self._clear_product_details(
                self.tr("برای جزئیات محصول، فیلتر «کالا» را وارد کنید.")
            )
            return
        invoice = self._invoices[row]
        matches = list(invoice.product_matches)
        if not matches:
            matches = self._build_matches_from_invoice_lines(invoice.invoice_id)
        if not matches:
            self._clear_product_details(
                self.tr("در این فاکتور، ردیف مطابق برای کالا پیدا نشد.")
            )
            return

        self.details_label.setText(
            self.tr("فاکتور #{id} | ردیف‌های کالا: {rows}").format(
                id=invoice.invoice_id,
                rows=self._format_match_rows(invoice),
            )
        )
        self.product_details_table.setRowCount(len(matches))
        for row_idx, match in enumerate(matches):
            row_item = QTableWidgetItem(
                str(match.row_number) if match.row_number > 0 else "-"
            )
            row_item.setTextAlignment(Qt.AlignCenter)
            self.product_details_table.setItem(row_idx, 0, row_item)

            name_item = QTableWidgetItem(match.product_name)
            name_item.setTextAlignment(
                Qt.AlignVCenter | Qt.AlignRight | Qt.AlignAbsolute
            )
            self.product_details_table.setItem(row_idx, 1, name_item)

            qty_item = QTableWidgetItem(str(match.quantity))
            qty_item.setTextAlignment(Qt.AlignCenter)
            self.product_details_table.setItem(row_idx, 2, qty_item)

            price_item = QTableWidgetItem(format_amount(match.price))
            price_item.setTextAlignment(Qt.AlignCenter)
            self.product_details_table.setItem(row_idx, 3, price_item)

            line_total_item = QTableWidgetItem(format_amount(match.line_total))
            line_total_item.setTextAlignment(Qt.AlignCenter)
            self.product_details_table.setItem(row_idx, 4, line_total_item)

            cost_item = QTableWidgetItem(format_amount(match.cost_price))
            cost_item.setTextAlignment(Qt.AlignCenter)
            self.product_details_table.setItem(row_idx, 5, cost_item)

        self._current_detail_matches = matches
        self.product_details_table.blockSignals(True)
        self.product_details_table.selectRow(0)
        self.product_details_table.blockSignals(False)
        self._show_inventory_details_for_match(matches[0])
        self._show_inventory_action_details(matches[0].product_name)

    def _build_matches_from_invoice_lines(
        self, invoice_id: int
    ) -> list[InvoiceProductMatch]:
        product_filter = self._current_product_filter
        if not product_filter:
            return []
        target = normalize_text(product_filter)
        if not target:
            return []
        result: list[InvoiceProductMatch] = []
        for row_number, line in enumerate(
            self.invoice_service.get_invoice_lines(invoice_id),
            start=1,
        ):
            line_name = normalize_text(line.product_name)
            if self._current_filter_fuzzy:
                matches = target in line_name
            else:
                matches = line_name == target
            if not matches:
                continue
            result.append(
                InvoiceProductMatch(
                    row_number=row_number,
                    product_name=line.product_name,
                    price=line.price,
                    quantity=line.quantity,
                    line_total=line.line_total,
                    cost_price=line.cost_price,
                )
            )
        return result

    def _show_selected_inventory_match(self) -> None:
        if not self._current_detail_matches:
            return
        row = self.product_details_table.currentRow()
        if row < 0 or row >= len(self._current_detail_matches):
            match = self._current_detail_matches[0]
        else:
            match = self._current_detail_matches[row]
        self._show_inventory_details_for_match(match)
        self._show_inventory_action_details(match.product_name)

    def _show_inventory_details_for_match(
        self, match: InvoiceProductMatch | None
    ) -> None:
        if match is None:
            self._set_inventory_html(
                self._muted_html(
                    self.tr(
                        "برای مشاهده جزئیات موجودی، یک کالای معتبر انتخاب کنید."
                    )
                )
            )
            return
        if not self.inventory_service or not self.inventory_service.is_loaded():
            self._set_inventory_html(
                self._muted_html(
                    self.tr(
                        "موجودی بارگذاری نشده است؛ جزئیات موجودی در دسترس نیست."
                    )
                )
            )
            return

        idx = self.inventory_service.find_index(match.product_name)
        if idx is None:
            self._set_inventory_html(
                self._muted_html(
                    self.tr("کالا در موجودی پیدا نشد: {name}").format(
                        name=match.product_name
                    )
                )
            )
            return
        try:
            df = self.inventory_service.get_dataframe()
        except Exception:  # noqa: BLE001
            self._set_inventory_html(
                self._muted_html(self.tr("خواندن جزئیات موجودی ناموفق بود."))
            )
            return
        if idx not in df.index:
            self._set_inventory_html(
                self._muted_html(
                    self.tr("کالا در موجودی پیدا نشد: {name}").format(
                        name=match.product_name
                    )
                )
            )
            return
        row = df.loc[idx]
        alarm_raw = row.get("alarm")
        alarm = (
            self.tr("تنظیم نشده")
            if alarm_raw is None or str(alarm_raw).strip() == ""
            else str(self._safe_int(alarm_raw))
        )
        source_raw = row.get("source")
        source = (
            self.tr("نامشخص")
            if source_raw is None or str(source_raw).strip() == ""
            else str(source_raw).strip()
        )
        self._set_inventory_html(
            self._format_inventory_details_html(
                match.product_name,
                f"{self._safe_int(row.get('quantity')):,}",
                format_amount(self._safe_float(row.get("avg_buy_price"))),
                format_amount(self._safe_float(row.get("last_buy_price"))),
                format_amount(self._safe_float(row.get("sell_price"))),
                alarm,
                source,
            )
        )

    def _show_inventory_action_details(self, product_name: str) -> None:
        if not product_name:
            self._set_action_html(
                self._muted_html(
                    self.tr(
                        "برای مشاهده تغییرات موجودی، یک کالا را انتخاب کنید."
                    )
                )
            )
            return
        if not self.action_log_service:
            self._set_action_html(
                self._muted_html(self.tr("اطلاعات اقدامات در دسترس نیست."))
            )
            return
        cache_key = normalize_text(product_name)
        if cache_key in self._action_cache:
            self._set_action_html(self._action_cache[cache_key])
            return

        actions = self.action_log_service.list_actions(
            limit=200,
            offset=0,
            search=product_name,
        )
        for action in actions:
            if action.action_type != "inventory_edit":
                continue
            extracted = self._extract_inventory_action_block(
                action.details, product_name
            )
            if not extracted:
                continue
            section_title, before_snapshot, after_snapshot = extracted
            formatted = self._format_inventory_action_details(
                action,
                product_name,
                section_title,
                before_snapshot,
                after_snapshot,
            )
            self._action_cache[cache_key] = formatted
            self._set_action_html(formatted)
            return

        fallback = self.tr("برای این کالا تغییر موجودی ثبت نشده است.")
        self._action_cache[cache_key] = self._muted_html(fallback)
        self._set_action_html(self._action_cache[cache_key])

    def _extract_inventory_action_block(
        self, details: str, product_name: str
    ) -> (
        tuple[
            str,
            tuple[list[tuple[str, str]], str | None],
            tuple[list[tuple[str, str]], str | None],
        ]
        | None
    ):
        text = str(details or "").strip()
        if not text:
            return None
        blocks = [part.strip() for part in text.split("\n\n") if part.strip()]
        if len(blocks) < 2:
            return None
        target = normalize_text(product_name)
        for block in blocks[1:]:
            lines = [
                line.strip() for line in block.splitlines() if line.strip()
            ]
            if not lines:
                continue
            title = lines[0]
            name_part = title
            if "]" in title:
                name_part = title.split("]", 1)[1].strip()
            if normalize_text(name_part) != target:
                continue
            try:
                before_idx = lines.index("قبل:")
                after_idx = lines.index("بعد:")
            except ValueError:
                continue
            if after_idx <= before_idx:
                continue
            before_lines = lines[before_idx + 1 : after_idx]
            after_lines = lines[after_idx + 1 :]
            before_snapshot = self._parse_inventory_snapshot(before_lines)
            after_snapshot = self._parse_inventory_snapshot(after_lines)
            return title, before_snapshot, after_snapshot
        return None

    def _parse_inventory_snapshot(
        self, lines: list[str]
    ) -> tuple[list[tuple[str, str]], str | None]:
        if not lines:
            return [], None
        marker = lines[0].strip()
        if marker in {"(هیچ)", "(وجود ندارد)", "(حذف شد)"}:
            return [], marker
        headers = [part.strip() for part in lines[0].split("|")]
        values: list[str] = []
        if len(lines) > 1:
            values = [part.strip() for part in lines[1].split("|")]
        if len(values) < len(headers):
            values.extend([""] * (len(headers) - len(values)))
        if len(values) > len(headers):
            values = values[: len(headers)]
        return list(zip(headers, values)), None

    def _format_inventory_snapshot(
        self, snapshot: tuple[list[tuple[str, str]], str | None]
    ) -> str:
        pairs, marker = snapshot
        if marker:
            return marker
        if not pairs:
            return self.tr("نامشخص")
        lines: list[str] = []
        for key, value in pairs:
            key_norm = normalize_text(key)
            if key_norm in {"نامکالا", "productname", "product_name"}:
                continue
            display = value if str(value).strip() else "-"
            lines.append(f"{key}: {display}")
        if not lines:
            lines = [f"{key}: {value}" for key, value in pairs]
        return "\n".join(lines)

    def _format_inventory_action_details(
        self,
        action,
        product_name: str,
        section_title: str,
        before_snapshot: tuple[list[tuple[str, str]], str | None],
        after_snapshot: tuple[list[tuple[str, str]], str | None],
    ) -> str:
        admin = action.admin_username or self.tr("نامشخص")
        date_text = to_jalali_datetime(action.created_at)
        before_text = self._format_inventory_snapshot(before_snapshot)
        after_text = self._format_inventory_snapshot(after_snapshot)
        before_html = self._htmlize_kv_block(before_text)
        after_html = self._htmlize_kv_block(after_text)
        header = escape(action.title or action.action_type)
        section = escape(section_title)
        return (
            "<div dir='rtl' align='right' "
            "style='text-align:right; direction:rtl; unicode-bidi:plaintext;'>"
            "<div align='right' "
            "style='font-weight:700; color:#0f172a; margin-bottom:6px; text-align:right;'>"
            + escape(product_name)
            + "</div>"
            "<div align='right' "
            "style='color:#64748b; font-size:12px; margin-bottom:8px; text-align:right; unicode-bidi:plaintext;'>"
            + escape(date_text)
            + " | "
            + escape(admin)
            + "</div>"
            "<div align='right' "
            "style='font-weight:600; margin-bottom:4px; text-align:right;'>"
            + header
            + "</div>"
            "<div align='right' "
            "style='color:#94a3b8; margin-bottom:8px; text-align:right; unicode-bidi:plaintext;'>"
            + section
            + "</div>"
            "<table dir='rtl' align='right' "
            "style='width:100%; border-collapse:separate; border-spacing:6px; direction:rtl;'>"
            "<tr>"
            "<td align='right' style='vertical-align:top; border:1px solid #e2e8f0; "
            "border-radius:8px; padding:6px;'>"
            "<div align='right' style='font-weight:700; margin-bottom:4px; text-align:right;'>"
            + escape(self.tr("قبل"))
            + "</div>"
            "<div align='right' "
            "style='color:#0f172a; font-size:12px; line-height:1.6; text-align:right; direction:rtl; unicode-bidi:plaintext;'>"
            + before_html
            + "</div>"
            "</td>"
            "<td align='right' style='vertical-align:top; border:1px solid #e2e8f0; "
            "border-radius:8px; padding:6px;'>"
            "<div align='right' style='font-weight:700; margin-bottom:4px; text-align:right;'>"
            + escape(self.tr("بعد"))
            + "</div>"
            "<div align='right' "
            "style='color:#0f172a; font-size:12px; line-height:1.6; text-align:right; direction:rtl; unicode-bidi:plaintext;'>"
            + after_html
            + "</div>"
            "</td>"
            "</tr>"
            "</table>"
            "</div>"
        )

    def _format_inventory_details_html(
        self,
        product_name: str,
        qty: str,
        avg: str,
        last: str,
        sell: str,
        alarm: str,
        source: str,
    ) -> str:
        rows = [
            (self.tr("موجودی فعلی"), qty),
            (self.tr("میانگین خرید"), avg),
            (self.tr("آخرین خرید"), last),
            (self.tr("قیمت فروش"), sell),
            (self.tr("حد هشدار"), alarm),
            (self.tr("منبع"), source),
        ]
        return (
            "<div dir='rtl' align='right' "
            "style='text-align:right; direction:rtl; unicode-bidi:plaintext; width:100%;'>"
            "<div align='right' "
            "style='font-weight:700; color:#0f172a; margin-bottom:6px; text-align:right;'>"
            + escape(product_name)
            + "</div>"
            + "<table dir='rtl' align='right' width='100%' "
            "style='width:100%; border-collapse:separate; border-spacing:0 4px;'>"
            + self._format_inventory_kv_rows(rows)
            + "</table>"
            "</div>"
        )

    def _htmlize_kv_block(self, text: str) -> str:
        lines = [
            line.strip() for line in str(text).splitlines() if line.strip()
        ]
        if not lines:
            return escape(str(text))
        return (
            "<table dir='rtl' align='right' width='100%' "
            "style='width:100%; border-collapse:separate; border-spacing:0 2px;'>"
            + "".join(
                "<tr><td align='right' "
                "style='text-align:right; direction:rtl; unicode-bidi:plaintext;'>"
                + escape(line)
                + "</td></tr>"
                for line in lines
            )
            + "</table>"
        )

    def _format_inventory_kv_rows(self, rows: list[tuple[str, str]]) -> str:
        return "".join(
            "<tr><td align='right' "
            "style='text-align:right; direction:rtl; unicode-bidi:plaintext;'>"
            "<span style='color:#64748b;'>" + escape(label) + ":</span> "
            "<span style='color:#0f172a; font-weight:600;'>"
            + escape(value)
            + "</span>"
            "</td></tr>"
            for label, value in rows
        )

    @staticmethod
    def _init_rtl_text_edit(widget: QTextEdit) -> None:
        widget.setReadOnly(True)
        widget.setLineWrapMode(QTextEdit.WidgetWidth)
        widget.setLayoutDirection(Qt.RightToLeft)
        widget.setAlignment(Qt.AlignRight | Qt.AlignTop)
        option = QTextOption()
        option.setTextDirection(Qt.RightToLeft)
        option.setAlignment(Qt.AlignRight | Qt.AlignTop)
        widget.document().setDefaultTextOption(option)

    def _wrap_details_html(self, body_html: str) -> str:
        return (
            "<html><head><meta charset='utf-8'>"
            "<style>"
            "body{font-family:Vazirmatn,Tahoma,sans-serif;"
            "direction:rtl; text-align:right; margin:0;}"
            "</style></head><body>" + body_html + "</body></html>"
        )

    def _set_inventory_html(self, body_html: str) -> None:
        self.inventory_details_label.setHtml(self._wrap_details_html(body_html))
        self._apply_rtl_text_format(self.inventory_details_label)

    def _set_action_html(self, body_html: str) -> None:
        self.action_details_label.setHtml(self._wrap_details_html(body_html))
        self._apply_rtl_text_format(self.action_details_label)

    @staticmethod
    def _apply_rtl_text_format(widget: QTextEdit) -> None:
        cursor = widget.textCursor()
        cursor.select(QTextCursor.Document)
        block_fmt = QTextBlockFormat()
        block_fmt.setLayoutDirection(Qt.RightToLeft)
        block_fmt.setAlignment(Qt.AlignRight)
        cursor.mergeBlockFormat(block_fmt)
        cursor.clearSelection()
        widget.setTextCursor(cursor)
        widget.setAlignment(Qt.AlignRight | Qt.AlignTop)

    def _muted_html(self, text: str) -> str:
        return "<span style='color:#64748b;'>" + escape(text) + "</span>"

    def _clear_product_details(self, message: str) -> None:
        self.details_label.setText(message)
        self.product_details_table.setRowCount(0)
        self._current_detail_matches = []
        self._set_inventory_html(
            self._muted_html(
                self.tr("پس از انتخاب کالا، خلاصه موجودی نمایش داده می‌شود.")
            )
        )
        self._set_action_html(
            self._muted_html(
                self.tr(
                    "برای مشاهده تغییرات موجودی، یک ردیف کالا را انتخاب کنید."
                )
            )
        )

    @staticmethod
    def _safe_int(value: object) -> int:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0
        if number != number:
            return 0
        return int(number)

    @staticmethod
    def _safe_float(value: object) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        if number != number:
            return 0.0
        return number

    def _setup_product_completer(self) -> None:
        if not self.inventory_service or not self.inventory_service.is_loaded():
            self.product_hint.setText(
                self.tr("موجودی بارگذاری نشده است؛ پیشنهاد کالا در دسترس نیست.")
            )
            return
        product_names = self.inventory_service.get_product_names()
        self._product_map = {
            normalize_text(name): name for name in product_names
        }
        completer = QCompleter(product_names, self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self.product_input.setCompleter(completer)
        self.product_hint.setText(self.tr("برای جستجوی کالا تایپ کنید."))

    def _resolve_product_filter(self) -> tuple[str | None, bool]:
        text = self.product_input.text().strip()
        if not text:
            self.product_hint.setText(
                self.tr("برای جستجوی کالا تایپ کنید.")
                if self._product_map
                else ""
            )
            return None, False
        normalized = normalize_text(text)
        if normalized in self._product_map:
            self.product_hint.setText("")
            return self._product_map[normalized], False
        if self._product_map:
            self.product_hint.setText(
                self.tr("کالا در موجودی پیدا نشد؛ جستجوی جزئی انجام می‌شود.")
            )
        return text, True

    def _parse_invoice_id_range(
        self,
    ) -> tuple[int | None, int | None, str | None]:
        from_text = self.invoice_id_from.text().strip()
        to_text = self.invoice_id_to.text().strip()
        id_from = None
        if from_text:
            try:
                id_from = int(from_text)
            except ValueError:
                return (
                    None,
                    None,
                    self.tr("شماره فاکتور «از» باید عدد باشد."),
                )
        id_to = None
        if to_text:
            try:
                id_to = int(to_text)
            except ValueError:
                return (
                    None,
                    None,
                    self.tr("شماره فاکتور «تا» باید عدد باشد."),
                )
        if id_from is not None and id_from < 1:
            return (
                None,
                None,
                self.tr("شماره فاکتور «از» باید عدد مثبت باشد."),
            )
        if id_to is not None and id_to < 1:
            return (
                None,
                None,
                self.tr("شماره فاکتور «تا» باید عدد مثبت باشد."),
            )
        if id_from is not None and id_to is not None and id_to < id_from:
            return None, None, self.tr("بازه شماره فاکتور نامعتبر است.")
        return id_from, id_to, None

    def _open_export_menu(self) -> None:
        menu = QMenu(self.export_button)
        excel_action = menu.addAction(self.tr("اکسل (.xlsx)"))
        pdf_action = menu.addAction(self.tr("پی‌دی‌اف (.pdf)"))
        action = menu.exec(
            self.export_button.mapToGlobal(
                QPoint(0, self.export_button.height())
            )
        )
        if action == excel_action:
            self._export("excel")
        elif action == pdf_action:
            self._export("pdf")

    def _export(self, file_format: str) -> None:
        if not self._invoices:
            dialogs.show_error(
                self,
                self.tr("خروجی"),
                self.tr("فاکتوری برای خروجی وجود ندارد."),
            )
            return
        if file_format == "pdf":
            default_name = "invoices_export.pdf"
            file_filter = self.tr("فایل‌های PDF (*.pdf)")
        else:
            default_name = "invoices_export.xlsx"
            file_filter = self.tr("فایل‌های اکسل (*.xlsx)")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("خروجی فاکتورها"),
            default_name,
            file_filter,
        )
        if not file_path:
            return
        if file_format == "pdf":
            if not file_path.lower().endswith(".pdf"):
                file_path = f"{file_path}.pdf"
        else:
            if not file_path.lower().endswith(".xlsx"):
                file_path = f"{file_path}.xlsx"
        invoices_with_lines = []
        for invoice in self._invoices:
            lines = self.invoice_service.get_invoice_lines(invoice.invoice_id)
            invoices_with_lines.append((invoice, lines))
        if file_format == "pdf":
            export_invoices_pdf(file_path, invoices_with_lines)
        else:
            export_invoices_excel(file_path, invoices_with_lines)
        if self.action_log_service:
            admin = (
                self._current_admin_provider()
                if self._current_admin_provider
                else None
            )
            product_filter, fuzzy = self._resolve_product_filter()
            id_from, id_to, _ = self._parse_invoice_id_range()
            jy_from, jm_from, jd_from = self.from_date.jalali_date()
            jy_to, jm_to, jd_to = self.to_date.jalali_date()
            filter_text = (
                product_filter if product_filter else self.tr("همه کالاها")
            )
            filter_type = (
                self.tr("دقیق")
                if product_filter and not fuzzy
                else self.tr("جزئی")
            )
            if id_from is None and id_to is None:
                id_range_text = self.tr("همه")
            elif id_from is not None and id_to is not None:
                id_range_text = self.tr("{id_from} تا {id_to}").format(
                    id_from=id_from, id_to=id_to
                )
            elif id_from is not None:
                id_range_text = self.tr("از {id_from}").format(id_from=id_from)
            else:
                id_range_text = self.tr("تا {id_to}").format(id_to=id_to)
            self.action_log_service.log_action(
                "invoice_batch_export",
                self.tr("خروجی گروهی فاکتور"),
                self.tr(
                    "بازه تاریخ: {from_date} تا {to_date}\n"
                    "فیلتر شماره فاکتور: {id_range}\n"
                    "فیلتر کالا: {filter_text}\n"
                    "نوع فیلتر: {filter_type}\n"
                    "تعداد فاکتور: {invoice_count}\n"
                    "فرمت: {fmt}\n"
                    "مسیر: {path}"
                ).format(
                    from_date=f"{jy_from:04d}/{jm_from:02d}/{jd_from:02d}",
                    to_date=f"{jy_to:04d}/{jm_to:02d}/{jd_to:02d}",
                    id_range=id_range_text,
                    filter_text=filter_text,
                    filter_type=filter_type,
                    invoice_count=len(invoices_with_lines),
                    fmt=("PDF" if file_format == "pdf" else self.tr("اکسل")),
                    path=file_path,
                ),
                admin=admin,
            )
        if self.toast:
            self.toast.show(self.tr("خروجی فاکتورها انجام شد"), "success")
        else:
            dialogs.show_info(
                self,
                self.tr("خروجی"),
                self.tr("خروجی فاکتورها انجام شد."),
            )
