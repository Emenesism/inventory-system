from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QBoxLayout,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class SalesInvoicePreviewLine:
    product_name: str
    price: float
    quantity: int
    line_total: float


@dataclass(frozen=True)
class SalesInvoiceStockProjection:
    product_name: str
    current_qty: int
    sold_qty: int
    new_qty: int


@dataclass(frozen=True)
class SalesInvoicePreviewData:
    lines: list[SalesInvoicePreviewLine]
    total_lines: int
    total_quantity: int
    total_amount: float
    invalid_count: int
    projections: list[SalesInvoiceStockProjection]


class SalesInvoicePreviewDialog(QDialog):
    def __init__(
        self, parent: QWidget | None, data: SalesInvoicePreviewData
    ) -> None:
        super().__init__(parent)
        self.data = data

        self.setWindowTitle(self.tr("پیش نمایش فاکتور فروش"))
        self.setModal(True)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumSize(720, 560)
        self.resize(840, 640)
        self.setSizeGripEnabled(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setLayoutDirection(Qt.RightToLeft)

        content = QWidget()
        content.setLayoutDirection(Qt.RightToLeft)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(8, 8, 8, 8)
        content_layout.setSpacing(16)
        content_layout.setAlignment(Qt.AlignRight | Qt.AlignTop)

        title = QLabel(self.tr("پیش نمایش فاکتور فروش"))
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        title.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        content_layout.addWidget(title, 0, Qt.AlignRight)

        subtitle = QLabel(
            self.tr("لطفاً قبل از ثبت، فاکتور فروش را بررسی کنید.")
        )
        subtitle.setProperty("textRole", "muted")
        subtitle.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        subtitle.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        content_layout.addWidget(subtitle, 0, Qt.AlignRight)

        name_card = QFrame()
        name_card.setObjectName("Card")
        name_layout = QHBoxLayout(name_card)
        name_layout.setContentsMargins(16, 12, 16, 12)
        name_layout.setSpacing(12)

        name_label = QLabel(self.tr("نام فاکتور:"))
        name_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        name_layout.addWidget(name_label)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText(self.tr("اختیاری"))
        self.name_input.setLayoutDirection(Qt.RightToLeft)
        self.name_input.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        name_layout.addWidget(self.name_input, 1)

        content_layout.addWidget(name_card)

        lines_card = QFrame()
        lines_card.setObjectName("Card")
        lines_card.setLayoutDirection(Qt.RightToLeft)
        lines_layout = QVBoxLayout(lines_card)
        lines_layout.setContentsMargins(16, 16, 16, 16)
        lines_layout.setSpacing(12)
        lines_layout.setAlignment(Qt.AlignRight | Qt.AlignTop)

        lines_title = QLabel(self.tr("اقلام فاکتور"))
        lines_title.setStyleSheet("font-weight: 600;")
        lines_title.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lines_title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lines_layout.addWidget(lines_title, 0, Qt.AlignRight)

        self.lines_table = QTableWidget(len(data.lines) + 1, 2)
        self.lines_table.setHorizontalHeaderLabels(
            [self.tr("شرح کالا"), self.tr("تعداد")]
        )
        self.lines_table.setAlternatingRowColors(True)
        self.lines_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.lines_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.lines_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.lines_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.lines_table.setFocusPolicy(Qt.NoFocus)
        self.lines_table.setSizeAdjustPolicy(
            QAbstractScrollArea.AdjustToContents
        )
        self.lines_table.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Minimum
        )
        self.lines_table.horizontalHeader().setStretchLastSection(True)
        self.lines_table.verticalHeader().setDefaultSectionSize(32)
        self.lines_table.setMinimumHeight(200)
        self.lines_table.setLayoutDirection(Qt.RightToLeft)
        self.lines_table.setStyleSheet(
            "QHeaderView::section { text-align: right; padding-right: 6px; }"
        )

        lines_header = self.lines_table.horizontalHeader()
        lines_header.setDefaultAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lines_header.setSectionResizeMode(0, QHeaderView.Stretch)
        lines_header.setSectionResizeMode(1, QHeaderView.ResizeToContents)

        for row_idx, line in enumerate(data.lines):
            self._set_item(self.lines_table, row_idx, 0, line.product_name)
            self._set_item(self.lines_table, row_idx, 1, str(line.quantity))

        totals_row = len(data.lines)
        self._set_item(self.lines_table, totals_row, 0, self.tr("جمع کل"))
        self._set_item(
            self.lines_table,
            totals_row,
            1,
            str(data.total_quantity),
        )

        self._fit_table_height(self.lines_table)
        lines_layout.addWidget(self.lines_table)
        content_layout.addWidget(lines_card)

        scroll.setWidget(content)
        layout.addWidget(scroll)

        question = QLabel(self.tr("ثبت این فاکتور؟"))
        question.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        question.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(question, 0, Qt.AlignRight)

        button_row = QHBoxLayout()
        button_row.setDirection(QBoxLayout.RightToLeft)

        confirm_button = QPushButton(self.tr("ثبت فاکتور"))
        confirm_button.clicked.connect(self.accept)
        confirm_button.setDefault(True)
        button_row.addWidget(confirm_button)

        cancel_button = QPushButton(self.tr("انصراف"))
        cancel_button.setProperty("variant", "secondary")
        cancel_button.clicked.connect(self.reject)
        button_row.addWidget(cancel_button)

        layout.addLayout(button_row)

    def invoice_name(self) -> str | None:
        name = self.name_input.text().strip()
        return name if name else None

    @staticmethod
    def _fit_table_height(table: QTableWidget) -> None:
        header_height = table.horizontalHeader().height()
        frame = table.frameWidth() * 2
        height = header_height + table.verticalHeader().length() + frame
        height = max(height, table.minimumHeight())
        table.setMinimumHeight(height)
        table.setMaximumHeight(height)

    @staticmethod
    def _summary_label(title: str, value: str) -> QLabel:
        label = QLabel(f"{title}: {value}")
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return label

    @staticmethod
    def _set_item(table: QTableWidget, row: int, col: int, text: str) -> None:
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignVCenter | Qt.AlignRight)
        table.setItem(row, col, item)
