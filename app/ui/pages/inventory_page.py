from __future__ import annotations

import pandas as pd
from PySide6.QtCore import QModelIndex, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app.utils import dialogs
from app.utils.search import NormalizedFilterProxyModel
from app.utils.table_models import DataFrameTableModel
from app.utils.text import normalize_text


class InventoryPage(QWidget):
    reload_requested = Signal()
    save_requested = Signal()
    export_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model: DataFrameTableModel | None = None
        self._proxy: NormalizedFilterProxyModel | None = None
        self._column_names: list[str] = []
        self._column_widths: dict[str, int] = {}
        self._editable_columns: list[str] | None = None
        self._blocked_columns: set[str] | None = None
        self._name_changes: dict[str, str] = {}
        self._name_originals: dict[str, str] = {}
        self._lazy_enabled_default = True
        self._pending_filter = ""
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self._apply_filter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel(self.tr("نمای کلی موجودی"))
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        header.addWidget(title)
        header.addStretch(1)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(self.tr("جستجوی کالا..."))
        self.search_input.setMinimumWidth(260)
        self.search_input.textChanged.connect(self._queue_filter)
        header.addWidget(self.search_input)

        self.reload_button = QPushButton(self.tr("بارگذاری مجدد"))
        self.reload_button.clicked.connect(self.reload_requested.emit)
        header.addWidget(self.reload_button)

        self.save_button = QPushButton(self.tr("ذخیره تغییرات"))
        self.save_button.clicked.connect(self.save_requested.emit)
        header.addWidget(self.save_button)

        self.add_row_button = QPushButton(self.tr("افزودن ردیف"))
        self.add_row_button.clicked.connect(self.add_row)
        header.addWidget(self.add_row_button)

        self.delete_row_button = QPushButton(self.tr("حذف انتخاب‌شده"))
        self.delete_row_button.setStyleSheet(
            "QPushButton { background: #DC2626; }"
            "QPushButton:hover { background: #B91C1C; }"
            "QPushButton:disabled { background: #9CA3AF; }"
        )
        self.delete_row_button.clicked.connect(self.delete_selected_rows)
        self.delete_row_button.setEnabled(False)
        header.addWidget(self.delete_row_button)

        self.export_button = QPushButton(self.tr("خروجی"))
        self.export_button.clicked.connect(self.export_requested.emit)
        header.addWidget(self.export_button)

        layout.addLayout(header)

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)

        self.table = QTableView()
        self.table.setSortingEnabled(False)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setAlternatingRowColors(True)
        if hasattr(self.table, "setUniformRowHeights"):
            self.table.setUniformRowHeights(True)
        self.table.verticalHeader().setDefaultSectionSize(40)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionsClickable(False)
        header.sectionResized.connect(self._remember_column_width)
        self.table.setEditTriggers(QAbstractItemView.AllEditTriggers)
        self.table.verticalScrollBar().valueChanged.connect(
            self._maybe_fetch_more
        )
        card_layout.addWidget(self.table)

        layout.addWidget(card)

    def set_inventory(
        self,
        dataframe,
        editable_columns: list[str] | None = None,
        blocked_columns: list[str] | None = None,
    ) -> None:  # noqa: ANN001
        if dataframe is None:
            return
        dataframe = self._sort_dataframe_by_product_name(dataframe)
        self._name_changes = {}
        self._name_originals = {}
        row_count = len(dataframe)
        if editable_columns is not None:
            self._editable_columns = editable_columns
            self._blocked_columns = None
        if blocked_columns is not None:
            self._blocked_columns = set(blocked_columns)
            self._editable_columns = None
        self._column_names = [str(name) for name in dataframe.columns]
        filter_text = self.search_input.text()
        active_editable = self._editable_columns
        if active_editable is None and self._blocked_columns:
            active_editable = [
                col
                for col in dataframe.columns
                if col not in self._blocked_columns
            ]
        lazy_enabled = row_count > 500
        self._lazy_enabled_default = lazy_enabled
        chunk_size = 200 if row_count <= 2000 else 500
        header_labels = {
            str(column): self._localized_header_label(str(column))
            for column in dataframe.columns
        }
        self._model = DataFrameTableModel(
            dataframe,
            editable_columns=active_editable,
            header_labels=header_labels,
            lazy_load=lazy_enabled,
            chunk_size=chunk_size,
        )
        self._model.cell_edited.connect(self._handle_cell_edit)
        self._proxy = NormalizedFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.setDynamicSortFilter(True)
        self._proxy.setSortCaseSensitivity(Qt.CaseInsensitive)
        self._proxy.setSortLocaleAware(True)
        self.table.setModel(self._proxy)
        self._wire_selection_model()
        if filter_text:
            self._model.set_lazy_loading(False)
            self._proxy.set_filter_text(filter_text)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionsClickable(False)
        product_col = self._product_column_index()
        for col in range(self._model.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.Interactive)
        for col in range(self._model.columnCount()):
            column_name = self._column_names[col]
            saved_width = self._column_widths.get(column_name)
            if saved_width and saved_width > 24:
                header.resizeSection(col, int(saved_width))
                continue
            header.resizeSection(col, self._default_column_width(column_name))
        if product_col is not None:
            self._proxy.sort(product_col, Qt.AscendingOrder)

    def get_dataframe(self):  # noqa: ANN001
        if not self._model:
            return None
        return self._sort_dataframe_by_product_name(self._model.dataframe())

    def get_name_changes(self) -> list[tuple[str, str]]:
        changes: list[tuple[str, str]] = []
        for key, new_name in self._name_changes.items():
            old_name = self._name_originals.get(key, "")
            if not old_name or not new_name:
                continue
            if normalize_text(old_name) == normalize_text(new_name):
                continue
            changes.append((old_name, new_name))
        return changes

    def clear_name_changes(self) -> None:
        self._name_changes = {}
        self._name_originals = {}

    def set_editable_columns(self, editable_columns: list[str] | None) -> None:
        self._editable_columns = editable_columns
        self._blocked_columns = None
        if not self._model:
            return
        current_df = self._model.dataframe()
        self.set_inventory(current_df, editable_columns=editable_columns)

    def set_blocked_columns(self, blocked_columns: list[str] | None) -> None:
        self._blocked_columns = (
            set(blocked_columns) if blocked_columns else None
        )
        self._editable_columns = None
        if not self._model:
            return
        current_df = self._model.dataframe()
        self.set_inventory(current_df, blocked_columns=blocked_columns)

    def set_enabled_state(self, enabled: bool) -> None:
        self.search_input.setEnabled(enabled)
        self.reload_button.setEnabled(enabled)
        self.save_button.setEnabled(enabled)
        self.add_row_button.setEnabled(enabled)
        self.delete_row_button.setEnabled(enabled and self._has_selection())
        self.export_button.setEnabled(enabled)
        self.table.setEnabled(enabled)

    def add_row(self) -> None:
        if not self._model:
            return
        df = self._model.dataframe()
        new_row: dict[str, object] = {}
        for col in df.columns:
            if col == "product_name":
                new_row[col] = ""
            elif col in {"quantity"}:
                new_row[col] = 0
            elif col in {"avg_buy_price", "last_buy_price", "sell_price"}:
                new_row[col] = 0.0
            else:
                new_row[col] = ""

        lazy_enabled = self._model.rowCount() < len(df)
        if lazy_enabled:
            df = pd.concat([pd.DataFrame([new_row]), df], ignore_index=True)
            target_row = 0
        else:
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            target_row = len(df) - 1

        self._model.set_dataframe(df)
        if self._proxy is None:
            return

        def focus_row() -> bool:
            source_index = self._model.index(target_row, 0)
            proxy_index = self._proxy.mapFromSource(source_index)
            if not proxy_index.isValid():
                return False
            self.table.scrollTo(proxy_index)
            self.table.setCurrentIndex(proxy_index)
            self.table.edit(proxy_index)
            return True

        if not focus_row():
            self.search_input.clear()
            self._apply_filter()
            focus_row()

    def delete_selected_rows(self) -> None:
        if not self._model or not self._proxy:
            return
        selected_rows = sorted(
            {
                self._proxy.mapToSource(index).row()
                for index in self.table.selectedIndexes()
                if index.isValid()
            },
            reverse=True,
        )
        selected_rows = [row for row in selected_rows if row >= 0]
        if not selected_rows:
            return
        if not dialogs.ask_yes_no(
            self,
            self.tr("حذف ردیف‌ها"),
            self.tr("آیا {count} ردیف انتخاب‌شده حذف شود؟").format(
                count=len(selected_rows)
            ),
        ):
            return

        df = self._model.dataframe()
        df = df.drop(df.index[selected_rows]).reset_index(drop=True)
        self._model.set_dataframe(df)
        self._update_delete_button()

    def _has_selection(self) -> bool:
        return bool(self.table.selectedIndexes())

    def _update_delete_button(self) -> None:
        enabled = self.table.isEnabled() and self._has_selection()
        self.delete_row_button.setEnabled(enabled)

    def _handle_cell_edit(
        self,
        row: int,
        column_name: str,
        old_value,
        new_value,
    ) -> None:
        if column_name != "product_name":
            return
        old_name = str(old_value or "").strip()
        new_name = str(new_value or "").strip()
        if not old_name or not new_name:
            return
        if normalize_text(old_name) == normalize_text(new_name):
            return

        old_key = normalize_text(old_name)
        if old_key in self._name_changes:
            self._name_changes[old_key] = new_name
            if old_key not in self._name_originals:
                self._name_originals[old_key] = old_name
            return

        for key, current_new in list(self._name_changes.items()):
            if normalize_text(current_new) == old_key:
                self._name_changes[key] = new_name
                return

        self._name_changes[old_key] = new_name
        self._name_originals[old_key] = old_name

    def _wire_selection_model(self) -> None:
        selection_model = self.table.selectionModel()
        if selection_model is None:
            return
        selection_model.selectionChanged.connect(
            lambda *_: self._update_delete_button()
        )
        self._update_delete_button()

    def _queue_filter(self, text: str) -> None:
        self._pending_filter = text
        self._search_timer.start()

    def _apply_filter(self) -> None:
        if self._proxy and self._model:
            text = self._pending_filter
            if text:
                self._model.set_lazy_loading(False)
            else:
                self._model.set_lazy_loading(self._lazy_enabled_default)
            self._proxy.set_filter_text(text)

    def _maybe_fetch_more(self) -> None:
        if not self._proxy:
            return
        bar = self.table.verticalScrollBar()
        if bar.maximum() == 0:
            return
        if bar.value() >= bar.maximum() - 24:
            if self._proxy.canFetchMore(QModelIndex()):
                self._proxy.fetchMore(QModelIndex())

    def _remember_column_width(
        self, logical_index: int, _old_size: int, new_size: int
    ) -> None:
        if (
            logical_index < 0
            or logical_index >= len(self._column_names)
            or new_size <= 0
        ):
            return
        self._column_widths[self._column_names[logical_index]] = int(new_size)

    @staticmethod
    def _default_column_width(column_name: str) -> int:
        normalized = InventoryPage._normalize_column_name(column_name)
        if normalized in {"product_name", "نام_کالا", "کالا"}:
            return 360
        if normalized in {"source", "منبع"}:
            return 180
        return 140

    def _localized_header_label(self, column_name: str) -> str:
        normalized = self._normalize_column_name(column_name)
        mapping = {
            "product_name": self.tr("نام کالا"),
            "quantity": self.tr("تعداد"),
            "avg_buy_price": self.tr("میانگین قیمت خرید"),
            "last_buy_price": self.tr("آخرین قیمت خرید"),
            "sell_price": self.tr("قیمت فروش"),
            "alarm": self.tr("آلارم"),
            "source": self.tr("منبع"),
        }
        return mapping.get(normalized, str(column_name))

    def _product_column_index(self) -> int | None:
        for idx, column_name in enumerate(self._column_names):
            if self._is_product_column_name(column_name):
                return idx
        return None

    @staticmethod
    def _normalize_column_name(column_name: object) -> str:
        return (
            str(column_name).strip().lower().replace("-", "_").replace(" ", "_")
        )

    @classmethod
    def _is_product_column_name(cls, column_name: object) -> bool:
        normalized = cls._normalize_column_name(column_name)
        if normalized in {
            "product_name",
            "product",
            "name",
            "نام_محصول",
            "نام_کالا",
            "کالا",
            "محصول",
        }:
            return True
        return "product" in normalized and "name" in normalized

    @classmethod
    def _product_column_name(cls, columns: list[object]) -> str | None:
        for column_name in columns:
            if cls._is_product_column_name(column_name):
                return str(column_name)
        return None

    @classmethod
    def _sort_dataframe_by_product_name(
        cls, dataframe: pd.DataFrame
    ) -> pd.DataFrame:
        sorted_df = dataframe.copy()
        product_column = cls._product_column_name(list(sorted_df.columns))
        if not product_column or sorted_df.empty:
            return sorted_df.reset_index(drop=True)
        sort_key = (
            sorted_df[product_column].fillna("").astype(str).map(normalize_text)
        )
        return (
            sorted_df.assign(_name_sort=sort_key)
            .sort_values(by=["_name_sort"], kind="mergesort")
            .drop(columns=["_name_sort"])
            .reset_index(drop=True)
        )
