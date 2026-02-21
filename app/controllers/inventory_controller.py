from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

from PySide6.QtCore import QObject, QThread, Signal, Slot

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
from app.utils.text import is_empty_marker, normalize_text


@dataclass
class _InventorySaveContext:
    df: Any
    old_df: Any
    admin: Any
    admin_username: str | None
    name_changes: list[tuple[str, str]]


class _InventorySaveWorker(QObject):
    progress = Signal(str)
    succeeded = Signal(dict)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        inventory_service: InventoryService,
        invoice_service: InvoiceService | None,
        df,
        old_df,
        admin_username: str | None,
        name_changes: list[tuple[str, str]],
    ) -> None:  # noqa: ANN001
        super().__init__()
        self._inventory_service = inventory_service
        self._invoice_service = invoice_service
        self._df = df
        self._old_df = old_df
        self._admin_username = admin_username
        self._name_changes = name_changes

    @Slot()
    def run(self) -> None:
        try:
            self.progress.emit("saving_inventory")
            self._inventory_service.save(
                self._df, admin_username=self._admin_username
            )
            result: dict[str, Any] = {
                "updated_lines": 0,
                "updated_invoice_ids": [],
                "rename_error": "",
                "diff_details": "",
                "diff_failed": False,
                "diff_error": "",
            }
            if self._name_changes and self._invoice_service is not None:
                self.progress.emit("renaming_invoices")
                try:
                    rename_result = self._invoice_service.rename_products(
                        self._name_changes, admin_username=self._admin_username
                    )
                except Exception as exc:  # noqa: BLE001
                    result["rename_error"] = str(exc)
                else:
                    result["updated_lines"] = int(rename_result.updated_lines)
                    result["updated_invoice_ids"] = [
                        int(invoice_id)
                        for invoice_id in rename_result.updated_invoice_ids
                    ]
            if self._old_df is not None:
                self.progress.emit("building_diff")
                try:
                    result["diff_details"] = (
                        InventoryController.build_inventory_diff_for_worker(
                            self._old_df, self._df
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    result["diff_failed"] = True
                    result["diff_error"] = str(exc)
            self.succeeded.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()


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
        self._save_thread: QThread | None = None
        self._save_worker: _InventorySaveWorker | None = None
        self._save_context: _InventorySaveContext | None = None

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
        if self._save_thread is not None and self._save_thread.isRunning():
            self.toast.show(self.tr("ذخیره موجودی در حال انجام است"), "info")
            return
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
        self._save_context = _InventorySaveContext(
            df=df,
            old_df=old_df,
            admin=admin,
            admin_username=admin_username,
            name_changes=name_changes,
        )
        self._start_save_worker()

    def _start_save_worker(self) -> None:
        context = self._save_context
        if context is None:
            return
        self.page.set_save_in_progress(True, self.tr("در حال ذخیره موجودی..."))
        self.toast.show(self.tr("ذخیره موجودی آغاز شد"), "info")
        thread = QThread(self)
        worker = _InventorySaveWorker(
            self.inventory_service,
            self.invoice_service,
            context.df,
            context.old_df,
            context.admin_username,
            context.name_changes,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_save_progress)
        worker.succeeded.connect(self._on_save_succeeded)
        worker.failed.connect(self._on_save_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_save_thread_finished)
        thread.finished.connect(thread.deleteLater)
        self._save_thread = thread
        self._save_worker = worker
        thread.start()

    @Slot(str)
    def _on_save_progress(self, stage: str) -> None:
        status_map = {
            "saving_inventory": self.tr("در حال ذخیره موجودی..."),
            "renaming_invoices": self.tr(
                "در حال به‌روزرسانی نام کالاها در فاکتورها..."
            ),
            "building_diff": self.tr("در حال آماده‌سازی گزارش تغییرات..."),
        }
        self.page.set_save_in_progress(
            True, status_map.get(stage, self.tr("در حال ذخیره موجودی..."))
        )

    @Slot(dict)
    def _on_save_succeeded(self, payload: dict[str, Any]) -> None:
        context = self._save_context
        if context is None:
            self.page.set_save_in_progress(False)
            return
        self.page.set_save_in_progress(
            True, self.tr("در حال نهایی‌سازی ذخیره...")
        )
        clear_changes = True
        rename_error = str(payload.get("rename_error", "")).strip()
        if rename_error:
            clear_changes = False
            dialogs.show_error(
                self.page,
                self.tr("خطای به‌روزرسانی فاکتور"),
                self.tr("به‌روزرسانی نام کالاها در فاکتورها ناموفق بود."),
            )
            self._logger.error(
                "Failed to update invoice product names: %s", rename_error
            )
        else:
            updated = int(payload.get("updated_lines", 0) or 0)
            if updated:
                invoice_ids = [
                    int(invoice_id)
                    for invoice_id in payload.get("updated_invoice_ids", [])
                ]
                invoice_count = len(invoice_ids)
                if self._refresh_history_views is not None:
                    self._refresh_history_views()
                if self.action_log_service:
                    before_names = "\n".join(
                        f"- {old}" for old, _ in context.name_changes
                    )
                    after_names = "\n".join(
                        f"- {new}" for _, new in context.name_changes
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
                        admin=context.admin,
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
        details = str(payload.get("diff_details", "") or "")
        if context.old_df is not None and bool(payload.get("diff_failed")):
            self._logger.warning(
                "Background diff builder failed; falling back to UI thread: %s",
                str(payload.get("diff_error", "") or "-"),
            )
            details = self._build_inventory_diff(context.old_df, context.df)
        if details and self.action_log_service:
            if not self._is_duplicate_inventory_log(details):
                self.action_log_service.log_action(
                    "inventory_edit",
                    self.tr("ویرایش دستی موجودی"),
                    details,
                    admin=context.admin,
                )
                self._last_inventory_log_details = details
                self._last_inventory_log_at = time.monotonic()
        self._save_context = None
        self.page.set_save_in_progress(False)
        self.toast.show(self.tr("موجودی ذخیره شد"), "success")

    @Slot(str)
    def _on_save_failed(self, message: str) -> None:
        self.page.set_save_in_progress(False)
        dialogs.show_error(
            self.page,
            self.tr("خطای موجودی"),
            message or self.tr("ذخیره موجودی ناموفق بود."),
        )
        self.toast.show(self.tr("ذخیره موجودی ناموفق بود"), "error")
        self._logger.error("Failed to save inventory: %s", message)
        self._save_context = None

    @Slot()
    def _on_save_thread_finished(self) -> None:
        self._save_thread = None
        self._save_worker = None

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

    @classmethod
    def build_inventory_diff_for_worker(cls, old_df, new_df) -> str:  # noqa: ANN001
        return cls._build_inventory_diff_fast(old_df, new_df)

    def _build_inventory_diff(self, old_df, new_df) -> str:  # noqa: ANN001
        try:
            return self._build_inventory_diff_fast(
                old_df, new_df, translate=self.tr
            )
        except Exception:  # noqa: BLE001
            self._logger.exception(
                "Fast inventory diff failed. Falling back to legacy diff builder."
            )
            return self._build_inventory_diff_legacy(old_df, new_df)

    @classmethod
    def _build_inventory_diff_fast(
        cls,
        old_df,
        new_df,
        translate: Callable[[str], str] | None = None,
    ) -> str:  # noqa: ANN001
        columns: list[str] = []
        old_columns = list(old_df.columns) if old_df is not None else []
        new_columns = list(new_df.columns) if new_df is not None else []
        for col in old_columns + new_columns:
            col_name = str(col)
            if col_name not in columns:
                columns.append(col_name)
        if "product_name" in columns:
            columns = ["product_name"] + [
                col for col in columns if col != "product_name"
            ]

        old_map, old_order, old_indexed = cls._prepare_inventory_diff_data(
            old_df
        )
        new_map, new_order, new_indexed = cls._prepare_inventory_diff_data(
            new_df
        )

        sections: list[str] = []
        added = 0
        edited = 0
        removed = 0

        shared_order = [key for key in new_order if key in old_map]
        changed_keys: set[str] = set()
        if shared_order:
            old_shared = old_indexed.reindex(shared_order)
            new_shared = new_indexed.reindex(shared_order)
            changed_flags = [False] * len(shared_order)
            compare_columns = [col for col in columns if col != "product_name"]
            for col in compare_columns:
                if col in old_shared.columns:
                    old_values = old_shared[col].to_numpy()
                else:
                    old_values = [None] * len(shared_order)
                if col in new_shared.columns:
                    new_values = new_shared[col].to_numpy()
                else:
                    new_values = [None] * len(shared_order)
                for idx, (old_value, new_value) in enumerate(
                    zip(old_values, new_values)
                ):
                    if changed_flags[idx]:
                        continue
                    if cls._values_differ_static(old_value, new_value):
                        changed_flags[idx] = True
            changed_keys = {
                shared_order[idx]
                for idx, is_changed in enumerate(changed_flags)
                if is_changed
            }

        for key in new_order:
            new_row = new_map.get(key)
            if new_row is None:
                continue
            old_row = old_map.get(key)
            name = str(new_row.get("product_name", "")).strip() or key
            if old_row is None:
                added += 1
                sections.append(
                    cls._tr(
                        "[افزودن کالا] {name}\n"
                        "قبل:\n"
                        "(وجود ندارد)\n"
                        "بعد:\n"
                        "{after_block}",
                        translate,
                    ).format(
                        name=name,
                        after_block=cls._format_inventory_row_block_static(
                            new_row, columns, translate=translate
                        ),
                    )
                )
                continue
            if key not in changed_keys:
                continue
            edited += 1
            sections.append(
                cls._tr(
                    "[ویرایش کالا] {name}\n"
                    "قبل:\n"
                    "{before_block}\n"
                    "بعد:\n"
                    "{after_block}",
                    translate,
                ).format(
                    name=name,
                    before_block=cls._format_inventory_row_block_static(
                        old_row, columns, translate=translate
                    ),
                    after_block=cls._format_inventory_row_block_static(
                        new_row, columns, translate=translate
                    ),
                )
            )

        for key in old_order:
            if key in new_map:
                continue
            old_row = old_map.get(key)
            if old_row is None:
                continue
            removed += 1
            name = str(old_row.get("product_name", "")).strip() or key
            sections.append(
                cls._tr(
                    "[حذف کالا] {name}\nقبل:\n{before_block}\nبعد:\n(حذف شد)",
                    translate,
                ).format(
                    name=name,
                    before_block=cls._format_inventory_row_block_static(
                        old_row, columns, translate=translate
                    ),
                )
            )

        if not sections:
            return ""

        summary = cls._tr(
            "خلاصه تغییرات موجودی | افزودن: {added} | ویرایش: {edited} | حذف: {removed}",
            translate,
        ).format(added=added, edited=edited, removed=removed)
        return summary + "\n\n" + "\n\n".join(sections)

    def _build_inventory_diff_legacy(self, old_df, new_df) -> str:  # noqa: ANN001
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

    @classmethod
    def _prepare_inventory_diff_data(cls, df):  # noqa: ANN001
        if df is None:
            return {}, [], None
        if "product_name" not in df.columns:
            return {}, [], df.iloc[0:0].copy()
        working = df.copy()
        name_series = working["product_name"].fillna("").astype(str).str.strip()
        keys = name_series.map(normalize_text)
        working = working.assign(_key=keys)
        working = working[working["_key"] != ""].copy()
        if working.empty:
            return {}, [], working.set_index("_key", drop=False)
        ordered_keys = list(dict.fromkeys(working["_key"].tolist()))
        deduped = working.drop_duplicates(subset="_key", keep="last").copy()
        indexed = deduped.set_index("_key", drop=False)
        row_map = indexed.drop(columns=["_key"]).to_dict(orient="index")
        return row_map, ordered_keys, indexed.drop(columns=["_key"])

    def _inventory_column_label(self, column_name: str) -> str:
        return self._inventory_column_label_static(column_name, self.tr)

    @staticmethod
    def _inventory_column_label_static(
        column_name: str, translate: Callable[[str], str] | None = None
    ) -> str:
        tr = translate or (lambda text: text)
        return {
            "product_name": tr("نام کالا"),
            "quantity": tr("تعداد"),
            "avg_buy_price": tr("میانگین قیمت خرید"),
            "last_buy_price": tr("آخرین قیمت خرید"),
            "sell_price": tr("قیمت فروش"),
            "alarm": tr("آلارم"),
            "source": tr("منبع"),
        }.get(column_name, column_name)

    @staticmethod
    def _value_missing(value) -> bool:  # noqa: ANN001
        return is_empty_marker(value)

    def _values_differ(self, a, b) -> bool:  # noqa: ANN001
        return self._values_differ_static(a, b)

    @staticmethod
    def _values_differ_static(a, b) -> bool:  # noqa: ANN001
        if InventoryController._value_missing(
            a
        ) and InventoryController._value_missing(b):
            return False
        try:
            if isinstance(a, (int, float)) or isinstance(b, (int, float)):
                return abs(float(a) - float(b)) > 1e-6
        except Exception:  # noqa: BLE001
            pass
        return str(a) != str(b)

    def _format_inventory_value(self, value) -> str:  # noqa: ANN001
        return self._format_inventory_value_static(value)

    @staticmethod
    def _format_inventory_value_static(value) -> str:  # noqa: ANN001
        if InventoryController._value_missing(value):
            return "-"
        if isinstance(value, float):
            rounded = round(value)
            if abs(value - rounded) < 1e-6:
                return f"{int(rounded):,}"
            return f"{value:,.4f}".rstrip("0").rstrip(".")
        return str(value)

    def _format_inventory_row_block(self, row, columns: list[str]) -> str:  # noqa: ANN001
        return self._format_inventory_row_block_static(
            row, columns, translate=self.tr
        )

    @classmethod
    def _format_inventory_row_block_static(
        cls,
        row,
        columns: list[str],
        translate: Callable[[str], str] | None = None,
    ) -> str:  # noqa: ANN001
        headers = [
            cls._inventory_column_label_static(col, translate=translate)
            for col in columns
        ]
        values = [
            cls._format_inventory_value_static(row.get(col)) for col in columns
        ]
        header_row = " | ".join(headers)
        value_row = " | ".join(values)
        return header_row + "\n" + value_row

    @staticmethod
    def _tr(text: str, translate: Callable[[str], str] | None = None) -> str:
        if translate is None:
            return text
        return translate(text)

    def _is_duplicate_inventory_log(self, details: str) -> bool:
        if self._last_inventory_log_details != details:
            return False
        return (time.monotonic() - self._last_inventory_log_at) < 2.0
