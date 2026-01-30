from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QBoxLayout,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.utils.numeric import format_amount


@dataclass(frozen=True)
class PurchaseInvoicePreviewLine:
    product_name: str
    price: float
    quantity: int
    line_total: float


@dataclass(frozen=True)
class PurchaseInvoiceStockProjection:
    product_name: str
    current_qty: int
    added_qty: int
    new_qty: int


@dataclass(frozen=True)
class PurchaseInvoicePreviewData:
    lines: list[PurchaseInvoicePreviewLine]
    total_lines: int
    total_quantity: int
    total_cost: float
    invalid_count: int
    projections: list[PurchaseInvoiceStockProjection]


class PurchaseInvoicePreviewDialog(QDialog):
    def __init__(
        self, parent: QWidget | None, data: PurchaseInvoicePreviewData
    ) -> None:
        super().__init__(parent)
        self.data = data

        self.setWindowTitle("پیش نمایش فاکتور خرید")
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

        title = QLabel("پیش نمایش فاکتور خرید")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        title.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        content_layout.addWidget(title, 0, Qt.AlignRight)

        subtitle = QLabel("لطفاً قبل از ثبت، فاکتور خرید را بررسی کنید.")
        subtitle.setProperty("textRole", "muted")
        subtitle.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        subtitle.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        content_layout.addWidget(subtitle, 0, Qt.AlignRight)

        summary_card = QFrame()
        summary_card.setObjectName("Card")
        summary_card.setLayoutDirection(Qt.RightToLeft)
        summary_layout = QGridLayout(summary_card)
        summary_layout.setContentsMargins(16, 16, 16, 16)
        summary_layout.setHorizontalSpacing(24)
        summary_layout.setVerticalSpacing(8)
        summary_layout.setAlignment(Qt.AlignRight | Qt.AlignTop)

        total_lines_label = self._summary_label(
            "تعداد ردیف ها", str(data.total_lines)
        )
        summary_layout.addWidget(total_lines_label, 0, 0, Qt.AlignRight)

        total_qty_label = self._summary_label(
            "جمع تعداد", str(data.total_quantity)
        )
        summary_layout.addWidget(total_qty_label, 0, 1, Qt.AlignRight)

        total_cost_label = self._summary_label(
            "جمع کل", format_amount(data.total_cost)
        )
        summary_layout.addWidget(total_cost_label, 1, 0, Qt.AlignRight)
        if data.invalid_count:
            invalid_label = self._summary_label(
                "ردیف های نامعتبر", str(data.invalid_count)
            )
            summary_layout.addWidget(invalid_label, 1, 1, Qt.AlignRight)
        summary_layout.setColumnStretch(0, 1)
        summary_layout.setColumnStretch(1, 1)
        content_layout.addWidget(summary_card)

        lines_card = QFrame()
        lines_card.setObjectName("Card")
        lines_card.setLayoutDirection(Qt.RightToLeft)
        lines_layout = QVBoxLayout(lines_card)
        lines_layout.setContentsMargins(16, 16, 16, 16)
        lines_layout.setSpacing(12)
        lines_layout.setAlignment(Qt.AlignRight | Qt.AlignTop)

        lines_title = QLabel("اقلام فاکتور")
        lines_title.setStyleSheet("font-weight: 600;")
        lines_title.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lines_title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lines_layout.addWidget(lines_title, 0, Qt.AlignRight)

        self.lines_table = QTableWidget(len(data.lines), 4)
        self.lines_table.setHorizontalHeaderLabels(
            ["شرح کالا", "تعداد", "قیمت خرید", "جمع خط"]
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
        lines_header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        lines_header.setSectionResizeMode(3, QHeaderView.ResizeToContents)

        for row_idx, line in enumerate(data.lines):
            self._set_item(self.lines_table, row_idx, 0, line.product_name)
            self._set_item(self.lines_table, row_idx, 1, str(line.quantity))
            self._set_item(
                self.lines_table, row_idx, 2, format_amount(line.price)
            )
            self._set_item(
                self.lines_table, row_idx, 3, format_amount(line.line_total)
            )

        self._fit_table_height(self.lines_table)
        lines_layout.addWidget(self.lines_table)
        content_layout.addWidget(lines_card)

        stock_card = QFrame()
        stock_card.setObjectName("Card")
        stock_card.setLayoutDirection(Qt.RightToLeft)
        stock_layout = QVBoxLayout(stock_card)
        stock_layout.setContentsMargins(16, 16, 16, 16)
        stock_layout.setSpacing(12)
        stock_layout.setAlignment(Qt.AlignRight | Qt.AlignTop)

        stock_title = QLabel("پیش بینی موجودی پس از ثبت")
        stock_title.setStyleSheet("font-weight: 600;")
        stock_title.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        stock_title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        stock_layout.addWidget(stock_title, 0, Qt.AlignRight)

        if data.projections:
            self.stock_table = QTableWidget(len(data.projections), 4)
            self.stock_table.setHorizontalHeaderLabels(
                [
                    "کالا",
                    "موجودی فعلی",
                    "افزایش",
                    "موجودی پس از ثبت",
                ]
            )
            self.stock_table.setAlternatingRowColors(True)
            self.stock_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self.stock_table.setSelectionMode(QAbstractItemView.NoSelection)
            self.stock_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.stock_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.stock_table.setFocusPolicy(Qt.NoFocus)
            self.stock_table.setSizeAdjustPolicy(
                QAbstractScrollArea.AdjustToContents
            )
            self.stock_table.setSizePolicy(
                QSizePolicy.Expanding, QSizePolicy.Minimum
            )
            self.stock_table.horizontalHeader().setStretchLastSection(True)
            self.stock_table.verticalHeader().setDefaultSectionSize(30)
            self.stock_table.setMinimumHeight(160)
            self.stock_table.setLayoutDirection(Qt.RightToLeft)
            self.stock_table.setStyleSheet(
                "QHeaderView::section { text-align: right; padding-right: 6px; }"
            )

            stock_header = self.stock_table.horizontalHeader()
            stock_header.setDefaultAlignment(Qt.AlignRight | Qt.AlignVCenter)
            stock_header.setSectionResizeMode(0, QHeaderView.Stretch)
            stock_header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
            stock_header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
            stock_header.setSectionResizeMode(3, QHeaderView.ResizeToContents)

            for row_idx, projection in enumerate(data.projections):
                self._set_item(
                    self.stock_table, row_idx, 0, projection.product_name
                )
                self._set_item(
                    self.stock_table,
                    row_idx,
                    1,
                    str(projection.current_qty),
                )
                self._set_item(
                    self.stock_table, row_idx, 2, str(projection.added_qty)
                )
                self._set_item(
                    self.stock_table, row_idx, 3, str(projection.new_qty)
                )

            self._fit_table_height(self.stock_table)
            stock_layout.addWidget(self.stock_table)
        else:
            empty_label = QLabel("موردی برای نمایش وجود ندارد.")
            empty_label.setProperty("textRole", "muted")
            empty_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            stock_layout.addWidget(empty_label)

        content_layout.addWidget(stock_card)

        scroll.setWidget(content)
        layout.addWidget(scroll)

        question = QLabel("ثبت این فاکتور؟")
        question.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        question.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(question, 0, Qt.AlignRight)

        button_row = QHBoxLayout()
        button_row.setDirection(QBoxLayout.RightToLeft)

        confirm_button = QPushButton("ثبت فاکتور")
        confirm_button.clicked.connect(self.accept)
        confirm_button.setDefault(True)
        button_row.addWidget(confirm_button)

        cancel_button = QPushButton("انصراف")
        cancel_button.setProperty("variant", "secondary")
        cancel_button.clicked.connect(self.reject)
        button_row.addWidget(cancel_button)

        layout.addLayout(button_row)

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
