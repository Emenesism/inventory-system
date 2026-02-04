from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCompleter,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.fuzzy_search import get_fuzzy_matches
from app.services.sales_import_service import (
    SalesPreviewRow,
    SalesPreviewSummary,
)


class ProductNameDelegate(QStyledItemDelegate):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._product_names: list[str] = []

    def set_product_names(self, names: list[str]) -> None:
        self._product_names = names

    def createEditor(self, parent, option, index):  # noqa: ANN001
        if index.column() != 0:
            return super().createEditor(parent, option, index)
        editor = QLineEdit(parent)
        editor.setLayoutDirection(Qt.RightToLeft)
        editor.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        completer = QCompleter(editor)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        editor.setCompleter(completer)
        editor.textChanged.connect(
            lambda text, ed=editor: self._update_completer(ed, text)
        )
        return editor

    def setEditorData(self, editor, index) -> None:  # noqa: ANN001
        if isinstance(editor, QLineEdit):
            editor.setText(str(index.data(Qt.EditRole) or "").strip())
            return
        super().setEditorData(editor, index)

    def setModelData(self, editor, model, index) -> None:  # noqa: ANN001
        if isinstance(editor, QLineEdit):
            model.setData(index, editor.text().strip())
            return
        super().setModelData(editor, model, index)

    def _update_completer(self, editor: QLineEdit, text: str) -> None:
        if not self._product_names:
            return
        matches = get_fuzzy_matches(text, self._product_names)
        completer = editor.completer()
        if completer is None:
            return
        if not matches:
            completer.popup().hide()
            return
        model = completer.model()
        if model is None:
            from PySide6.QtCore import QStringListModel

            completer.setModel(QStringListModel(matches))
        else:
            from PySide6.QtCore import QStringListModel

            if isinstance(model, QStringListModel):
                model.setStringList(matches)
            else:
                completer.setModel(QStringListModel(matches))
        completer.complete()


class QuantityDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):  # noqa: ANN001
        if index.column() != 1:
            return super().createEditor(parent, option, index)
        editor = QLineEdit(parent)
        editor.setValidator(QIntValidator(0, 1_000_000, editor))
        editor.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return editor

    def setEditorData(self, editor, index) -> None:  # noqa: ANN001
        if isinstance(editor, QLineEdit):
            editor.setText(str(index.data(Qt.EditRole) or "0").strip())
            return
        super().setEditorData(editor, index)

    def setModelData(self, editor, model, index) -> None:  # noqa: ANN001
        if isinstance(editor, QLineEdit):
            text = editor.text().strip()
            model.setData(index, text if text != "" else "0")
            return
        super().setModelData(editor, model, index)


