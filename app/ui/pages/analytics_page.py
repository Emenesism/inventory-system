from __future__ import annotations

from PySide6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QValueAxis,
)
from PySide6.QtCore import QMargins, Qt
from PySide6.QtGui import QColor, QPainter
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
from app.utils.dates import to_jalali_datetime, to_jalali_month


class AnalyticsPage(QWidget):
    def __init__(
        self,
        invoice_service: InvoiceService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setLayoutDirection(Qt.RightToLeft)
        self.invoice_service = invoice_service

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        outer_layout.addWidget(self._scroll)

        self._content = QWidget()
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

        chart_card = QFrame()
        chart_card.setObjectName("Card")
        chart_layout = QVBoxLayout(chart_card)
        chart_layout.setContentsMargins(16, 16, 16, 16)
        chart_layout.setSpacing(10)
        chart_title = QLabel(self.tr("روند ماهانه (تعداد)"))
        chart_title.setStyleSheet("font-weight: 600;")
        chart_layout.addWidget(chart_title)

        self.monthly_chart = QChart()
        self.monthly_chart.setBackgroundVisible(False)
        self.monthly_chart.setMargins(QMargins(8, 8, 8, 8))
        self.monthly_chart.legend().setVisible(True)
        self.monthly_chart.legend().setAlignment(Qt.AlignBottom)
        self.chart_view = QChartView(self.monthly_chart)
        self.chart_view.setRenderHint(QPainter.Antialiasing, True)
        self.chart_view.setMinimumHeight(320)
        chart_layout.addWidget(self.chart_view)
        layout.addWidget(chart_card)

        summary_card = QFrame()
        summary_card.setObjectName("Card")
        summary_layout = QVBoxLayout(summary_card)
        summary_layout.setContentsMargins(16, 16, 16, 16)
        summary_layout.setSpacing(10)
        summary_title = QLabel(self.tr("جزئیات ماهانه"))
        summary_title.setStyleSheet("font-weight: 600;")
        summary_layout.addWidget(summary_title)

        self.monthly_table = QTableWidget(0, 6)
        self.monthly_table.setHorizontalHeaderLabels(
            [
                self.tr("ماه"),
                self.tr("فروش"),
                self.tr("خرید"),
                self.tr("خالص"),
                self.tr("فاکتور فروش"),
                self.tr("فاکتور خرید"),
            ]
        )
        header_view = self.monthly_table.horizontalHeader()
        for section in range(6):
            header_view.setSectionResizeMode(section, QHeaderView.Stretch)
        self.monthly_table.verticalHeader().setDefaultSectionSize(32)
        self.monthly_table.setMinimumHeight(120)
        self.monthly_table.setAlternatingRowColors(True)
        self.monthly_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        summary_layout.addWidget(self.monthly_table)
        layout.addWidget(summary_card)

        top_card = QFrame()
        top_card.setObjectName("Card")
        top_layout = QVBoxLayout(top_card)
        top_layout.setContentsMargins(16, 16, 16, 16)
        top_layout.setSpacing(10)

        top_header = QHBoxLayout()
        top_title = QLabel(self.tr("۱۰ کالای پرفروش (بر اساس تعداد)"))
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
        self.unsold_days_combo.setCurrentIndex(0)
        self.unsold_days_combo.currentIndexChanged.connect(
            self._load_unsold_products
        )
        unsold_header.addWidget(self.unsold_days_combo)
        unsold_layout.addLayout(unsold_header)

        self.unsold_counts_label = QLabel(
            self.tr("30 روز: 0 | 60 روز: 0 | 90 روز: 0")
        )
        self.unsold_counts_label.setProperty("textRole", "muted")
        unsold_layout.addWidget(self.unsold_counts_label)

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
        self._load_monthly_quantities()
        self._load_top_products()
        self._load_unsold_products()

    def _load_monthly_quantities(self) -> None:
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

        self._populate_monthly_table(summary)
        self._populate_monthly_chart(summary)

    def _populate_monthly_table(
        self, summary: list[dict[str, int | str]]
    ) -> None:
        self.monthly_table.setRowCount(len(summary))
        for row_idx, item in enumerate(summary):
            month_item = QTableWidgetItem(
                to_jalali_month(str(item.get("month", "")))
            )
            month_item.setTextAlignment(Qt.AlignCenter)
            self.monthly_table.setItem(row_idx, 0, month_item)

            sales_item = QTableWidgetItem(
                f"{self._safe_int(item.get('sales_qty')):,}"
            )
            sales_item.setTextAlignment(Qt.AlignCenter)
            self.monthly_table.setItem(row_idx, 1, sales_item)

            purchase_item = QTableWidgetItem(
                f"{self._safe_int(item.get('purchase_qty')):,}"
            )
            purchase_item.setTextAlignment(Qt.AlignCenter)
            self.monthly_table.setItem(row_idx, 2, purchase_item)

            net_item = QTableWidgetItem(
                f"{self._safe_int(item.get('net_qty')):,}"
            )
            net_item.setTextAlignment(Qt.AlignCenter)
            self.monthly_table.setItem(row_idx, 3, net_item)

            sales_inv_item = QTableWidgetItem(
                f"{self._safe_int(item.get('sales_invoices')):,}"
            )
            sales_inv_item.setTextAlignment(Qt.AlignCenter)
            self.monthly_table.setItem(row_idx, 4, sales_inv_item)

            purchase_inv_item = QTableWidgetItem(
                f"{self._safe_int(item.get('purchase_invoices')):,}"
            )
            purchase_inv_item.setTextAlignment(Qt.AlignCenter)
            self.monthly_table.setItem(row_idx, 5, purchase_inv_item)

    def _populate_monthly_chart(
        self, summary: list[dict[str, int | str]]
    ) -> None:
        chart = QChart()
        chart.setBackgroundVisible(False)
        chart.setMargins(QMargins(8, 8, 8, 8))
        chart.legend().setAlignment(Qt.AlignBottom)
        chart.setAnimationOptions(QChart.SeriesAnimations)

        if not summary:
            self.chart_view.setChart(chart)
            return

        ordered = list(reversed(summary))
        labels = [
            to_jalali_month(str(item.get("month", ""))) for item in ordered
        ]

        purchase_set = QBarSet(self.tr("خرید"))
        purchase_set.setColor(QColor("#16A34A"))
        sales_set = QBarSet(self.tr("فروش"))
        sales_set.setColor(QColor("#2563EB"))
        net_set = QBarSet(self.tr("خالص"))
        net_set.setColor(QColor("#D97706"))

        min_value = 0.0
        max_value = 1.0
        for item in ordered:
            purchase_qty = float(self._safe_int(item.get("purchase_qty")))
            sales_qty = float(self._safe_int(item.get("sales_qty")))
            net_qty = float(self._safe_int(item.get("net_qty")))
            purchase_set.append(purchase_qty)
            sales_set.append(sales_qty)
            net_set.append(net_qty)
            min_value = min(min_value, purchase_qty, sales_qty, net_qty)
            max_value = max(max_value, purchase_qty, sales_qty, net_qty)

        series = QBarSeries()
        series.setBarWidth(0.7)
        series.append(purchase_set)
        series.append(sales_set)
        series.append(net_set)
        chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append(labels)
        axis_y = QValueAxis()
        axis_y.setLabelFormat("%d")
        if min_value == max_value:
            if max_value <= 0:
                min_value -= 1
                max_value = 1
            else:
                min_value = 0
                max_value += 1
        if min_value >= 0:
            axis_y.setRange(0, max_value * 1.1)
        else:
            span = max_value - min_value
            padding = span * 0.1 if span > 0 else 1
            axis_y.setRange(min_value - padding, max_value + padding)
        axis_y.applyNiceNumbers()
        chart.addAxis(axis_x, Qt.AlignBottom)
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_x)
        series.attachAxis(axis_y)

        self.chart_view.setChart(chart)

    def _load_top_products(self) -> None:
        days = int(self.top_days_combo.currentData() or 0)
        try:
            items = self.invoice_service.get_top_sold_products(
                days=days, limit=10
            )
        except Exception:  # noqa: BLE001
            items = []

        self.top_products_table.setRowCount(len(items))
        for row_idx, item in enumerate(items):
            product_item = QTableWidgetItem(str(item.get("product_name", "")))
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
        # Show 30/60/90-day unsold counts together for quick comparison.
        counts: dict[int, int] = {}
        for period in (30, 60, 90):
            try:
                rows = self.invoice_service.get_unsold_products(
                    days=period, limit=5000
                )
            except Exception:  # noqa: BLE001
                rows = []
            counts[period] = len(rows)
        self.unsold_counts_label.setText(
            self.tr("30 روز: {c30} | 60 روز: {c60} | 90 روز: {c90}").format(
                c30=f"{counts.get(30, 0):,}",
                c60=f"{counts.get(60, 0):,}",
                c90=f"{counts.get(90, 0):,}",
            )
        )

        days = int(self.unsold_days_combo.currentData() or 30)
        try:
            items = self.invoice_service.get_unsold_products(
                days=days, limit=200
            )
        except Exception:  # noqa: BLE001
            items = []

        self.unsold_table.setRowCount(len(items))
        for row_idx, item in enumerate(items):
            product_item = QTableWidgetItem(str(item.get("product_name", "")))
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

            source_item = QTableWidgetItem(str(item.get("source", "") or "-"))
            source_item.setTextAlignment(Qt.AlignCenter)
            self.unsold_table.setItem(row_idx, 3, source_item)

    @staticmethod
    def _safe_int(value: object) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0
