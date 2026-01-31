from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QAbstractItemDelegate,
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.services.invoice_service import InvoiceLine, InvoiceSummary
from app.utils import dialogs
from app.utils.numeric import format_amount, normalize_numeric_text
from app.utils.text import normalize_text


class InvoiceEditDialog(QDialog):
    def __init__(
        self,
        invoice: InvoiceSummary,
        lines: list[InvoiceLine],
        product_names: list[str],
        cost_map: dict[str, float],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.invoice = invoice
        self._cost_map = cost_map
        self._product_map = {
            normalize_text(name): name for name in product_names
        }
        self.updated_lines: list[InvoiceLine] | None = None
        self._updating = False

        self.setWindowTitle(f"Edit Invoice #{invoice.invoice_id}")
        self.setModal(True)
        self.setMinimumWidth(720)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel(f"Edit Invoice #{invoice.invoice_id}")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(title)

        meta = QLabel(
            f"Type: {invoice.invoice_type.title()} | "
            f"Lines: {invoice.total_lines} | "
            f"Total Qty: {invoice.total_qty}"
        )
        meta.setProperty("textRole", "muted")
        layout.addWidget(meta)

        hint_text = (
            "Double-click to edit. Use Remove Line for mistakes, "
            "then Save to apply inventory changes."
        )
        if invoice.invoice_type.startswith("sales"):
            hint_text += " Changing product uses current avg buy price."
        hint = QLabel(hint_text)
        hint.setProperty("textRole", "muted")
        hint.setProperty("size", "small")
        layout.addWidget(hint)

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 12, 12, 12)
        card_layout.setSpacing(8)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Product", "Price", "Qty", "Line Total"]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.AnyKeyPressed
        )
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.horizontalHeader().setStretchLastSection(True)
        card_layout.addWidget(self.table)
        layout.addWidget(card)

        summary_row = QHBoxLayout()
        self.total_lines_label = QLabel("Lines: 0")
        self.total_qty_label = QLabel("Total Qty: 0")
        self.total_amount_label = QLabel("Total Amount: 0")
        summary_row.addWidget(self.total_lines_label)
        summary_row.addWidget(self.total_qty_label)
        summary_row.addWidget(self.total_amount_label)
        summary_row.addStretch(1)
        layout.addLayout(summary_row)

        self.error_label = QLabel("")
        self.error_label.setProperty("textRole", "danger")
        self.error_label.setProperty("size", "small")
        layout.addWidget(self.error_label)

        button_row = QHBoxLayout()
        self.add_button = QPushButton("Add Line")
        self.add_button.clicked.connect(self._append_empty_row)
        button_row.addWidget(self.add_button)

        self.remove_button = QPushButton("Remove Line")
        self.remove_button.clicked.connect(self._remove_selected_line)
        button_row.addWidget(self.remove_button)
        button_row.addStretch(1)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_row.addWidget(self.cancel_button)
        self.save_button = QPushButton("Save Changes")
        self.save_button.clicked.connect(self._try_accept)
        button_row.addWidget(self.save_button)
        layout.addLayout(button_row)

        self._populate(lines)
        self._delegate = _EnterMoveDelegate(self._handle_enter, self.table)
        self.table.setItemDelegate(self._delegate)
        self.table.installEventFilter(self)
        self.table.itemChanged.connect(self._on_item_changed)
        self._update_validation_state()

    def _populate(self, lines: list[InvoiceLine]) -> None:
        self._updating = True
        self.table.blockSignals(True)
        self.table.setRowCount(len(lines))
        for row_idx, line in enumerate(lines):
            product_item = QTableWidgetItem(line.product_name)
            product_item.setData(
                Qt.UserRole,
                {
                    "original_product": line.product_name,
                    "cost_price": line.cost_price,
                },
            )
            self.table.setItem(row_idx, 0, product_item)

            price_item = QTableWidgetItem(self._format_number(line.price))
            price_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_idx, 1, price_item)

            qty_item = QTableWidgetItem(str(line.quantity))
            qty_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_idx, 2, qty_item)

            total_item = QTableWidgetItem(
                self._format_amount(line.price * line.quantity)
            )
            total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            total_item.setFlags(total_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row_idx, 3, total_item)
        self.table.blockSignals(False)
        self._updating = False
        self._recalculate_summary()

    def _remove_selected_line(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            dialogs.show_error(self, "Edit Invoice", "Select a line to remove.")
            return
        self.table.removeRow(row)
        self._recalculate_summary()
        self._update_validation_state()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self.table and event.type() == QEvent.KeyPress:
            key = event.key()
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self._handle_enter()
                return True
            if key == Qt.Key_Delete:
                if self.table.state() != QAbstractItemView.EditingState:
                    if self.table.currentRow() >= 0:
                        self._remove_selected_line()
                    return True
        return super().eventFilter(obj, event)

    def _handle_enter(self) -> None:
        row = self.table.currentRow()
        col = self.table.currentColumn()
        if col < 0:
            col = 0
        if row < 0:
            new_row = self._append_empty_row()
            self.table.setCurrentCell(new_row, col)
            self.table.editItem(self.table.item(new_row, col))
            return
        if row < self.table.rowCount() - 1:
            self.table.setCurrentCell(row + 1, col)
            self.table.editItem(self.table.item(row + 1, col))
            return
        new_row = self._append_empty_row()
        self.table.setCurrentCell(new_row, col)
        self.table.editItem(self.table.item(new_row, col))

    def _append_empty_row(self) -> int:
        self._updating = True
        self.table.blockSignals(True)
        row = self.table.rowCount()
        self.table.insertRow(row)

        product_item = QTableWidgetItem("")
        product_item.setData(
            Qt.UserRole,
            {
                "original_product": "",
                "cost_price": 0.0,
            },
        )
        self.table.setItem(row, 0, product_item)

        price_item = QTableWidgetItem("")
        price_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(row, 1, price_item)

        qty_item = QTableWidgetItem("")
        qty_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(row, 2, qty_item)

        total_item = QTableWidgetItem("")
        total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        total_item.setFlags(total_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, 3, total_item)

        self.table.blockSignals(False)
        self._updating = False
        self._recalculate_summary()
        self._update_validation_state()
        return row

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating:
            return
        if item.column() in {1, 2}:
            self._recalculate_row(item.row())
        self._recalculate_summary()
        self._update_validation_state()

    def _recalculate_row(self, row_idx: int) -> None:
        price_item = self.table.item(row_idx, 1)
        qty_item = self.table.item(row_idx, 2)
        if price_item is None or qty_item is None:
            return
        price = self._parse_price(price_item.text())
        qty = self._parse_quantity(qty_item.text())
        total_item = self.table.item(row_idx, 3)
        if total_item is None:
            total_item = QTableWidgetItem("")
            total_item.setFlags(total_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row_idx, 3, total_item)
        if price is None or qty is None:
            total_item.setText("")
            return
        total_item.setText(self._format_amount(price * qty))

    def _recalculate_summary(self) -> None:
        total_qty = 0
        total_amount = 0.0
        for row in range(self.table.rowCount()):
            price_item = self.table.item(row, 1)
            qty_item = self.table.item(row, 2)
            if price_item is None or qty_item is None:
                continue
            price = self._parse_price(price_item.text())
            qty = self._parse_quantity(qty_item.text())
            if price is None or qty is None:
                continue
            total_qty += qty
            total_amount += price * qty
        self.total_lines_label.setText(f"Lines: {self.table.rowCount()}")
        self.total_qty_label.setText(f"Total Qty: {total_qty}")
        self.total_amount_label.setText(
            f"Total Amount: {self._format_amount(total_amount)}"
        )

    def _update_validation_state(self) -> None:
        errors = self._collect_errors()
        if errors:
            self.error_label.setText("\n".join(errors[:3]))
            self.save_button.setEnabled(False)
        else:
            self.error_label.setText("")
            self.save_button.setEnabled(True)

    def _collect_errors(self) -> list[str]:
        errors: list[str] = []
        if self.table.rowCount() == 0:
            errors.append("Invoice must have at least one line.")
            return errors
        for row in range(self.table.rowCount()):
            product_item = self.table.item(row, 0)
            product = product_item.text().strip() if product_item else ""
            if not product:
                errors.append(f"Row {row + 1}: Product is required.")
                continue
            if normalize_text(product) not in self._product_map:
                errors.append(f"Row {row + 1}: Product not found in inventory.")
            price_item = self.table.item(row, 1)
            price = self._parse_price(price_item.text() if price_item else "")
            if price is None or price <= 0:
                errors.append(f"Row {row + 1}: Price must be > 0.")
            qty_item = self.table.item(row, 2)
            qty = self._parse_quantity(qty_item.text() if qty_item else "")
            if qty is None or qty <= 0:
                errors.append(f"Row {row + 1}: Qty must be a whole number.")
        return errors

    def _try_accept(self) -> None:
        errors = self._collect_errors()
        if errors:
            dialogs.show_error(self, "Edit Invoice", "\n".join(errors[:5]))
            return
        lines: list[InvoiceLine] = []
        for row in range(self.table.rowCount()):
            product_item = self.table.item(row, 0)
            price_item = self.table.item(row, 1)
            qty_item = self.table.item(row, 2)
            if not product_item or not price_item or not qty_item:
                continue
            product_key = normalize_text(product_item.text().strip())
            product_name = self._product_map.get(product_key, "")
            if not product_name:
                continue
            price = self._parse_price(price_item.text())
            qty = self._parse_quantity(qty_item.text())
            if price is None or qty is None:
                continue
            meta = product_item.data(Qt.UserRole) or {}
            original_product = meta.get("original_product", product_name)
            cost_price = meta.get("cost_price", price)
            if self.invoice.invoice_type.startswith("sales"):
                if normalize_text(original_product) != product_key:
                    cost_price = float(self._cost_map.get(product_key, 0.0))
            else:
                cost_price = price
            lines.append(
                InvoiceLine(
                    product_name=product_name,
                    price=float(price),
                    quantity=int(qty),
                    line_total=float(price * qty),
                    cost_price=float(cost_price),
                )
            )
        if not lines:
            dialogs.show_error(
                self,
                "Edit Invoice",
                "Invoice must have at least one valid line.",
            )
            return
        self.updated_lines = lines
        self.accept()

    @staticmethod
    def _parse_price(text: str) -> float | None:
        normalized = normalize_numeric_text(str(text))
        if not normalized:
            return None
        try:
            value = float(normalized)
        except ValueError:
            return None
        if value != value:
            return None
        return value

    @staticmethod
    def _parse_quantity(text: str) -> int | None:
        normalized = normalize_numeric_text(str(text))
        if not normalized:
            return None
        try:
            value = float(normalized)
        except ValueError:
            return None
        if value != value or value % 1 != 0:
            return None
        return int(value)

    @staticmethod
    def _format_amount(value: float) -> str:
        return format_amount(value)

    @staticmethod
    def _format_number(value: float) -> str:
        if value is None:
            return ""
        if float(value).is_integer():
            return str(int(value))
        return str(value)


class _EnterMoveDelegate(QStyledItemDelegate):
    def __init__(self, on_enter, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self._on_enter = on_enter

    def eventFilter(self, editor, event) -> bool:  # noqa: ANN001, N802
        if event.type() == QEvent.KeyPress and event.key() in (
            Qt.Key_Return,
            Qt.Key_Enter,
        ):
            self.commitData.emit(editor)
            self.closeEditor.emit(editor, QAbstractItemDelegate.NoHint)
            if self._on_enter:
                self._on_enter()
            return True
        return super().eventFilter(editor, event)
