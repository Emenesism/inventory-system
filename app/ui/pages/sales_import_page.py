from __future__ import annotations

from PySide6.QtCore import Signal
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

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.preview_rows: list[SalesPreviewRow] = []

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
        self.file_input.setPlaceholderText("Select sales Excel/CSV file...")
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

        layout.addWidget(file_card)

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
        table_layout.addWidget(self.table)

        layout.addWidget(table_card)

    def set_preview(
        self, rows: list[SalesPreviewRow], summary: SalesPreviewSummary
    ) -> None:
        self.preview_rows = rows
        self.total_label.setText(f"Total: {summary.total}")
        self.success_label.setText(f"Success: {summary.success}")
        self.errors_label.setText(f"Errors: {summary.errors}")

        self.table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            self.table.setItem(row_idx, 0, QTableWidgetItem(row.product_name))
            self.table.setItem(
                row_idx, 1, QTableWidgetItem(str(row.quantity_sold))
            )
            self.table.setItem(row_idx, 2, QTableWidgetItem(row.status))
            self.table.setItem(row_idx, 3, QTableWidgetItem(row.message))
        self.table.resizeColumnsToContents()

    def set_enabled_state(self, enabled: bool) -> None:
        self.file_input.setEnabled(enabled)
        self.browse_button.setEnabled(enabled)
        self.preview_button.setEnabled(enabled)
        self.apply_button.setEnabled(enabled)
        self.table.setEnabled(enabled)

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
