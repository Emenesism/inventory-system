from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEvent, QLocale, QPoint, Qt, Signal
from PySide6.QtGui import QValidator
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QVBoxLayout,
)

from app.services.fuzzy_search import get_fuzzy_matches
from app.services.sales_manual_service import SalesManualLine
from app.utils.numeric import normalize_numeric_text


class QuantitySpinBox(QSpinBox):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setLocale(QLocale.c())
        editor = self.lineEdit()
        if editor is not None:
            editor.setInputMethodHints(Qt.ImhDigitsOnly | Qt.ImhPreferNumbers)
            editor.textEdited.connect(
                lambda text, widget=editor: self._normalize_editor_text(
                    widget, text
                )
            )

    def textFromValue(self, value: int) -> str:  # noqa: N802
        if value == 0:
            return ""
        return str(value)

    def valueFromText(self, text: str) -> int:  # noqa: N802
        normalized = normalize_numeric_text(text)
        if not normalized:
            return 0
        try:
            return int(round(float(normalized)))
        except ValueError:
            return 0

    def validate(self, text: str, pos: int):  # noqa: ANN001, N802
        normalized = normalize_numeric_text(text)
        if normalized == "":
            return (QValidator.Intermediate, text, pos)
        if normalized.isdigit():
            return (QValidator.Acceptable, text, pos)
        return (QValidator.Invalid, text, pos)

    @staticmethod
    def _normalize_editor_text(editor: QLineEdit, text: str) -> None:
        normalized = normalize_numeric_text(text)
        digits_only = "".join(ch for ch in normalized if "0" <= ch <= "9")
        if digits_only == text:
            return
        cursor = editor.cursorPosition()
        editor.blockSignals(True)
        editor.setText(digits_only)
        editor.blockSignals(False)
        editor.setCursorPosition(min(cursor, len(digits_only)))


class SalesManualInvoiceDialog(QDialog):
    submit_requested = Signal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.product_provider: Callable[[], list[str]] | None = None

        self.setWindowTitle(self.tr("فاکتور فروش دستی"))
        self.setModal(True)
        self.setMinimumSize(900, 640)
        self.resize(1040, 720)
        self.setSizeGripEnabled(True)
        self.setLayoutDirection(Qt.RightToLeft)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel(self.tr("فاکتور فروش دستی"))
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        header.addWidget(title)
        header.addStretch(1)
        layout.addLayout(header)

        info = QLabel(
            self.tr(
                "اقلام فروش را اضافه کنید. با تایپ نام کالا، پیشنهادهای مشابه "
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

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(
            [self.tr("کالا"), self.tr("تعداد")]
        )
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setDefaultSectionSize(42)
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

        self.cancel_button = QPushButton(self.tr("انصراف"))
        self.cancel_button.setProperty("variant", "secondary")
        self.cancel_button.clicked.connect(self.reject)
        button_row.addWidget(self.cancel_button)

        table_layout.addLayout(button_row)
        layout.addWidget(table_card)

        self.add_row()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() == QEvent.KeyPress:
            key = event.key()
            if key in (Qt.Key_Return, Qt.Key_Enter):
                if isinstance(obj, QLineEdit):
                    completer = obj.completer()
                    if completer and completer.popup().isVisible():
                        return False
                row, col = self._resolve_cell_position(obj)
                if row < 0:
                    self.add_row()
                    return True
                if row >= self.table.rowCount() - 1:
                    self.add_row(focus_column=col if col >= 0 else 0)
                else:
                    self._focus_cell(row + 1, col if col >= 0 else 0)
                return True
            if key == Qt.Key_Delete:
                self.remove_selected()
                return True
        return super().eventFilter(obj, event)

    def set_product_provider(self, provider: Callable[[], list[str]]) -> None:
        self.product_provider = provider

    def add_row(self, focus_column: int | None = 0) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)

        product_input = QLineEdit()
        product_input.setPlaceholderText(self.tr("نام کالا را بنویسید..."))
        product_input.setClearButtonEnabled(False)
        product_input.setLayoutDirection(Qt.RightToLeft)
        product_input.setAlignment(
            Qt.AlignRight | Qt.AlignAbsolute | Qt.AlignVCenter
        )
        product_input.setMinimumHeight(32)
        product_input.textChanged.connect(
            lambda text, widget=product_input: self._update_completer(
                text, widget
            )
        )
        product_input.installEventFilter(self)

        quantity_input = QuantitySpinBox()
        quantity_input.setRange(0, 1_000_000)
        quantity_input.setButtonSymbols(QAbstractSpinBox.NoButtons)
        quantity_input.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        quantity_input.setMinimumHeight(32)
        quantity_input.setSingleStep(1)
        quantity_input.setValue(0)
        line_edit = quantity_input.lineEdit()
        if line_edit is not None:
            line_edit.setLayoutDirection(Qt.RightToLeft)
            line_edit.setAlignment(
                Qt.AlignRight | Qt.AlignAbsolute | Qt.AlignVCenter
            )
            line_edit.setPlaceholderText(self.tr("تعداد را وارد کنید"))
        quantity_input.installEventFilter(self)

        self.table.setCellWidget(row, 0, product_input)
        self.table.setCellWidget(row, 1, quantity_input)
        if focus_column is not None:
            self._focus_cell(row, focus_column)

    def remove_selected(self) -> None:
        rows = sorted(
            set(index.row() for index in self.table.selectedIndexes()),
            reverse=True,
        )
        for row in rows:
            self.table.removeRow(row)

    def _resolve_cell_position(self, widget) -> tuple[int, int]:
        if widget is self.table:
            return self.table.currentRow(), self.table.currentColumn()
        try:
            pos = widget.mapTo(self.table.viewport(), QPoint(1, 1))
            index = self.table.indexAt(pos)
            if index.isValid():
                return index.row(), index.column()
        except Exception:  # noqa: BLE001
            pass
        return self.table.currentRow(), self.table.currentColumn()

    def _focus_cell(self, row: int, col: int) -> None:
        if row < 0 or col < 0:
            return
        if row >= self.table.rowCount():
            return
        if col >= self.table.columnCount():
            col = 0
        self.table.setCurrentCell(row, col)
        widget = self.table.cellWidget(row, col)
        if widget is not None:
            widget.setFocus()

    def collect_lines(self) -> list[SalesManualLine]:
        lines: list[SalesManualLine] = []
        for row in range(self.table.rowCount()):
            product_widget = self.table.cellWidget(row, 0)
            qty_widget = self.table.cellWidget(row, 1)
            if not isinstance(product_widget, QLineEdit):
                continue
            product_name = product_widget.text().strip()
            quantity = (
                qty_widget.value() if isinstance(qty_widget, QSpinBox) else 0
            )
            lines.append(
                SalesManualLine(product_name=product_name, quantity=quantity)
            )
        return lines

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
