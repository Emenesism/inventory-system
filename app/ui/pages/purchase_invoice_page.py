from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QValidator
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from app.services.fuzzy_search import get_fuzzy_matches
from app.services.purchase_service import PurchaseLine
from app.utils.numeric import format_amount, normalize_numeric_text


class PriceSpinBox(QSpinBox):
    def textFromValue(self, value: int) -> str:  # noqa: N802
        if value == 0:
            return ""
        return format_amount(value)

    def valueFromText(self, text: str) -> int:  # noqa: N802
        normalized = normalize_numeric_text(text)
        if not normalized:
            return 0
        try:
            return int(float(normalized))
        except ValueError:
            return 0

    def validate(self, text: str, pos: int):  # noqa: ANN001, N802
        normalized = normalize_numeric_text(text)
        if normalized == "":
            return (QValidator.Intermediate, text, pos)
        if normalized.replace(".", "", 1).isdigit():
            return (QValidator.Acceptable, text, pos)
        return (QValidator.Invalid, text, pos)


class QuantitySpinBox(QSpinBox):
    def textFromValue(self, value: int) -> str:  # noqa: N802
        if value == 0:
            return ""
        return str(value)

    def valueFromText(self, text: str) -> int:  # noqa: N802
        normalized = normalize_numeric_text(text)
        if not normalized:
            return 0
        try:
            return int(float(normalized))
        except ValueError:
            return 0

    def validate(self, text: str, pos: int):  # noqa: ANN001, N802
        normalized = normalize_numeric_text(text)
        if normalized == "":
            return (QValidator.Intermediate, text, pos)
        if normalized.replace(".", "", 1).isdigit():
            return (QValidator.Acceptable, text, pos)
        return (QValidator.Invalid, text, pos)


class PurchaseInvoicePage(QWidget):
    submit_requested = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.product_provider: Callable[[], list[str]] | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel(self.tr("فاکتور خرید"))
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        header.addWidget(title)
        header.addStretch(1)
        layout.addLayout(header)

        info = QLabel(
            self.tr(
                "اقلام خرید را اضافه کنید. با تایپ نام کالا، پیشنهادهای مشابه "
                "از موجودی نمایش داده می‌شود."
            )
        )
        info.setProperty("textRole", "muted")
        layout.addWidget(info)

        table_card = QFrame()
        table_card.setObjectName("Card")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(16, 16, 16, 16)
        table_layout.setSpacing(12)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(
            [self.tr("کالا"), self.tr("تعداد"), self.tr("قیمت خرید")]
        )
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setDefaultSectionSize(36)
        table_layout.addWidget(self.table)
        self.table.installEventFilter(self)

        button_row = QHBoxLayout()
        self.add_button = QPushButton(self.tr("افزودن ردیف"))
        self.add_button.clicked.connect(self.add_row)
        button_row.addWidget(self.add_button)

        self.remove_button = QPushButton(self.tr("حذف انتخاب‌شده"))
        self.remove_button.clicked.connect(self.remove_selected)
        button_row.addWidget(self.remove_button)

        button_row.addStretch(1)

        self.submit_button = QPushButton(self.tr("ثبت فاکتور"))
        self.submit_button.clicked.connect(self._emit_submit)
        button_row.addWidget(self.submit_button)
        table_layout.addLayout(button_row)

        layout.addWidget(table_card)

        self.add_row()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() == QEvent.KeyPress:
            key = event.key()
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self._advance_row()
                return True
            if key == Qt.Key_Delete:
                self.remove_selected()
                return True
        return super().eventFilter(obj, event)

    def set_product_provider(self, provider: Callable[[], list[str]]) -> None:
        self.product_provider = provider

    def add_row(self) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)

        product_input = QLineEdit()
        product_input.setPlaceholderText(self.tr("نام کالا را بنویسید..."))
        product_input.setClearButtonEnabled(True)
        product_input.textChanged.connect(
            lambda text, widget=product_input: self._update_completer(
                text, widget
            )
        )
        product_input.installEventFilter(self)

        quantity_input = QuantitySpinBox()
        quantity_input.setRange(0, 1_000_000)
        quantity_input.setSingleStep(1)
        quantity_input.setValue(0)
        quantity_input.installEventFilter(self)

        price_input = PriceSpinBox()
        price_input.setRange(0, 1_000_000_000)
        price_input.setSingleStep(100)
        price_input.setValue(0)
        price_input.setGroupSeparatorShown(True)
        price_input.installEventFilter(self)

        self.table.setCellWidget(row, 0, product_input)
        self.table.setCellWidget(row, 1, quantity_input)
        self.table.setCellWidget(row, 2, price_input)
        product_input.setFocus()

    def _advance_row(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            self.add_row()
            return
        col = 0
        if row < self.table.rowCount() - 1:
            next_row = row + 1
            self.table.setCurrentCell(next_row, col)
            widget = self.table.cellWidget(next_row, col)
            if widget is not None:
                widget.setFocus()
            return
        self.add_row()
        next_row = self.table.rowCount() - 1
        self.table.setCurrentCell(next_row, col)
        widget = self.table.cellWidget(next_row, col)
        if widget is not None:
            widget.setFocus()

    def remove_selected(self) -> None:
        rows = sorted(
            set(index.row() for index in self.table.selectedIndexes()),
            reverse=True,
        )
        for row in rows:
            self.table.removeRow(row)

    def collect_lines(self) -> list[PurchaseLine]:
        lines: list[PurchaseLine] = []
        for row in range(self.table.rowCount()):
            product_widget = self.table.cellWidget(row, 0)
            qty_widget = self.table.cellWidget(row, 1)
            price_widget = self.table.cellWidget(row, 2)
            if not isinstance(product_widget, QLineEdit):
                continue
            product_name = product_widget.text().strip()
            price = (
                price_widget.value()
                if isinstance(price_widget, QSpinBox)
                else 0
            )
            quantity = (
                qty_widget.value() if isinstance(qty_widget, QSpinBox) else 0
            )
            lines.append(
                PurchaseLine(
                    product_name=product_name, price=price, quantity=quantity
                )
            )
        return lines

    def set_enabled_state(self, enabled: bool) -> None:
        self.add_button.setEnabled(enabled)
        self.remove_button.setEnabled(enabled)
        self.submit_button.setEnabled(enabled)
        self.table.setEnabled(enabled)

    def reset_after_submit(self) -> None:
        self.table.setRowCount(0)
        self.add_row()

    def _emit_submit(self) -> None:
        self.submit_requested.emit(self.collect_lines())

    def _update_completer(self, text: str, widget: QLineEdit) -> None:
        if not self.product_provider:
            return
        from PySide6.QtCore import QStringListModel, Qt
        from PySide6.QtWidgets import QCompleter

        matches = get_fuzzy_matches(text, self.product_provider())
        completer = widget.completer()

        if not matches:
            if completer:
                completer.popup().hide()
            return

        if completer is None:
            model = QStringListModel(matches)
            completer = QCompleter(model, widget)
            completer.setCompletionMode(QCompleter.PopupCompletion)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setFilterMode(Qt.MatchContains)
            widget.setCompleter(completer)
        else:
            model = completer.model()
            if isinstance(model, QStringListModel):
                model.setStringList(matches)
            else:
                completer.setModel(QStringListModel(matches))
        completer.complete()
