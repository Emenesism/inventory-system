from __future__ import annotations

import shutil

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
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

from app.services.inventory_service import InventoryService
from app.services.invoice_service import InvoiceService, InvoiceSummary
from app.ui.widgets.invoice_edit_dialog import InvoiceEditDialog
from app.ui.widgets.toast import ToastManager
from app.utils import dialogs
from app.utils.dates import to_jalali_datetime
from app.utils.excel import export_invoice_excel
from app.utils.numeric import format_amount
from app.utils.text import normalize_text


class InvoicesPage(QWidget):
    def __init__(
        self,
        invoice_service: InvoiceService,
        inventory_service: InventoryService,
        toast: ToastManager | None = None,
        on_inventory_updated=None,
        on_invoices_updated=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.invoice_service = invoice_service
        self.inventory_service = inventory_service
        self.toast = toast
        self._on_inventory_updated = on_inventory_updated
        self._on_invoices_updated = on_invoices_updated
        self.invoices: list[InvoiceSummary] = []
        self._page_size = 200
        self._loaded_count = 0
        self._total_count = 0
        self._total_amount = 0.0
        self._loading_more = False
        self._show_prices = True
        self._can_edit = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("Invoices")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        header.addWidget(title)
        header.addStretch(1)

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh)
        header.addWidget(refresh_button)

        self.edit_button = QPushButton("Edit Invoice")
        self.edit_button.clicked.connect(self._edit_selected_invoice)
        self.edit_button.setEnabled(False)
        self.edit_button.setVisible(False)
        self.edit_button.setToolTip("Only purchase invoices can be edited.")
        header.addWidget(self.edit_button)

        self.delete_button = QPushButton("Delete Invoice")
        self.delete_button.setStyleSheet(
            "QPushButton { background: #DC2626; }"
            "QPushButton:hover { background: #B91C1C; }"
            "QPushButton:disabled { background: #9CA3AF; }"
        )
        self.delete_button.clicked.connect(self._delete_selected_invoice)
        self.delete_button.setEnabled(False)
        self.delete_button.setVisible(False)
        header.addWidget(self.delete_button)

        self.load_more_button = QPushButton("Load More")
        self.load_more_button.clicked.connect(self._load_more)
        self.load_more_button.setEnabled(False)
        header.addWidget(self.load_more_button)
        layout.addLayout(header)

        summary_card = QFrame()
        summary_card.setObjectName("Card")
        summary_layout = QHBoxLayout(summary_card)
        summary_layout.setContentsMargins(16, 16, 16, 16)
        summary_layout.setSpacing(24)

        self.total_invoices_label = QLabel("Total invoices: 0")
        self.total_amount_label = QLabel("Total amount: 0")
        summary_layout.addWidget(self.total_invoices_label)
        summary_layout.addWidget(self.total_amount_label)
        summary_layout.addStretch(1)
        layout.addWidget(summary_card)

        list_card = QFrame()
        list_card.setObjectName("Card")
        list_layout = QVBoxLayout(list_card)
        list_layout.setContentsMargins(16, 16, 16, 16)

        self.invoices_table = QTableWidget(0, 8)
        self.invoices_table.setHorizontalHeaderLabels(
            [
                "Date (IR)",
                "شماره فاکتور",
                "Type",
                "Lines",
                "Quantity",
                "Admin",
                "Total",
                "Export",
            ]
        )
        header_view = self.invoices_table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(6, QHeaderView.Stretch)
        header_view.setSectionResizeMode(7, QHeaderView.ResizeToContents)
        self.invoices_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.invoices_table.setAlternatingRowColors(True)
        self.invoices_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.invoices_table.horizontalHeader().setStretchLastSection(False)
        self.invoices_table.verticalHeader().setDefaultSectionSize(34)
        self.invoices_table.setMinimumHeight(240)
        self.invoices_table.itemSelectionChanged.connect(
            self._show_selected_details
        )
        self.invoices_table.itemSelectionChanged.connect(
            self._update_action_buttons
        )
        self.invoices_table.verticalScrollBar().valueChanged.connect(
            self._maybe_load_more
        )
        list_layout.addWidget(self.invoices_table)
        layout.addWidget(list_card)

        details_card = QFrame()
        details_card.setObjectName("Card")
        details_layout = QVBoxLayout(details_card)
        details_layout.setContentsMargins(16, 16, 16, 16)
        details_layout.setSpacing(12)

        self.details_label = QLabel("Select an invoice to view details.")
        details_layout.addWidget(self.details_label)

        self.lines_table = QTableWidget(0, 4)
        self.lines_table.setHorizontalHeaderLabels(
            ["Product", "Price", "Qty", "Line Total"]
        )
        lines_header = self.lines_table.horizontalHeader()
        lines_header.setSectionResizeMode(0, QHeaderView.Stretch)
        lines_header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        lines_header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        lines_header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.lines_table.setAlternatingRowColors(True)
        self.lines_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.lines_table.horizontalHeader().setStretchLastSection(True)
        self.lines_table.verticalHeader().setDefaultSectionSize(32)
        self.lines_table.setMinimumHeight(200)
        details_layout.addWidget(self.lines_table)

        layout.addWidget(details_card)
        self._apply_price_visibility()
        self.refresh()

    def refresh(self) -> None:
        self.invoices = []
        self._loaded_count = 0
        self._total_count, self._total_amount = (
            self.invoice_service.get_invoice_stats()
        )
        self.total_invoices_label.setText(
            f"Total invoices: {self._total_count}"
        )
        self._set_total_amount_label()
        self.invoices_table.blockSignals(True)
        self.invoices_table.setRowCount(0)
        self.invoices_table.blockSignals(False)
        self.details_label.setText("Select an invoice to view details.")
        self.lines_table.setRowCount(0)
        self._load_more()
        self._update_action_buttons()

    def _show_selected_details(self) -> None:
        row = self.invoices_table.currentRow()
        if row < 0:
            return
        item = self.invoices_table.item(row, 0)
        if not item:
            return
        invoice_id = item.data(Qt.UserRole)
        lines = self.invoice_service.get_invoice_lines(int(invoice_id))

        inv = next(
            (inv for inv in self.invoices if inv.invoice_id == invoice_id),
            None,
        )
        if inv:
            header_parts = [
                f"شماره فاکتور {inv.invoice_id}",
                self._format_type(inv.invoice_type),
                to_jalali_datetime(inv.created_at),
            ]
            header_parts.append(
                f"Admin {self._format_admin(inv.admin_id, inv.admin_username)}"
            )
            if self._show_prices:
                header_parts.append(
                    f"Total {self._format_amount(inv.total_amount)}"
                )
            else:
                header_parts.append("Total hidden")
            header = " | ".join(header_parts)
        else:
            header = "Invoice details"
        self.details_label.setText(header)

        self.lines_table.setRowCount(len(lines))
        for row_idx, line in enumerate(lines):
            self.lines_table.setItem(
                row_idx, 0, QTableWidgetItem(line.product_name)
            )
            price_item = QTableWidgetItem(self._format_amount(line.price))
            price_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.lines_table.setItem(row_idx, 1, price_item)

            qty_item = QTableWidgetItem(str(line.quantity))
            qty_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.lines_table.setItem(row_idx, 2, qty_item)

            total_item = QTableWidgetItem(self._format_amount(line.line_total))
            total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.lines_table.setItem(row_idx, 3, total_item)

    def _maybe_load_more(self) -> None:
        if self._loading_more or self._loaded_count >= self._total_count:
            return
        bar = self.invoices_table.verticalScrollBar()
        if bar.maximum() == 0:
            return
        if bar.value() >= bar.maximum() - 20:
            self._load_more()

    def _load_more(self) -> None:
        if self._loading_more or self._loaded_count >= self._total_count:
            self.load_more_button.setEnabled(False)
            return
        self._loading_more = True
        batch = self.invoice_service.list_invoices(
            limit=self._page_size, offset=self._loaded_count
        )
        if not batch:
            self._loading_more = False
            self.load_more_button.setEnabled(False)
            if not self.invoices:
                self.details_label.setText("No invoices yet.")
            return

        start_row = self.invoices_table.rowCount()
        self.invoices_table.setUpdatesEnabled(False)
        self.invoices_table.blockSignals(True)
        self.invoices_table.setRowCount(start_row + len(batch))
        for row_offset, invoice in enumerate(batch):
            row_idx = start_row + row_offset
            date_item = QTableWidgetItem(to_jalali_datetime(invoice.created_at))
            date_item.setData(Qt.UserRole, invoice.invoice_id)
            self.invoices_table.setItem(row_idx, 0, date_item)
            invoice_item = QTableWidgetItem(str(invoice.invoice_id))
            invoice_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.invoices_table.setItem(row_idx, 1, invoice_item)
            self.invoices_table.setItem(
                row_idx,
                2,
                QTableWidgetItem(self._format_type(invoice.invoice_type)),
            )
            lines_item = QTableWidgetItem(str(invoice.total_lines))
            lines_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.invoices_table.setItem(row_idx, 3, lines_item)

            qty_item = QTableWidgetItem(str(invoice.total_qty))
            qty_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.invoices_table.setItem(row_idx, 4, qty_item)

            admin_item = QTableWidgetItem(
                self._format_admin(invoice.admin_id, invoice.admin_username)
            )
            self.invoices_table.setItem(row_idx, 5, admin_item)

            total_value = (
                self._format_amount(invoice.total_amount)
                if self._show_prices
                else ""
            )
            total_item = QTableWidgetItem(total_value)
            total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.invoices_table.setItem(row_idx, 6, total_item)

            export_button = QPushButton("Export")
            export_button.setProperty("compact", True)
            export_button.clicked.connect(
                lambda _=False, inv_id=invoice.invoice_id: self._export_invoice(
                    inv_id
                )
            )
            self.invoices_table.setCellWidget(row_idx, 7, export_button)

        self.invoices.extend(batch)
        self._loaded_count += len(batch)
        self.invoices_table.blockSignals(False)
        self.invoices_table.setUpdatesEnabled(True)
        self._loading_more = False
        self.load_more_button.setEnabled(self._loaded_count < self._total_count)
        if start_row == 0 and self.invoices:
            self.invoices_table.selectRow(0)

    @staticmethod
    def _format_type(value: str) -> str:
        if value == "purchase":
            return "Purchase"
        if value == "sales":
            return "Sales"
        return value.title()

    @staticmethod
    def _format_amount(value: float) -> str:
        return format_amount(value)

    @staticmethod
    def _format_admin(admin_id: int | None, admin_username: str | None) -> str:
        if admin_username:
            return admin_username
        if admin_id is not None:
            return f"ID {admin_id}"
        return "Unknown"

    def set_price_visibility(self, show: bool) -> None:
        self._show_prices = bool(show)
        self._apply_price_visibility()
        self._set_total_amount_label()
        if self.invoices_table.currentRow() >= 0:
            self._show_selected_details()

    def _apply_price_visibility(self) -> None:
        self.invoices_table.setColumnHidden(6, not self._show_prices)
        self.lines_table.setColumnHidden(1, not self._show_prices)
        self.lines_table.setColumnHidden(3, not self._show_prices)

    def _set_total_amount_label(self) -> None:
        if self._show_prices:
            self.total_amount_label.setText(
                f"Total amount: {self._format_amount(self._total_amount)}"
            )
        else:
            self.total_amount_label.setText("Total amount: Hidden")

    def set_edit_enabled(self, enabled: bool) -> None:
        self._can_edit = bool(enabled)
        self.edit_button.setVisible(self._can_edit)
        self.delete_button.setVisible(self._can_edit)
        self._update_action_buttons()

    def _update_action_buttons(self) -> None:
        has_selection = self._selected_invoice_id() is not None
        edit_allowed = False
        if has_selection:
            summary = self._selected_invoice_summary()
            edit_allowed = (
                summary is not None and summary.invoice_type == "purchase"
            )
        self.edit_button.setEnabled(self._can_edit and edit_allowed)
        self.delete_button.setEnabled(self._can_edit and has_selection)

    def _selected_invoice_id(self) -> int | None:
        row = self.invoices_table.currentRow()
        if row < 0:
            return None
        item = self.invoices_table.item(row, 0)
        if not item:
            return None
        invoice_id = item.data(Qt.UserRole)
        if invoice_id is None:
            return None
        return int(invoice_id)

    def _selected_invoice_summary(self) -> InvoiceSummary | None:
        invoice_id = self._selected_invoice_id()
        if invoice_id is None:
            return None
        summary = next(
            (inv for inv in self.invoices if inv.invoice_id == invoice_id),
            None,
        )
        if summary is not None:
            return summary
        return self.invoice_service.get_invoice(invoice_id)

    def _edit_selected_invoice(self) -> None:
        if not self._can_edit:
            return
        invoice_id = self._selected_invoice_id()
        if invoice_id is None:
            return
        invoice = self.invoice_service.get_invoice(invoice_id)
        if invoice is None:
            dialogs.show_error(self, "Invoices", "Invoice not found.")
            return
        if invoice.invoice_type != "purchase":
            dialogs.show_info(
                self,
                "Edit Invoice",
                "Only purchase invoices can be edited.",
            )
            return
        lines = self.invoice_service.get_invoice_lines(invoice_id)
        if not lines:
            dialogs.show_error(self, "Invoices", "Invoice has no lines.")
            return
        if not self.inventory_service.is_loaded():
            dialogs.show_error(self, "Inventory", "Inventory not loaded.")
            return
        inventory_df = self.inventory_service.get_dataframe()
        product_names = self.inventory_service.get_product_names()
        cost_map = {
            normalize_text(name): float(inventory_df.at[idx, "avg_buy_price"])
            for idx, name in inventory_df["product_name"].items()
        }
        dialog = InvoiceEditDialog(
            invoice, lines, product_names, cost_map, self
        )
        if dialog.exec() != QDialog.Accepted or dialog.updated_lines is None:
            return
        new_lines = dialog.updated_lines
        updated_df, delta_map, error = self._apply_invoice_change(
            invoice.invoice_type, lines, new_lines
        )
        if error:
            dialogs.show_error(self, "Edit Invoice", error)
            return
        impact_text = self._format_stock_impact(delta_map)
        confirm = dialogs.ask_yes_no(
            self,
            "Edit Invoice",
            (
                f"Save changes to invoice #{invoice.invoice_id}?\n"
                f"Type: {self._format_type(invoice.invoice_type)}\n"
                f"Date: {to_jalali_datetime(invoice.created_at)}\n"
                f"Lines: {len(lines)} → {len(new_lines)}\n"
                f"Stock impact:\n{impact_text}"
            ),
        )
        if not confirm:
            return
        if not self._save_inventory_and_update_db(
            updated_df,
            lambda: self.invoice_service.update_invoice_lines(
                invoice.invoice_id, invoice.invoice_type, new_lines
            ),
        ):
            return
        if self.toast:
            self.toast.show("Invoice updated", "success")
        else:
            dialogs.show_info(self, "Invoices", "Invoice updated.")
        self._after_invoice_change()

    def _delete_selected_invoice(self) -> None:
        if not self._can_edit:
            return
        invoice_id = self._selected_invoice_id()
        if invoice_id is None:
            return
        invoice = self.invoice_service.get_invoice(invoice_id)
        if invoice is None:
            dialogs.show_error(self, "Invoices", "Invoice not found.")
            return
        lines = self.invoice_service.get_invoice_lines(invoice_id)
        if not lines:
            dialogs.show_error(self, "Invoices", "Invoice has no lines.")
            return
        if not self.inventory_service.is_loaded():
            dialogs.show_error(self, "Inventory", "Inventory not loaded.")
            return
        updated_df, delta_map, error = self._apply_invoice_change(
            invoice.invoice_type, lines, []
        )
        if error:
            dialogs.show_error(self, "Delete Invoice", error)
            return
        impact_text = self._format_stock_impact(delta_map)
        confirm = dialogs.ask_yes_no(
            self,
            "Delete Invoice",
            (
                f"Delete invoice #{invoice.invoice_id}?\n"
                f"Type: {self._format_type(invoice.invoice_type)}\n"
                f"Date: {to_jalali_datetime(invoice.created_at)}\n"
                f"Lines: {invoice.total_lines}\n"
                f"Stock impact:\n{impact_text}"
            ),
        )
        if not confirm:
            return
        if not self._save_inventory_and_update_db(
            updated_df,
            lambda: self.invoice_service.delete_invoice(invoice.invoice_id),
        ):
            return
        if self.toast:
            self.toast.show("Invoice deleted", "success")
        else:
            dialogs.show_info(self, "Invoices", "Invoice deleted.")
        self._after_invoice_change()

    def _export_invoice(self, invoice_id: int) -> None:
        invoice = self.invoice_service.get_invoice(invoice_id)
        if invoice is None:
            dialogs.show_error(self, "Export Invoice", "Invoice not found.")
            return
        lines = self.invoice_service.get_invoice_lines(invoice_id)
        if not lines:
            dialogs.show_error(self, "Export Invoice", "Invoice has no lines.")
            return
        default_name = f"invoice_{invoice.invoice_id}.xlsx"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Invoice",
            default_name,
            "Excel Files (*.xlsx)",
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".xlsx"):
            file_path = f"{file_path}.xlsx"
        export_invoice_excel(file_path, invoice, lines)
        if self.toast:
            self.toast.show("Invoice exported", "success")
        else:
            dialogs.show_info(self, "Export Invoice", "Invoice exported.")

    def _after_invoice_change(self) -> None:
        if self._on_inventory_updated:
            self._on_inventory_updated()
        if self._on_invoices_updated:
            self._on_invoices_updated()
        else:
            self.refresh()

    def _save_inventory_and_update_db(self, updated_df, update_db) -> bool:
        backup_path = None
        try:
            backup_path = self.inventory_service.save(updated_df)
        except Exception as exc:  # noqa: BLE001
            dialogs.show_error(self, "Inventory", str(exc))
            return False
        try:
            update_db()
        except Exception as exc:  # noqa: BLE001
            if backup_path and self.inventory_service.store.path is not None:
                shutil.copy2(backup_path, self.inventory_service.store.path)
                try:
                    self.inventory_service.load()
                except Exception:  # noqa: BLE001
                    pass
            dialogs.show_error(self, "Invoices", str(exc))
            return False
        return True

    def _apply_invoice_change(self, invoice_type, old_lines, new_lines):
        inventory_df = self.inventory_service.get_dataframe().copy()
        if invoice_type == "sales":
            return self._apply_sales_change(inventory_df, old_lines, new_lines)
        if invoice_type == "purchase":
            return self._apply_purchase_change(
                inventory_df, old_lines, new_lines
            )
        return None, {}, "Unsupported invoice type."

    def _apply_sales_change(self, df, old_lines, new_lines):
        old_map = self._aggregate_lines(old_lines, include_cost=False)
        new_map = self._aggregate_lines(new_lines, include_cost=False)
        inventory_index = {
            normalize_text(name): idx
            for idx, name in df["product_name"].items()
        }
        errors: list[str] = []
        delta_map: dict[str, int] = {}
        for key in set(old_map) | set(new_map):
            old_qty = old_map.get(key, {}).get("qty", 0)
            new_qty = new_map.get(key, {}).get("qty", 0)
            delta = old_qty - new_qty
            idx = inventory_index.get(key)
            if idx is None:
                errors.append(
                    f"Product not found in inventory: {old_map.get(key, {}).get('name') or new_map.get(key, {}).get('name')}"
                )
                continue
            current_qty = int(df.at[idx, "quantity"])
            new_qty_total = current_qty + delta
            if delta < 0 and new_qty_total < 0:
                errors.append(
                    f"Not enough stock for {df.at[idx, 'product_name']}."
                )
                continue
            df.at[idx, "quantity"] = int(new_qty_total)
            if delta != 0:
                delta_map[df.at[idx, "product_name"]] = int(delta)
        if errors:
            return None, {}, "\n".join(errors[:5])
        return df, delta_map, ""

    def _apply_purchase_change(self, df, old_lines, new_lines):
        old_map = self._aggregate_lines(old_lines, include_cost=True)
        new_map = self._aggregate_lines(new_lines, include_cost=True)
        inventory_index = {
            normalize_text(name): idx
            for idx, name in df["product_name"].items()
        }
        errors: list[str] = []
        delta_map: dict[str, int] = {}
        for key in set(old_map) | set(new_map):
            old_qty = old_map.get(key, {}).get("qty", 0)
            old_cost = old_map.get(key, {}).get("cost", 0.0)
            new_qty = new_map.get(key, {}).get("qty", 0)
            new_cost = new_map.get(key, {}).get("cost", 0.0)
            idx = inventory_index.get(key)
            if idx is None:
                errors.append(
                    f"Product not found in inventory: {old_map.get(key, {}).get('name') or new_map.get(key, {}).get('name')}"
                )
                continue
            current_qty = int(df.at[idx, "quantity"])
            current_avg = float(df.at[idx, "avg_buy_price"])
            total_cost = current_avg * current_qty
            if old_qty > current_qty:
                errors.append(
                    f"Not enough stock to reverse purchase for {df.at[idx, 'product_name']}."
                )
                continue
            remaining_qty = current_qty - old_qty
            remaining_cost = total_cost - float(old_cost)
            if remaining_cost < -0.01:
                errors.append(
                    f"Stock value too low to reverse purchase for {df.at[idx, 'product_name']}."
                )
                continue
            if remaining_qty <= 0:
                remaining_qty = 0
                remaining_cost = 0.0
            new_qty_total = remaining_qty + new_qty
            new_cost_total = remaining_cost + float(new_cost)
            if new_qty_total < 0:
                errors.append(
                    f"Invalid quantity for {df.at[idx, 'product_name']}."
                )
                continue
            new_avg = new_cost_total / new_qty_total if new_qty_total else 0.0
            df.at[idx, "quantity"] = int(new_qty_total)
            df.at[idx, "avg_buy_price"] = round(float(new_avg), 4)
            delta = new_qty - old_qty
            if delta != 0:
                delta_map[df.at[idx, "product_name"]] = int(delta)
        if errors:
            return None, {}, "\n".join(errors[:5])
        return df, delta_map, ""

    @staticmethod
    def _aggregate_lines(lines, include_cost: bool):
        data: dict[str, dict[str, object]] = {}
        for line in lines:
            key = normalize_text(line.product_name)
            if key not in data:
                data[key] = {"name": line.product_name, "qty": 0, "cost": 0.0}
            data[key]["qty"] += int(line.quantity)
            if include_cost:
                data[key]["cost"] += float(line.price) * int(line.quantity)
        return data

    @staticmethod
    def _format_stock_impact(delta_map: dict[str, int]) -> str:
        if not delta_map:
            return "No stock change."
        lines = []
        sorted_items = sorted(
            delta_map.items(), key=lambda item: abs(item[1]), reverse=True
        )
        for name, delta in sorted_items[:6]:
            sign = "+" if delta > 0 else "-"
            lines.append(f"{sign}{abs(delta)} {name}")
        remaining = len(delta_map) - len(lines)
        if remaining > 0:
            lines.append(f"... and {remaining} more")
        return "\n".join(lines)
