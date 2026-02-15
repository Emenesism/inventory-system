from __future__ import annotations

import logging
import time

from PySide6.QtCore import QObject

from app.models.errors import InventoryFileError
from app.services.action_log_service import ActionLogService
from app.services.inventory_service import InventoryService
from app.services.invoice_service import InvoiceService
from app.ui.pages.inventory_page import InventoryPage
from app.ui.widgets.toast import ToastManager
from app.utils import dialogs
from app.utils.excel import (
    style_inventory_export_sheet,
)
from app.utils.text import normalize_text


class InventoryController(QObject):
    def __init__(
        self,
        page: InventoryPage,
        inventory_service: InventoryService,
        toast: ToastManager,
        action_log_service: ActionLogService,
        current_admin_provider,
        invoice_service: InvoiceService | None = None,
        refresh_history_views=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.page = page
        self.inventory_service = inventory_service
        self.toast = toast
        self.action_log_service = action_log_service
        self._current_admin_provider = current_admin_provider
        self.invoice_service = invoice_service
        self._refresh_history_views = refresh_history_views
        self._logger = logging.getLogger(self.__class__.__name__)
        self._last_inventory_log_details: str | None = None
        self._last_inventory_log_at: float = 0.0

        self.page.reload_requested.connect(self.reload)
        self.page.save_requested.connect(self.save)
        self.page.export_requested.connect(self.export)

    def reload(self) -> None:
        try:
            df = self.inventory_service.load()
        except InventoryFileError as exc:
            dialogs.show_error(self.page, self.tr("خطای موجودی"), str(exc))
            self.toast.show(self.tr("بارگذاری مجدد موجودی ناموفق بود"), "error")
            self._logger.exception("Failed to reload inventory")
            return
        self.page.set_inventory(df)
        self.toast.show(self.tr("موجودی بارگذاری مجدد شد"), "success")

    def save(self) -> None:
        df = self.page.get_dataframe()
        if df is None:
            return
        try:
            old_df = self.inventory_service.get_dataframe().copy()
        except Exception:  # noqa: BLE001
            old_df = None
        admin = (
            self._current_admin_provider()
            if self._current_admin_provider
            else None
        )
        admin_username = admin.username if admin else None
        try:
            self.inventory_service.save(df, admin_username=admin_username)
        except InventoryFileError as exc:
            dialogs.show_error(self.page, self.tr("خطای موجودی"), str(exc))
            self.toast.show(self.tr("ذخیره موجودی ناموفق بود"), "error")
            self._logger.exception("Failed to save inventory")
            return
        name_changes = self.page.get_name_changes()
        if name_changes and df is not None and "product_name" in df.columns:
            current_names = {
                normalize_text(str(name))
                for name in df["product_name"].tolist()
            }
            name_changes = [
                (old, new)
                for old, new in name_changes
                if normalize_text(new) in current_names
            ]
        clear_changes = True
        if name_changes and self.invoice_service is not None:
            try:
                rename_result = self.invoice_service.rename_products(
                    name_changes, admin_username=admin_username
                )
            except Exception:  # noqa: BLE001
                clear_changes = False
                dialogs.show_error(
                    self.page,
                    self.tr("خطای به‌روزرسانی فاکتور"),
                    self.tr("به‌روزرسانی نام کالاها در فاکتورها ناموفق بود."),
                )
                self._logger.exception(
                    "Failed to update invoice product names."
                )
            else:
                updated = rename_result.updated_lines
                if updated:
                    invoice_ids = rename_result.updated_invoice_ids
                    invoice_count = len(invoice_ids)
                    if self._refresh_history_views is not None:
                        self._refresh_history_views()
                    if self.action_log_service:
                        before_names = "\n".join(
                            f"- {old}" for old, _ in name_changes
                        )
                        after_names = "\n".join(
                            f"- {new}" for _, new in name_changes
                        )
                        detail_lines = [
                            self.tr("قبل:\n{before_names}").format(
                                before_names=before_names or self.tr("(هیچ)")
                            ),
                            self.tr("بعد:\n{after_names}").format(
                                after_names=after_names or self.tr("(هیچ)")
                            ),
                        ]
                        if invoice_ids:
                            invoice_text = ", ".join(
                                str(invoice_id) for invoice_id in invoice_ids
                            )
                            detail_lines.append(
                                self.tr("فاکتورهای تحت تاثیر: {ids}").format(
                                    ids=invoice_text
                                )
                            )
                        detail_lines.append(
                            self.tr("تعداد ردیف‌های تغییرکرده: {count}").format(
                                count=updated
                            )
                        )
                        details = "\n".join(detail_lines)
                        self.action_log_service.log_action(
                            "invoice_product_rename",
                            self.tr("به‌روزرسانی نام کالا در فاکتورها"),
                            details,
                            admin=admin,
                        )
                    shown_ids = ", ".join(
                        str(invoice_id) for invoice_id in invoice_ids[:25]
                    )
                    if len(invoice_ids) > 25:
                        shown_ids += (
                            f", ... (+{len(invoice_ids) - 25} "
                            + self.tr("مورد دیگر")
                            + ")"
                        )
                    if shown_ids:
                        dialogs.show_info(
                            self.page,
                            self.tr("به‌روزرسانی فاکتور"),
                            (
                                self.tr(
                                    "{updated} ردیف فاکتور در {count} فاکتور به‌روزرسانی شد.\n"
                                ).format(updated=updated, count=invoice_count)
                                + self.tr("شناسه فاکتورها: {ids}").format(
                                    ids=shown_ids
                                )
                            ),
                        )
                    self.toast.show(
                        self.tr(
                            "{updated} ردیف در {count} فاکتور به‌روزرسانی شد"
                        ).format(updated=updated, count=invoice_count),
                        "success",
                    )
        if clear_changes:
            self.page.clear_name_changes()
        if old_df is not None:
            details = self._build_inventory_diff(old_df, df)
            if details and self.action_log_service:
                if not self._is_duplicate_inventory_log(details):
                    self.action_log_service.log_action(
                        "inventory_edit",
                        self.tr("ویرایش دستی موجودی"),
                        details,
                        admin=admin,
                    )
                    self._last_inventory_log_details = details
                    self._last_inventory_log_at = time.monotonic()
        self.toast.show(self.tr("موجودی ذخیره شد"), "success")

    def export(self) -> None:
        df = self.page.get_dataframe()
        if df is None:
            dialogs.show_error(
                self.page,
                self.tr("موجودی"),
                self.tr("موجودی بارگذاری نشده است."),
            )
            return
        if df.empty:
            dialogs.show_error(
                self.page,
                self.tr("موجودی"),
                self.tr("داده‌ای برای خروجی وجود ندارد."),
            )
            return
        from PySide6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getSaveFileName(
            self.page,
            self.tr("خروجی موجودی"),
            "stock.xlsx",
            self.tr("فایل‌های اکسل (*.xlsx)"),
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".xlsx"):
            file_path = f"{file_path}.xlsx"
        try:
            export_df = self._prepare_export_dataframe(df)
            export_df.to_excel(file_path, index=False)
            style_inventory_export_sheet(file_path, data_row_height=24)
        except Exception as exc:  # noqa: BLE001
            dialogs.show_error(self.page, self.tr("موجودی"), str(exc))
            self._logger.exception("Failed to export inventory")
            return
        if self.action_log_service:
            admin = (
                self._current_admin_provider()
                if self._current_admin_provider
                else None
            )
            self.action_log_service.log_action(
                "inventory_export",
                self.tr("خروجی موجودی"),
                self.tr("تعداد ردیف‌ها: {count}\nمسیر: {path}").format(
                    count=len(export_df),
                    path=file_path,
                ),
                admin=admin,
            )
        self.toast.show(self.tr("خروجی موجودی انجام شد"), "success")

    @staticmethod
    def _sort_for_export(df):  # noqa: ANN001
        export_df = df.copy()
        if export_df.empty:
            return export_df

        name_column = (
            "product_name"
            if "product_name" in export_df.columns
            else str(export_df.columns[0])
        )
        sort_key = (
            export_df[name_column]
            .fillna("")
            .map(lambda value: normalize_text(str(value)))
        )
        empty_key = sort_key == ""
        return (
            export_df.assign(_empty_sort=empty_key, _name_sort=sort_key)
            .sort_values(
                by=["_empty_sort", "_name_sort"],
                ascending=[True, True],
                kind="mergesort",
            )
            .drop(columns=["_empty_sort", "_name_sort"])
            .reset_index(drop=True)
        )

    @classmethod
    def _prepare_export_dataframe(cls, df):  # noqa: ANN001
        export_df = cls._sort_for_export(df)
        if export_df.empty:
            return export_df
        localized = export_df.rename(
            columns={
                str(column): cls._inventory_export_column_label(str(column))
                for column in export_df.columns
            }
        )
        localized.insert(0, "ردیف", range(1, len(localized) + 1))
        return localized

    @staticmethod
    def _inventory_export_column_label(column_name: str) -> str:
        normalized = (
            str(column_name).strip().lower().replace("-", "_").replace(" ", "_")
        )
        mapping = {
            "product_name": "نام کالا",
            "quantity": "تعداد",
            "avg_buy_price": "میانگین قیمت خرید",
            "last_buy_price": "آخرین قیمت خرید",
            "sell_price": "قیمت فروش",
            "alarm": "آلارم",
            "source": "منبع",
        }
        return mapping.get(normalized, str(column_name))

    def _build_inventory_diff(self, old_df, new_df) -> str:  # noqa: ANN001
        def key_map(df):
            return {
                normalize_text(str(row["product_name"])): row
                for _, row in df.iterrows()
                if str(row.get("product_name", "")).strip()
            }

        columns: list[str] = []
        for col in list(old_df.columns) + list(new_df.columns):
            col_name = str(col)
            if col_name not in columns:
                columns.append(col_name)
        if "product_name" in columns:
            columns = ["product_name"] + [
                col for col in columns if col != "product_name"
            ]

        old_map = key_map(old_df)
        new_map = key_map(new_df)

        sections: list[str] = []
        added = 0
        edited = 0
        removed = 0

        for key, new_row in new_map.items():
            old_row = old_map.get(key)
            name = str(new_row.get("product_name", "")).strip() or key
            if old_row is None:
                added += 1
                sections.append(
                    self.tr(
                        "[افزودن کالا] {name}\n"
                        "قبل:\n"
                        "(وجود ندارد)\n"
                        "بعد:\n"
                        "{after_block}"
                    ).format(
                        name=name,
                        after_block=self._format_inventory_row_block(
                            new_row, columns
                        ),
                    )
                )
                continue

            changed = any(
                self._values_differ(old_row.get(col), new_row.get(col))
                for col in columns
                if col != "product_name"
            )
            if not changed:
                continue

            edited += 1
            sections.append(
                self.tr(
                    "[ویرایش کالا] {name}\n"
                    "قبل:\n"
                    "{before_block}\n"
                    "بعد:\n"
                    "{after_block}"
                ).format(
                    name=name,
                    before_block=self._format_inventory_row_block(
                        old_row, columns
                    ),
                    after_block=self._format_inventory_row_block(
                        new_row, columns
                    ),
                )
            )

        for key, old_row in old_map.items():
            if key in new_map:
                continue
            removed += 1
            name = str(old_row.get("product_name", "")).strip() or key
            sections.append(
                self.tr(
                    "[حذف کالا] {name}\nقبل:\n{before_block}\nبعد:\n(حذف شد)"
                ).format(
                    name=name,
                    before_block=self._format_inventory_row_block(
                        old_row, columns
                    ),
                )
            )

        if not sections:
            return ""

        summary = self.tr(
            "خلاصه تغییرات موجودی | افزودن: {added} | ویرایش: {edited} | حذف: {removed}"
        ).format(added=added, edited=edited, removed=removed)
        return summary + "\n\n" + "\n\n".join(sections)

    def _inventory_column_label(self, column_name: str) -> str:
        return {
            "product_name": self.tr("نام کالا"),
            "quantity": self.tr("تعداد"),
            "avg_buy_price": self.tr("میانگین قیمت خرید"),
            "last_buy_price": self.tr("آخرین قیمت خرید"),
            "sell_price": self.tr("قیمت فروش"),
            "alarm": self.tr("آلارم"),
            "source": self.tr("منبع"),
        }.get(column_name, column_name)

    @staticmethod
    def _value_missing(value) -> bool:  # noqa: ANN001
        if value is None:
            return True
        try:
            compare = value != value
            if isinstance(compare, bool):
                if compare:
                    return True
            elif str(compare).strip().lower() == "true":
                return True
        except Exception:  # noqa: BLE001
            pass
        return str(value).strip().lower() in {"nan", "none", "<na>", "nat"}

    def _values_differ(self, a, b) -> bool:  # noqa: ANN001
        if self._value_missing(a) and self._value_missing(b):
            return False
        try:
            if isinstance(a, (int, float)) or isinstance(b, (int, float)):
                return abs(float(a) - float(b)) > 1e-6
        except Exception:  # noqa: BLE001
            pass
        return str(a) != str(b)

    def _format_inventory_value(self, value) -> str:  # noqa: ANN001
        if self._value_missing(value):
            return "-"
        if isinstance(value, float):
            rounded = round(value)
            if abs(value - rounded) < 1e-6:
                return f"{int(rounded):,}"
            return f"{value:,.4f}".rstrip("0").rstrip(".")
        return str(value)

    def _format_inventory_row_block(self, row, columns: list[str]) -> str:  # noqa: ANN001
        headers = [self._inventory_column_label(col) for col in columns]
        values = [self._format_inventory_value(row.get(col)) for col in columns]
        header_row = " | ".join(headers)
        value_row = " | ".join(values)
        return header_row + "\n" + value_row

    def _is_duplicate_inventory_log(self, details: str) -> bool:
        if self._last_inventory_log_details != details:
            return False
        return (time.monotonic() - self._last_inventory_log_at) < 2.0
