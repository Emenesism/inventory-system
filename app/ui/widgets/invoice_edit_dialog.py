from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QAbstractItemDelegate,
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
        self.updated_name: str | None = invoice.invoice_name
        self._updating = False

        self.setWindowTitle(
            self.tr("ویرایش فاکتور #{id}").format(id=invoice.invoice_id)
        )
        self.setModal(True)
        self.setMinimumWidth(720)
        self.setLayoutDirection(Qt.RightToLeft)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel(
            self.tr("ویرایش فاکتور #{id}").format(id=invoice.invoice_id)
        )
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(title)

        meta = QLabel(
            self.tr(
                "نوع: {type} | ردیف‌ها: {lines} | مجموع تعداد: {qty}"
            ).format(
                type=self._format_invoice_type(invoice.invoice_type),
                lines=invoice.total_lines,
                qty=invoice.total_qty,
            )
        )
        meta.setProperty("textRole", "muted")
        layout.addWidget(meta)

        name_row = QHBoxLayout()
        name_label = QLabel(self.tr("نام فاکتور:"))
        name_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        name_row.addWidget(name_label)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText(self.tr("اختیاری"))
        self.name_input.setText(invoice.invoice_name or "")
        name_row.addWidget(self.name_input, 1)
        layout.addLayout(name_row)

        hint_text = self.tr(
            "برای ویرایش دوبار کلیک کنید. برای حذف ردیف اشتباه از «حذف ردیف» "
            "استفاده کنید و سپس ذخیره را بزنید."
        )
        if invoice.invoice_type.startswith("sales"):
            hint_text += " " + self.tr(
                "در فروش، تغییر نام کالا از میانگین خرید فعلی استفاده می‌کند."
            )
        hint = QLabel(hint_text)
        hint.setProperty("textRole", "muted")
        hint.setProperty("size", "small")
        layout.addWidget(hint)

        search_row = QHBoxLayout()
        search_label = QLabel(self.tr("جستجو:"))
        search_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        search_row.addWidget(search_label)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            self.tr("جستجو در کالاهای این فاکتور...")
        )
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._apply_search_filter)
        search_row.addWidget(self.search_input, 1)
        layout.addLayout(search_row)

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 12, 12, 12)
        card_layout.setSpacing(8)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            [
                self.tr("کالا"),
                self.tr("قیمت"),
                self.tr("تعداد"),
                self.tr("جمع خط"),
            ]
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
        self.total_lines_label = QLabel(self.tr("ردیف‌ها: 0"))
        self.total_qty_label = QLabel(self.tr("مجموع تعداد: 0"))
        self.total_amount_label = QLabel(self.tr("مبلغ کل: 0"))
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
        self.add_button = QPushButton(self.tr("افزودن ردیف"))
        self.add_button.clicked.connect(self._append_empty_row)
        button_row.addWidget(self.add_button)

        self.remove_button = QPushButton(self.tr("حذف ردیف"))
        self.remove_button.clicked.connect(self._remove_selected_line)
        button_row.addWidget(self.remove_button)
        button_row.addStretch(1)
        self.cancel_button = QPushButton(self.tr("انصراف"))
        self.cancel_button.clicked.connect(self.reject)
        button_row.addWidget(self.cancel_button)
        self.save_button = QPushButton(self.tr("ذخیره تغییرات"))
        self.save_button.clicked.connect(self._try_accept)
        button_row.addWidget(self.save_button)
        layout.addLayout(button_row)

        if self._is_sales():
            self._apply_sales_ui()

        self._populate(lines)
        self._delegate = _EnterMoveDelegate(self._handle_enter, self.table)
        self.table.setItemDelegate(self._delegate)
        self.table.installEventFilter(self)
        self.table.itemChanged.connect(self._on_item_changed)
        self._update_validation_state()
        self._apply_search_filter()

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
                    "original_price": line.price,
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
            dialogs.show_error(
                self,
                self.tr("ویرایش فاکتور"),
                self.tr("یک ردیف را برای حذف انتخاب کنید."),
            )
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
                "original_price": 0.0,
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
        self._apply_search_filter()
        return row

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating:
            return
        if item.column() in {1, 2}:
            self._recalculate_row(item.row())
        if item.column() == 0:
            self._apply_search_filter()
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
            qty_item = self.table.item(row, 2)
            if qty_item is None:
                continue
            qty = self._parse_quantity(qty_item.text())
            if qty is None:
                continue
            total_qty += qty
            if not self._is_sales():
                price_item = self.table.item(row, 1)
                if price_item is None:
                    continue
                price = self._parse_price(price_item.text())
                if price is None:
                    continue
                total_amount += price * qty
        self.total_lines_label.setText(
            self.tr("ردیف‌ها: {count}").format(count=self.table.rowCount())
        )
        self.total_qty_label.setText(
            self.tr("مجموع تعداد: {count}").format(count=total_qty)
        )
        self.total_amount_label.setText(
            self.tr("مبلغ کل: {amount}").format(
                amount=self._format_amount(total_amount)
            )
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
            errors.append(self.tr("فاکتور باید حداقل یک ردیف داشته باشد."))
            return errors
        for row in range(self.table.rowCount()):
            product_item = self.table.item(row, 0)
            product = product_item.text().strip() if product_item else ""
            if not product:
                errors.append(
                    self.tr("ردیف {row}: نام کالا الزامی است.").format(
                        row=row + 1
                    )
                )
                continue
            if normalize_text(product) not in self._product_map:
                errors.append(
                    self.tr("ردیف {row}: کالا در موجودی پیدا نشد.").format(
                        row=row + 1
                    )
                )
            price_item = self.table.item(row, 1)
            price = self._parse_price(price_item.text() if price_item else "")
            if not self._is_sales():
                if price is None or price <= 0:
                    errors.append(
                        self.tr(
                            "ردیف {row}: قیمت باید بزرگ‌تر از صفر باشد."
                        ).format(row=row + 1)
                    )
            qty_item = self.table.item(row, 2)
            qty = self._parse_quantity(qty_item.text() if qty_item else "")
            if qty is None or qty <= 0:
                errors.append(
                    self.tr(
                        "ردیف {row}: تعداد باید عدد صحیح مثبت باشد."
                    ).format(row=row + 1)
                )
        return errors

    def _try_accept(self) -> None:
        errors = self._collect_errors()
        if errors:
            dialogs.show_error(
                self,
                self.tr("ویرایش فاکتور"),
                "\n".join(errors[:5]),
            )
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
            if price is None and self._is_sales():
                meta = product_item.data(Qt.UserRole) or {}
                price = float(meta.get("original_price", 0.0))
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
                self.tr("ویرایش فاکتور"),
                self.tr("فاکتور باید حداقل یک ردیف معتبر داشته باشد."),
            )
            return
        self.updated_name = self._normalized_name()
        self.updated_lines = lines
        self.accept()

    def _normalized_name(self) -> str | None:
        name = self.name_input.text().strip()
        return name if name else None

    def _is_sales(self) -> bool:
        return self.invoice.invoice_type.startswith("sales")

    def _format_invoice_type(self, invoice_type: str) -> str:
        if invoice_type == "purchase":
            return self.tr("خرید")
        if invoice_type == "sales_manual":
            return self.tr("فروش دستی")
        if invoice_type == "sales_basalam":
            return self.tr("فروش باسلام")
        if invoice_type == "sales_site":
            return self.tr("فروش سایت")
        if invoice_type.startswith("sales"):
            return self.tr("فروش")
        return invoice_type

    def _apply_sales_ui(self) -> None:
        self.table.setColumnHidden(1, True)
        self.table.setColumnHidden(3, True)
        self.total_amount_label.setVisible(False)

    def _apply_search_filter(self) -> None:
        query = normalize_text(self.search_input.text().strip())
        for row in range(self.table.rowCount()):
            product_item = self.table.item(row, 0)
            product = (
                normalize_text(product_item.text()) if product_item else ""
            )
            match = True if not query else query in product
            self.table.setRowHidden(row, not match)

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