class SalesImportPage(QWidget):
    preview_requested = Signal(str)
    apply_requested = Signal()
    product_name_edited = Signal(list)
    export_requested = Signal()
    manual_invoice_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.preview_rows: list[SalesPreviewRow] = []
        self._suppress_item_updates = False
        self._pending_rows: set[int] = set()
        self._edit_timer = QTimer(self)
        self._edit_timer.setSingleShot(True)
        self._edit_timer.setInterval(350)
        self._edit_timer.timeout.connect(self._emit_pending_updates)
        self._edit_enabled = False
        self._deferred_refresh = False
        self._deferred_timer = QTimer(self)
        self._deferred_timer.setSingleShot(True)
        self._deferred_timer.setInterval(200)
        self._deferred_timer.timeout.connect(self._apply_deferred_refresh)
        self._product_names: list[str] = []
        self._product_delegate = ProductNameDelegate(self)
        self._quantity_delegate = QuantityDelegate(self)
        self._sales_invoice_type: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("Sales Import")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        header.addWidget(title)
        header.addStretch(1)
        layout.addLayout(header)

        file_card = QFrame()
        file_card.setObjectName("Card")
        file_layout = QHBoxLayout(file_card)
        file_layout.setContentsMargins(16, 16, 16, 16)
        file_layout.setSpacing(12)

        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText(
            "Select sales Excel/CSV file (Product Name, Quantity)..."
        )
        self.file_input.textEdited.connect(self._on_file_text_edited)
        file_layout.addWidget(self.file_input, 1)

        self.browse_button = QPushButton("Browse")
        self.browse_button.clicked.connect(self._browse_file)
        file_layout.addWidget(self.browse_button)

        self.preview_button = QPushButton("Load Preview")
        self.preview_button.clicked.connect(self._emit_preview)
        file_layout.addWidget(self.preview_button)

        self.manual_invoice_button = QPushButton("Manual Invoice")
        self.manual_invoice_button.clicked.connect(
            self.manual_invoice_requested.emit
        )
        file_layout.addWidget(self.manual_invoice_button)

        self.apply_button = QPushButton("Apply Updates")
        self.apply_button.clicked.connect(self.apply_requested.emit)
        file_layout.addWidget(self.apply_button)

        self.export_button = QPushButton("Export")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export_requested.emit)
        file_layout.addWidget(self.export_button)

        layout.addWidget(file_card)

        helper = QLabel(
            "Expected columns: Product Name, Quantity (or Quantity Sold). "
            "Optional: Sell Price for profit analytics."
        )
        helper.setProperty("textRole", "muted")
        layout.addWidget(helper)

        summary_card = QFrame()
        summary_card.setObjectName("Card")
        summary_layout = QHBoxLayout(summary_card)
        summary_layout.setContentsMargins(16, 16, 16, 16)
        summary_layout.setSpacing(24)

        self.total_label = QLabel("Total: 0")
        self.success_label = QLabel("Success: 0")
        self.errors_label = QLabel("Errors: 0")
        summary_layout.addWidget(self.total_label)
        summary_layout.addWidget(self.success_label)
        summary_layout.addWidget(self.errors_label)
        summary_layout.addStretch(1)

        layout.addWidget(summary_card)

        table_card = QFrame()
        table_card.setObjectName("Card")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(16, 16, 16, 16)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Product", "Quantity Sold", "Status", "Message"]
        )
        self.table.setSortingEnabled(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.itemChanged.connect(self._on_item_changed)
        table_layout.addWidget(self.table)

        layout.addWidget(table_card)

    def set_edit_mode(
        self, enabled: bool, product_names: list[str] | None = None
    ) -> None:
        was_enabled = self._edit_enabled
        self._edit_enabled = enabled
        self._product_names = product_names or []
        if enabled:
            self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
            self.table.setSortingEnabled(False)
            self.table.verticalHeader().setDefaultSectionSize(38)
            self._product_delegate.set_product_names(self._product_names)
            self.table.setItemDelegateForColumn(0, self._product_delegate)
            self.table.setItemDelegateForColumn(1, self._quantity_delegate)
            self.table.setEditTriggers(
                QAbstractItemView.DoubleClicked
                | QAbstractItemView.EditKeyPressed
                | QAbstractItemView.SelectedClicked
            )
            if not was_enabled:
                self.table.installEventFilter(self)
        else:
            self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self.table.setSelectionMode(QAbstractItemView.SingleSelection)
            self.table.setSortingEnabled(False)
            self.table.verticalHeader().setDefaultSectionSize(32)
            self.table.setItemDelegateForColumn(0, None)
            self.table.setItemDelegateForColumn(1, None)
            if was_enabled:
                self.table.removeEventFilter(self)
        if self.preview_rows:
            summary = self._compute_summary()
            self.set_preview(self.preview_rows, summary)

    def _compute_summary(self) -> SalesPreviewSummary:
        total = len(self.preview_rows)
        success = sum(1 for row in self.preview_rows if row.status == "OK")
        errors = total - success
        return SalesPreviewSummary(total=total, success=success, errors=errors)

    def set_preview(
        self, rows: list[SalesPreviewRow], summary: SalesPreviewSummary
    ) -> None:
        self.preview_rows = list(rows)
        self._pending_rows.clear()
        self._edit_timer.stop()
        self._deferred_refresh = False
        self._deferred_timer.stop()
        self.export_button.setEnabled(bool(rows))
        self.total_label.setText(f"Total: {summary.total}")
        self.success_label.setText(f"Success: {summary.success}")
        self.errors_label.setText(f"Errors: {summary.errors}")
        self._sort_preview_rows()
        self._rebuild_table()
        header = self.table.horizontalHeader()
        if self._edit_enabled:
            header.setSectionResizeMode(0, QHeaderView.Stretch)
            header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(3, QHeaderView.Interactive)
            self.table.setColumnWidth(3, 260)
        else:
            self.table.resizeColumnsToContents()

    def set_enabled_state(self, enabled: bool) -> None:
        self.file_input.setEnabled(enabled)
        self.browse_button.setEnabled(enabled)
        self.preview_button.setEnabled(enabled)
        self.manual_invoice_button.setEnabled(enabled)
        self.apply_button.setEnabled(enabled)
        self.export_button.setEnabled(enabled and bool(self.preview_rows))
        self.table.setEnabled(enabled)

    def reset_after_apply(self) -> None:
        self.preview_rows = []
        self._pending_rows.clear()
        self._edit_timer.stop()
        self._deferred_refresh = False
        self._deferred_timer.stop()
        self.export_button.setEnabled(False)
        self.file_input.clear()
        self._sales_invoice_type = None
        self.total_label.setText("Total: 0")
        self.success_label.setText("Success: 0")
        self.errors_label.setText("Errors: 0")
        self.table.setRowCount(0)

    def _emit_preview(self) -> None:
        path = self.file_input.text().strip()
        if not path:
            return
        if not self._ensure_sales_type():
            return
        self.preview_requested.emit(path)

    def _browse_file(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Sales File",
            "",
            "Excel Files (*.xlsx *.xlsm);;CSV Files (*.csv)",
        )
        if file_path:
            self._sales_invoice_type = None
            if not self._ensure_sales_type():
                return
            self.file_input.setText(file_path)
            self.preview_requested.emit(file_path)

    def _on_file_text_edited(self, _text: str) -> None:
        self._sales_invoice_type = None

    def get_sales_invoice_type(self) -> str:
        return self._sales_invoice_type or "sales"

    def _ensure_sales_type(self) -> bool:
        if self._sales_invoice_type:
            return True
        items = ["Basalam", "Site"]
        selection, ok = QInputDialog.getItem(
            self,
            "Sales Source",
            "Select sales source for this file:",
            items,
            0,
            False,
        )
        if not ok:
            return False
        normalized = str(selection).strip().lower()
        if normalized == "basalam":
            self._sales_invoice_type = "sales_basalam"
        elif normalized == "site":
            self._sales_invoice_type = "sales_site"
        else:
            self._sales_invoice_type = "sales"
        return True

    def flush_pending_edits(self) -> None:
        if not self._pending_rows:
            return
        self._edit_timer.stop()
        self._emit_pending_updates()

    def update_preview_rows(
        self, row_indices: list[int], summary: SalesPreviewSummary
    ) -> None:
        self.total_label.setText(f"Total: {summary.total}")
        self.success_label.setText(f"Success: {summary.success}")
        self.errors_label.setText(f"Errors: {summary.errors}")
        if self._is_editing():
            self._update_status_cells(row_indices)
            self._deferred_refresh = True
            self._deferred_timer.start()
            return
        self._sort_preview_rows()
        self._rebuild_table()

    def _emit_pending_updates(self) -> None:
        if not self._pending_rows:
            return
        rows = sorted(self._pending_rows)
        self._pending_rows.clear()
        self.product_name_edited.emit(rows)

    def _is_editing(self) -> bool:
        return self.table.state() == QAbstractItemView.EditingState

    def _apply_deferred_refresh(self) -> None:
        if not self._deferred_refresh:
            return
        if self._is_editing():
            self._deferred_timer.start()
            return
        self._deferred_refresh = False
        self._sort_preview_rows()
        self._rebuild_table()

    def _update_status_cells(self, row_indices: list[int]) -> None:
        if not row_indices or not self.preview_rows:
            return
        targets = set(row_indices)
        self._suppress_item_updates = True
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            if name_item is None:
                continue
            idx = name_item.data(Qt.UserRole)
            if not isinstance(idx, int) or idx not in targets:
                continue
            row_data = self.preview_rows[idx]

            status_item = self.table.item(row, 2)
            if status_item is None:
                status_item = QTableWidgetItem()
                status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, 2, status_item)
            status_item.setText(row_data.status)

            message_item = self.table.item(row, 3)
            if message_item is None:
                message_item = QTableWidgetItem()
                message_item.setFlags(message_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, 3, message_item)
            message_item.setText(row_data.message)
        self._suppress_item_updates = False

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._suppress_item_updates:
            return
        if item.column() not in (0, 1):
            return
        idx = item.data(Qt.UserRole)
        if not isinstance(idx, int):
            return
        if idx < 0 or idx >= len(self.preview_rows):
            return
        if item.column() == 0:
            raw_text = item.text()
            text = raw_text.strip()
            if raw_text != text:
                self._suppress_item_updates = True
                item.setText(text)
                self._suppress_item_updates = False
            self.preview_rows[idx].product_name = text
            self._pending_rows.add(idx)
            self._edit_timer.start()
            return
        raw_text = item.text()
        text = raw_text.strip()
        if text == "":
            value = 0
        elif text.isdigit():
            value = int(text)
        else:
            value = 0
        if raw_text != str(value):
            self._suppress_item_updates = True
            item.setText(str(value))
            self._suppress_item_updates = False
        self.preview_rows[idx].quantity_sold = value
        self._pending_rows.add(idx)
        self._edit_timer.start()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if not self._edit_enabled:
            return super().eventFilter(obj, event)
        if obj is self.table and event.type() == QEvent.KeyPress:
            key = event.key()
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self._handle_enter()
                return True
            if key == Qt.Key_Delete:
                self._delete_selected_rows()
                return True
        return super().eventFilter(obj, event)

    def _queue_refresh(self, idx: int) -> None:
        if idx < 0:
            return
        self._pending_rows.add(idx)
        self._edit_timer.start()

    def _sort_preview_rows(self) -> None:
        def status_rank(row: SalesPreviewRow) -> int:
            value = str(row.status or "").strip().lower()
            if value == "error":
                return 0
            if value == "ok":
                return 1
            return 2

        self.preview_rows.sort(key=status_rank)

    def _rebuild_table(self) -> None:
        if not self.preview_rows:
            self.table.setRowCount(0)
            return
        was_sorting = self.table.isSortingEnabled()
        self._suppress_item_updates = True
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.preview_rows))
        for row_idx, row in enumerate(self.preview_rows):
            name_item = QTableWidgetItem(row.product_name)
            name_item.setData(Qt.UserRole, row_idx)
            if self._edit_enabled:
                name_item.setFlags(name_item.flags() | Qt.ItemIsEditable)
            else:
                name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row_idx, 0, name_item)

            qty_item = QTableWidgetItem(str(row.quantity_sold))
            if self._edit_enabled:
                qty_item.setFlags(qty_item.flags() | Qt.ItemIsEditable)
            else:
                qty_item.setFlags(qty_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row_idx, 1, qty_item)

            status_item = QTableWidgetItem(row.status)
            status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row_idx, 2, status_item)

            message_item = QTableWidgetItem(row.message)
            message_item.setFlags(message_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row_idx, 3, message_item)

        self._suppress_item_updates = False
        self.table.setSortingEnabled(was_sorting)

    def _handle_enter(self) -> None:
        row = self.table.currentRow()
        col = self.table.currentColumn()
        if row < 0:
            return
        if col not in (0, 1):
            col = 0
        if row >= self.table.rowCount() - 1:
            self._add_row()
            next_row = self.table.rowCount() - 1
        else:
            next_row = row + 1
        self.table.setCurrentCell(next_row, col)
        item = self.table.item(next_row, col)
        if item is not None:
            self.table.editItem(item)

    def _add_row(self) -> None:
        new_row = SalesPreviewRow(
            product_name="",
            quantity_sold=1,
            sell_price=0.0,
            cost_price=0.0,
            status="Error",
            message="Missing product name",
            resolved_name="",
        )
        self.preview_rows.append(new_row)
        self.export_button.setEnabled(True)
        self._sort_preview_rows()
        self._rebuild_table()
        preview_idx = None
        for idx, row in enumerate(self.preview_rows):
            if row is new_row:
                preview_idx = idx
                break
        if preview_idx is not None:
            self._queue_refresh(preview_idx)

    def _delete_selected_rows(self) -> None:
        selected_rows = sorted(
            {index.row() for index in self.table.selectedIndexes()},
            reverse=True,
        )
        if not selected_rows:
            return

        preview_indices: list[int] = []
        for row in selected_rows:
            item = self.table.item(row, 0)
            if item is None:
                continue
            idx = item.data(Qt.UserRole)
            if isinstance(idx, int):
                preview_indices.append(idx)

        removed = sorted(set(preview_indices), reverse=True)
        for idx in removed:
            if 0 <= idx < len(self.preview_rows):
                self.preview_rows.pop(idx)

        self.export_button.setEnabled(bool(self.preview_rows))
        if not self.preview_rows:
            self.total_label.setText("Total: 0")
            self.success_label.setText("Success: 0")
            self.errors_label.setText("Errors: 0")
            self.table.setRowCount(0)
            return
        self._sort_preview_rows()
        self._rebuild_table()
        self._refresh_all_rows()

    def _reindex_after_removal(self, removed: list[int]) -> None:
        if not removed:
            return
        removed_sorted = sorted(removed)

        def remap(old_idx: int) -> int:
            shift = 0
            for removed_idx in removed_sorted:
                if old_idx > removed_idx:
                    shift += 1
                else:
                    break
            return old_idx - shift

        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is None:
                continue
            old_idx = item.data(Qt.UserRole)
            if not isinstance(old_idx, int):
                continue
            new_idx = remap(old_idx)
            item.setData(Qt.UserRole, new_idx)

    def _refresh_all_rows(self) -> None:
        self._pending_rows = set(range(len(self.preview_rows)))
        if self._pending_rows:
            self._edit_timer.start()
