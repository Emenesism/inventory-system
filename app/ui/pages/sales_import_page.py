from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.sales_import_service import (
    SalesPreviewRow,
    SalesPreviewSummary,
)


class SalesImportPage(QWidget):
    preview_requested = Signal(str)
    apply_requested = Signal()
    product_name_edited = Signal(list)
    export_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.preview_rows: list[SalesPreviewRow] = []
        self._suppress_item_updates = False
        self._pending_rows: set[int] = set()
        self._edit_timer = QTimer(self)
        self._edit_timer.setSingleShot(True)
        self._edit_timer.setInterval(350)
        self._edit_timer.timeout.connect(self._emit_pending_updates)

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
        file_layout.addWidget(self.file_input, 1)

        self.browse_button = QPushButton("Browse")
        self.browse_button.clicked.connect(self._browse_file)
        file_layout.addWidget(self.browse_button)

        self.preview_button = QPushButton("Load Preview")
        self.preview_button.clicked.connect(self._emit_preview)
        file_layout.addWidget(self.preview_button)

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
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.itemChanged.connect(self._on_item_changed)
        table_layout.addWidget(self.table)

        layout.addWidget(table_card)

    def set_preview(
        self, rows: list[SalesPreviewRow], summary: SalesPreviewSummary
    ) -> None:
        self.preview_rows = rows
        self._pending_rows.clear()
        self._edit_timer.stop()
        self.export_button.setEnabled(bool(rows))
        self.total_label.setText(f"Total: {summary.total}")
        self.success_label.setText(f"Success: {summary.success}")
        self.errors_label.setText(f"Errors: {summary.errors}")

        was_sorting = self.table.isSortingEnabled()
        self._suppress_item_updates = True
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            name_item = QTableWidgetItem(row.product_name)
            name_item.setData(Qt.UserRole, row_idx)
            self.table.setItem(row_idx, 0, name_item)

            qty_item = QTableWidgetItem(str(row.quantity_sold))
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
        self.table.resizeColumnsToContents()

    def set_enabled_state(self, enabled: bool) -> None:
        self.file_input.setEnabled(enabled)
        self.browse_button.setEnabled(enabled)
        self.preview_button.setEnabled(enabled)
        self.apply_button.setEnabled(enabled)
        self.export_button.setEnabled(enabled and bool(self.preview_rows))
        self.table.setEnabled(enabled)

    def reset_after_apply(self) -> None:
        self.preview_rows = []
        self._pending_rows.clear()
        self._edit_timer.stop()
        self.export_button.setEnabled(False)
        self.file_input.clear()
        self.total_label.setText("Total: 0")
        self.success_label.setText("Success: 0")
        self.errors_label.setText("Errors: 0")
        self.table.setRowCount(0)

    def _emit_preview(self) -> None:
        path = self.file_input.text().strip()
        if path:
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
            self.file_input.setText(file_path)
            self.preview_requested.emit(file_path)

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

        was_sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        row_map: dict[int, int] = {}
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is None:
                continue
            idx = item.data(Qt.UserRole)
            if isinstance(idx, int):
                row_map[idx] = row

        self._suppress_item_updates = True
        for preview_idx in row_indices:
            table_row = row_map.get(preview_idx)
            if table_row is None or preview_idx >= len(self.preview_rows):
                continue
            preview_row = self.preview_rows[preview_idx]

            status_item = self.table.item(table_row, 2)
            if status_item is None:
                status_item = QTableWidgetItem()
                self.table.setItem(table_row, 2, status_item)
            status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
            status_item.setText(preview_row.status)

            message_item = self.table.item(table_row, 3)
            if message_item is None:
                message_item = QTableWidgetItem()
                self.table.setItem(table_row, 3, message_item)
            message_item.setFlags(message_item.flags() & ~Qt.ItemIsEditable)
            message_item.setText(preview_row.message)
        self._suppress_item_updates = False
        self.table.setSortingEnabled(was_sorting)

    def _emit_pending_updates(self) -> None:
        if not self._pending_rows:
            return
        rows = sorted(self._pending_rows)
        self._pending_rows.clear()
        self.product_name_edited.emit(rows)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._suppress_item_updates:
            return
        if item.column() != 0:
            return
        idx = item.data(Qt.UserRole)
        if not isinstance(idx, int):
            return
        if idx < 0 or idx >= len(self.preview_rows):
            return
        raw_text = item.text()
        text = raw_text.strip()
        if raw_text != text:
            self._suppress_item_updates = True
            item.setText(text)
            self._suppress_item_updates = False
        self.preview_rows[idx].product_name = text
        self._pending_rows.add(idx)
        self._edit_timer.start()
