from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QEventLoop, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.config import AppConfig
from app.models.errors import InventoryFileError
from app.services.action_log_service import ActionLogService
from app.services.inventory_service import InventoryService
from app.utils.excel import autofit_columns, ensure_sheet_rtl
from app.utils.numeric import format_amount


def _t(text: str) -> str:
    return QCoreApplication.translate("LowStockPage", text)


COL_PRODUCT = _t("نام کالا")
COL_QUANTITY = _t("تعداد")
COL_ALARM = _t("حد هشدار")
COL_NEEDED = _t("نیاز")
COL_AVG_BUY = _t("میانگین خرید")
COL_SOURCE = _t("منبع")


class LowStockPage(QWidget):
    def __init__(
        self,
        inventory_service: InventoryService,
        config: AppConfig,
        action_log_service: ActionLogService | None = None,
        current_admin_provider=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.inventory_service = inventory_service
        self.config = config
        self.action_log_service = action_log_service
        self._current_admin_provider = current_admin_provider
        self._rows: list[dict[str, object]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel(self.tr("هشدار کمبود موجودی"))
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        header.addWidget(title)
        header.addStretch(1)

        export_button = QPushButton(self.tr("خروجی"))
        export_button.clicked.connect(self._export)
        header.addWidget(export_button)

        refresh_button = QPushButton(self.tr("بروزرسانی"))
        refresh_button.clicked.connect(self.refresh)
        header.addWidget(refresh_button)
        layout.addLayout(header)

        summary_card = QFrame()
        summary_card.setObjectName("Card")
        summary_layout = QHBoxLayout(summary_card)
        summary_layout.setContentsMargins(16, 16, 16, 16)
        summary_layout.setSpacing(24)

        self.items_label = QLabel(self.tr("کالاهای زیر حد هشدار: 0"))
        self.total_needed_label = QLabel(self.tr("مجموع نیاز: 0"))
        summary_layout.addWidget(self.items_label)
        summary_layout.addWidget(self.total_needed_label)
        summary_layout.addStretch(1)
        layout.addWidget(summary_card)

        table_card = QFrame()
        table_card.setObjectName("Card")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(16, 16, 16, 16)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            [
                self.tr("کالا"),
                self.tr("تعداد"),
                self.tr("هشدار"),
                self.tr("نیاز"),
                self.tr("میانگین خرید"),
                self.tr("منبع"),
            ]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, self.table.columnCount()):
            header_view.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setDefaultSectionSize(32)
        table_layout.addWidget(self.table)
        layout.addWidget(table_card)

    def set_enabled_state(self, enabled: bool) -> None:
        self.table.setEnabled(enabled)

    def refresh(self) -> None:
        if not self.inventory_service.is_loaded():
            self.table.setRowCount(0)
            self.items_label.setText(self.tr("کالاهای زیر حد هشدار: 0"))
            self.total_needed_label.setText(self.tr("مجموع نیاز: 0"))
            return

        rows: list[dict[str, object]] = []
        try:
            low_stock_rows = self.inventory_service.get_low_stock_rows(
                self.config.low_stock_threshold
            )
        except InventoryFileError:
            low_stock_rows = []
        for row in low_stock_rows:
            source_value = row.get("source", "")
            source_text = "" if source_value is None else str(source_value)
            if source_text.lower() == "nan":
                source_text = ""
            rows.append(
                {
                    "product": str(row.get("product_name", "")).strip(),
                    "quantity": int(row.get("quantity", 0) or 0),
                    "alarm": int(row.get("alarm", 0) or 0),
                    "needed": int(row.get("needed", 0) or 0),
                    "avg_buy": float(row.get("avg_buy_price", 0.0) or 0.0),
                    "source": source_text.strip(),
                }
            )

        self._rows = rows
        self.items_label.setText(
            self.tr("کالاهای زیر حد هشدار: {count}").format(count=len(rows))
        )
        self.total_needed_label.setText(
            self.tr("مجموع نیاز: {count}").format(
                count=sum(item["needed"] for item in rows)
            )
        )

        sorting_enabled = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)

        self.table.setRowCount(len(rows))
        for row_idx, item in enumerate(rows):
            product_item = QTableWidgetItem(item["product"])
            self.table.setItem(row_idx, 0, product_item)

            qty_item = QTableWidgetItem(str(item["quantity"]))
            qty_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_idx, 1, qty_item)

            min_item = QTableWidgetItem(str(item["alarm"]))
            min_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_idx, 2, min_item)

            needed_item = QTableWidgetItem(str(item["needed"]))
            needed_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_idx, 3, needed_item)

            avg_item = QTableWidgetItem(self._format_amount(item["avg_buy"]))
            avg_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_idx, 4, avg_item)

            source_item = QTableWidgetItem(item["source"])
            self.table.setItem(row_idx, 5, source_item)

            self._apply_severity_color(
                [
                    product_item,
                    qty_item,
                    min_item,
                    needed_item,
                    avg_item,
                    source_item,
                ],
                int(item["quantity"]),
                int(item["alarm"]),
            )

            if row_idx % 200 == 0:
                QApplication.processEvents(QEventLoop.ExcludeUserInputEvents)

        self.table.blockSignals(False)
        self.table.setUpdatesEnabled(True)
        self.table.setSortingEnabled(sorting_enabled)

    def _export(self) -> None:
        if not self._rows:
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("خروجی لیست کمبود موجودی"),
            "low_stock.xlsx",
            self.tr("فایل‌های اکسل (*.xlsx);;فایل‌های CSV (*.csv)"),
        )
        if not file_path:
            return

        import pandas as pd

        df = pd.DataFrame(self._rows)
        df = df.rename(
            columns={
                "product": COL_PRODUCT,
                "quantity": COL_QUANTITY,
                "alarm": COL_ALARM,
                "needed": COL_NEEDED,
                "avg_buy": COL_AVG_BUY,
                "source": COL_SOURCE,
            }
        )
        if file_path.lower().endswith(".csv"):
            df.to_csv(file_path, index=False)
        else:
            df.to_excel(file_path, index=False)
            self._apply_export_colors(file_path, df)
            ensure_sheet_rtl(file_path)
            autofit_columns(file_path)
        if self.action_log_service:
            admin = (
                self._current_admin_provider()
                if self._current_admin_provider
                else None
            )
            self.action_log_service.log_action(
                "low_stock_export",
                self.tr("خروجی کمبود موجودی"),
                self.tr("تعداد ردیف‌ها: {count}\nمسیر: {path}").format(
                    count=len(df), path=file_path
                ),
                admin=admin,
            )

    @staticmethod
    def _format_amount(value: float) -> str:
        return format_amount(value)

    def _apply_export_colors(self, file_path: str, df) -> None:
        try:
            from openpyxl import load_workbook
            from openpyxl.styles import PatternFill
        except ImportError:
            return

        max_needed = 0
        if COL_NEEDED not in df.columns:
            return
        for value in df[COL_NEEDED].tolist():
            try:
                max_needed = max(max_needed, int(value))
            except (TypeError, ValueError):
                continue
        if max_needed <= 0:
            return

        wb = load_workbook(file_path)
        ws = wb.active
        ws.sheet_view.rightToLeft = True
        needed_col = list(df.columns).index(COL_NEEDED) + 1
        start_row = 2
        end_row = start_row + len(df) - 1

        for row_idx in range(start_row, end_row + 1):
            needed_value = ws.cell(row_idx, needed_col).value
            try:
                needed = int(needed_value)
            except (TypeError, ValueError):
                continue
            severity = min(max(needed / max_needed, 0.0), 1.0)
            green = int(235 - (140 * severity))
            red = int(255 - (15 * (1 - severity)))
            fill = PatternFill(
                start_color=f"{red:02X}{green:02X}66",
                end_color=f"{red:02X}{green:02X}66",
                fill_type="solid",
            )
            for col_idx in range(1, ws.max_column + 1):
                ws.cell(row_idx, col_idx).fill = fill

        wb.save(file_path)

    def _apply_severity_color(
        self, items: list[QTableWidgetItem], qty: int, alarm: int
    ) -> None:
        if alarm <= 0:
            return
        deficit = max(alarm - qty, 0)
        severity = min(deficit / alarm, 1.0)
        if severity <= 0:
            return
        # Blend from light warning to strong red based on severity.
        low = (255, 244, 228)
        high = (255, 153, 153)
        red = int(low[0] + (high[0] - low[0]) * severity)
        green = int(low[1] + (high[1] - low[1]) * severity)
        blue = int(low[2] + (high[2] - low[2]) * severity)
        brush = QBrush(QColor(red, green, blue))
        for item in items:
            item.setBackground(brush)
