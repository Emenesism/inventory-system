from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGraphicsBlurEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.invoice_service import InvoiceService
from app.utils.dates import to_jalali_datetime
from app.utils.text import display_text


class AnalyticsPage(QWidget):
    def __init__(
        self,
        invoice_service: InvoiceService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("AnalyticsPage")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setLayoutDirection(Qt.RightToLeft)
        self.invoice_service = invoice_service

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self._scroll = QScrollArea(self)
        self._scroll.setObjectName("AnalyticsScroll")
        self._scroll.setAttribute(Qt.WA_StyledBackground, True)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        outer_layout.addWidget(self._scroll)
        viewport = self._scroll.viewport()
        if viewport is not None:
            viewport.setObjectName("AnalyticsViewport")
            viewport.setAttribute(Qt.WA_StyledBackground, True)

        self._content = QWidget()
        self._content.setObjectName("AnalyticsContent")
        self._content.setAttribute(Qt.WA_StyledBackground, True)
        self._scroll.setWidget(self._content)

        layout = QVBoxLayout(self._content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel(self.tr("تحلیل‌ها"))
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        header.addWidget(title)
        header.addStretch(1)

        refresh_analytics = QPushButton(self.tr("بروزرسانی"))
        refresh_analytics.clicked.connect(self.load_analytics)
        header.addWidget(refresh_analytics)
        layout.addLayout(header)

        stats_card = QFrame()
        stats_card.setObjectName("Card")
        stats_layout = QHBoxLayout(stats_card)
        stats_layout.setContentsMargins(16, 16, 16, 16)
        stats_layout.setSpacing(24)

        self.sales_qty_label = QLabel(self.tr("تعداد فروش: 0"))
        self.purchase_qty_label = QLabel(self.tr("تعداد خرید: 0"))
        self.net_qty_label = QLabel(self.tr("خالص موجودی: 0"))
        self.sales_invoice_count_label = QLabel(self.tr("فاکتور فروش: 0"))

        stats_layout.addWidget(self.sales_qty_label)
        stats_layout.addWidget(self.purchase_qty_label)
        stats_layout.addWidget(self.net_qty_label)
        stats_layout.addWidget(self.sales_invoice_count_label)
        stats_layout.addStretch(1)
        layout.addWidget(stats_card)

        top_card = QFrame()
        top_card.setObjectName("Card")
        top_layout = QVBoxLayout(top_card)
        top_layout.setContentsMargins(16, 16, 16, 16)
        top_layout.setSpacing(10)

        top_header = QHBoxLayout()
        top_title = QLabel(self.tr("کالاهای پرفروش (بر اساس تعداد)"))
        top_title.setStyleSheet("font-weight: 600;")
        top_header.addWidget(top_title)
        top_header.addStretch(1)
        top_header.addWidget(QLabel(self.tr("بازه:")))
        self.top_days_combo = QComboBox()
        self.top_days_combo.addItem(self.tr("30 روز"), 30)
        self.top_days_combo.addItem(self.tr("60 روز"), 60)
        self.top_days_combo.addItem(self.tr("90 روز"), 90)
        self.top_days_combo.addItem(self.tr("180 روز"), 180)
        self.top_days_combo.addItem(self.tr("365 روز"), 365)
        self.top_days_combo.addItem(self.tr("همه"), 0)
        self.top_days_combo.setCurrentIndex(2)
        self.top_days_combo.currentIndexChanged.connect(self._load_top_products)
        top_header.addWidget(self.top_days_combo)
        top_header.addWidget(QLabel(self.tr("تعداد:")))
        self.top_limit_combo = QComboBox()
        self.top_limit_combo.addItem(self.tr("10 کالا"), 10)
        self.top_limit_combo.addItem(self.tr("20 کالا"), 20)
        self.top_limit_combo.addItem(self.tr("30 کالا"), 30)
        self.top_limit_combo.addItem(self.tr("50 کالا"), 50)
        self.top_limit_combo.addItem(self.tr("100 کالا"), 100)
        self.top_limit_combo.addItem(self.tr("همه"), 200)
        self.top_limit_combo.setCurrentIndex(0)
        self.top_limit_combo.currentIndexChanged.connect(
            self._load_top_products
        )
        top_header.addWidget(self.top_limit_combo)
        top_layout.addLayout(top_header)

        self.top_products_table = QTableWidget(0, 4)
        self.top_products_table.setHorizontalHeaderLabels(
            [
                self.tr("کالا"),
                self.tr("تعداد فروش"),
                self.tr("تعداد فاکتور"),
                self.tr("آخرین فروش"),
            ]
        )
        top_header_view = self.top_products_table.horizontalHeader()
        top_header_view.setSectionResizeMode(0, QHeaderView.Stretch)
        top_header_view.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        top_header_view.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        top_header_view.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.top_products_table.verticalHeader().setDefaultSectionSize(32)
        self.top_products_table.verticalHeader().setVisible(False)
        self.top_products_table.setMinimumHeight(230)
        self.top_products_table.setAlternatingRowColors(True)
        self.top_products_table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        top_layout.addWidget(self.top_products_table)
        layout.addWidget(top_card)

        unsold_card = QFrame()
        unsold_card.setObjectName("Card")
        unsold_layout = QVBoxLayout(unsold_card)
        unsold_layout.setContentsMargins(16, 16, 16, 16)
        unsold_layout.setSpacing(10)

        unsold_header = QHBoxLayout()
        unsold_title = QLabel(self.tr("کالاهای بدون فروش"))
        unsold_title.setStyleSheet("font-weight: 600;")
        unsold_header.addWidget(unsold_title)
        unsold_header.addStretch(1)
        unsold_header.addWidget(QLabel(self.tr("بازه:")))
        self.unsold_days_combo = QComboBox()
        self.unsold_days_combo.addItem(self.tr("30 روز"), 30)
        self.unsold_days_combo.addItem(self.tr("60 روز"), 60)
        self.unsold_days_combo.addItem(self.tr("90 روز"), 90)
        self.unsold_days_combo.addItem(self.tr("180 روز"), 180)
        self.unsold_days_combo.addItem(self.tr("365 روز"), 365)
        self.unsold_days_combo.addItem(self.tr("همه"), 0)
        self.unsold_days_combo.setCurrentIndex(2)
        self.unsold_days_combo.currentIndexChanged.connect(
            self._load_unsold_products
        )
        unsold_header.addWidget(self.unsold_days_combo)
        unsold_layout.addLayout(unsold_header)

        self.unsold_table = QTableWidget(0, 4)
        self.unsold_table.setHorizontalHeaderLabels(
            [
                self.tr("کالا"),
                self.tr("موجودی"),
                self.tr("آخرین بروزرسانی"),
                self.tr("منبع"),
            ]
        )
        unsold_header_view = self.unsold_table.horizontalHeader()
        unsold_header_view.setSectionResizeMode(0, QHeaderView.Stretch)
        unsold_header_view.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        unsold_header_view.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        unsold_header_view.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.unsold_table.verticalHeader().setDefaultSectionSize(32)
        self.unsold_table.verticalHeader().setVisible(False)
        self.unsold_table.setMinimumHeight(250)
        self.unsold_table.setAlternatingRowColors(True)
        self.unsold_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        unsold_layout.addWidget(self.unsold_table)
        layout.addWidget(unsold_card)

        self._overlay = QFrame(self)
        self._overlay.setStyleSheet(
            "background: rgba(15, 23, 42, 0.55); border-radius: 16px;"
        )
        overlay_layout = QVBoxLayout(self._overlay)
        overlay_layout.setContentsMargins(0, 0, 0, 0)
        overlay_layout.addStretch(1)
        self._overlay.hide()

        self.load_analytics()
        self.set_accessible(True)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._overlay.setGeometry(self.rect())

    def set_accessible(self, accessible: bool) -> None:
        if accessible:
            self._content.setGraphicsEffect(None)
            self._content.setEnabled(True)
            self._overlay.hide()
            return
        blur = QGraphicsBlurEffect(self)
        blur.setBlurRadius(12)
        self._content.setGraphicsEffect(blur)
        self._content.setEnabled(False)
        self._overlay.show()
        self._overlay.raise_()

    def load_analytics(self) -> None:
        self._load_summary_stats()
        self._load_top_products()
        self._load_unsold_products()

    def _load_summary_stats(self) -> None:
        try:
            summary = self.invoice_service.get_monthly_quantity_summary()
        except Exception:  # noqa: BLE001
            summary = []
        total_sales = sum(
            self._safe_int(item.get("sales_qty")) for item in summary
        )
        total_purchases = sum(
            self._safe_int(item.get("purchase_qty")) for item in summary
        )
        total_net = total_purchases - total_sales
        total_sales_invoices = sum(
            self._safe_int(item.get("sales_invoices")) for item in summary
        )

        self.sales_qty_label.setText(
            self.tr("تعداد فروش: {count}").format(count=f"{total_sales:,}")
        )
        self.purchase_qty_label.setText(
            self.tr("تعداد خرید: {count}").format(count=f"{total_purchases:,}")
        )
        self.net_qty_label.setText(
            self.tr("خالص موجودی: {count}").format(count=f"{total_net:,}")
        )
        self.sales_invoice_count_label.setText(
            self.tr("فاکتور فروش: {count}").format(
                count=f"{total_sales_invoices:,}"
            )
        )

    def _load_top_products(self) -> None:
        days = int(self.top_days_combo.currentData() or 0)
        limit = int(self.top_limit_combo.currentData() or 10)
        try:
            items = self.invoice_service.get_top_sold_products(
                days=days, limit=limit
            )
        except Exception:  # noqa: BLE001
            items = []

        self.top_products_table.setRowCount(len(items))
        for row_idx, item in enumerate(items):
            product_item = QTableWidgetItem(
                display_text(item.get("product_name", ""), fallback="")
            )
            product_item.setTextAlignment(
                Qt.AlignVCenter | Qt.AlignRight | Qt.AlignAbsolute
            )
            self.top_products_table.setItem(row_idx, 0, product_item)

            qty_item = QTableWidgetItem(
                f"{self._safe_int(item.get('sold_qty')):,}"
            )
            qty_item.setTextAlignment(Qt.AlignCenter)
            self.top_products_table.setItem(row_idx, 1, qty_item)

            invoice_count_item = QTableWidgetItem(
                f"{self._safe_int(item.get('invoice_count')):,}"
            )
            invoice_count_item.setTextAlignment(Qt.AlignCenter)
            self.top_products_table.setItem(row_idx, 2, invoice_count_item)

            last_sold_raw = str(item.get("last_sold_at", "") or "").strip()
            last_sold_text = (
                to_jalali_datetime(last_sold_raw) if last_sold_raw else "-"
            )
            last_sold_item = QTableWidgetItem(last_sold_text)
            last_sold_item.setTextAlignment(Qt.AlignCenter)
            self.top_products_table.setItem(row_idx, 3, last_sold_item)

    def _load_unsold_products(self) -> None:
        days = int(self.unsold_days_combo.currentData() or 30)
        try:
            items = self.invoice_service.get_unsold_products(
                days=days, limit=200
            )
        except Exception:  # noqa: BLE001
            items = []

        self.unsold_table.setRowCount(len(items))
        for row_idx, item in enumerate(items):
            product_item = QTableWidgetItem(
                display_text(item.get("product_name", ""), fallback="")
            )
            product_item.setTextAlignment(
                Qt.AlignVCenter | Qt.AlignRight | Qt.AlignAbsolute
            )
            self.unsold_table.setItem(row_idx, 0, product_item)

            quantity_item = QTableWidgetItem(
                f"{self._safe_int(item.get('quantity')):,}"
            )
            quantity_item.setTextAlignment(Qt.AlignCenter)
            self.unsold_table.setItem(row_idx, 1, quantity_item)

            updated_raw = str(item.get("updated_at", "") or "").strip()
            updated_item = QTableWidgetItem(
                to_jalali_datetime(updated_raw) if updated_raw else "-"
            )
            updated_item.setTextAlignment(Qt.AlignCenter)
            self.unsold_table.setItem(row_idx, 2, updated_item)

            source_item = QTableWidgetItem(
                display_text(item.get("source", ""), fallback="-")
            )
            source_item.setTextAlignment(Qt.AlignCenter)
            self.unsold_table.setItem(row_idx, 3, source_item)

    @staticmethod
    def _safe_int(value: object) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0
