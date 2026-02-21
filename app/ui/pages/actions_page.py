from __future__ import annotations

import re
from html import escape

from PySide6.QtCore import QCoreApplication, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGraphicsBlurEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.services.action_log_service import ActionEntry, ActionLogService
from app.ui.fonts import format_html_font_stack, resolve_export_font_roles
from app.utils.dates import to_jalali_datetime


class ActionsPage(QWidget):
    def __init__(
        self, action_service: ActionLogService, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setLayoutDirection(Qt.RightToLeft)
        self.action_service = action_service
        self._page_size = 200
        self._loaded_count = 0
        self._total_count = 0
        self._loading_more = False
        self._actions: list[ActionEntry] = []
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self.refresh)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(16)

        self._content = QWidget()
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel(self.tr("اقدامات"))
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        header.addWidget(title)
        header.addStretch(1)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(self.tr("جستجو در اقدامات..."))
        self.search_input.textChanged.connect(self._queue_refresh)
        header.addWidget(self.search_input)

        refresh_button = QPushButton(self.tr("بروزرسانی"))
        refresh_button.clicked.connect(self.refresh)
        header.addWidget(refresh_button)

        self.load_more_button = QPushButton(self.tr("موارد بیشتر"))
        self.load_more_button.clicked.connect(self._load_more)
        self.load_more_button.setEnabled(False)
        header.addWidget(self.load_more_button)
        content_layout.addLayout(header)

        summary_card = QFrame()
        summary_card.setObjectName("Card")
        summary_layout = QHBoxLayout(summary_card)
        summary_layout.setContentsMargins(16, 16, 16, 16)
        summary_layout.setSpacing(24)

        self.total_label = QLabel(self.tr("تعداد اقدامات: 0"))
        summary_layout.addWidget(self.total_label)
        summary_layout.addStretch(1)
        content_layout.addWidget(summary_card)

        list_card = QFrame()
        list_card.setObjectName("Card")
        list_layout = QVBoxLayout(list_card)
        list_layout.setContentsMargins(16, 16, 16, 16)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            [
                self.tr("تاریخ"),
                self.tr("ادمین"),
                self.tr("نوع"),
                self.tr("عنوان"),
            ]
        )
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(32)
        if hasattr(self.table, "setUniformRowHeights"):
            self.table.setUniformRowHeights(True)
        self.table.itemSelectionChanged.connect(self._show_details)
        self.table.verticalScrollBar().valueChanged.connect(
            self._maybe_load_more
        )
        list_layout.addWidget(self.table)
        content_layout.addWidget(list_card)

        details_card = QFrame()
        details_card.setObjectName("Card")
        details_layout = QVBoxLayout(details_card)
        details_layout.setContentsMargins(16, 16, 16, 16)
        details_layout.setSpacing(12)

        self.details_label = QLabel(self.tr("جزئیات اقدام را انتخاب کنید."))
        self.details_label.setStyleSheet(
            "font-size: 15px; font-weight: 700; color: #334155;"
        )
        details_layout.addWidget(self.details_label)

        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setLineWrapMode(QTextEdit.WidgetWidth)
        self.details_text.setLayoutDirection(Qt.RightToLeft)
        details_layout.addWidget(self.details_text)
        content_layout.addWidget(details_card)

        outer.addWidget(self._content)

        self._overlay = QFrame(self)
        self._overlay.setStyleSheet(
            "background: rgba(15, 23, 42, 0.55); border-radius: 16px;"
        )
        overlay_layout = QVBoxLayout(self._overlay)
        overlay_layout.setContentsMargins(0, 0, 0, 0)
        overlay_layout.addStretch(1)
        self._overlay.hide()

        self.refresh()
        self.set_accessible(False)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._overlay.setGeometry(self.rect())

    def set_accessible(self, accessible: bool) -> None:
        if accessible:
            self._content.setGraphicsEffect(None)
            self._content.setEnabled(True)
            self._overlay.hide()
        else:
            blur = QGraphicsBlurEffect(self)
            blur.setBlurRadius(12)
            self._content.setGraphicsEffect(blur)
            self._content.setEnabled(False)
            self._overlay.show()
            self._overlay.raise_()

    def refresh(self) -> None:
        self._search_timer.stop()
        self._actions = []
        self._loaded_count = 0
        search = self.search_input.text().strip()
        self._total_count = self.action_service.count_actions(
            search if search else None
        )
        self.total_label.setText(
            self.tr("تعداد اقدامات: {count}").format(count=self._total_count)
        )
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        self.table.blockSignals(False)
        self.details_label.setText(self.tr("جزئیات اقدام را انتخاب کنید."))
        self.details_text.clear()
        self._load_more()

    def _queue_refresh(self, _text: str) -> None:
        self._search_timer.start()

    def _show_details(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 0)
        if not item:
            return
        action_id = item.data(Qt.UserRole)
        action = next(
            (entry for entry in self._actions if entry.action_id == action_id),
            None,
        )
        if not action:
            return
        header = f"{action.title} | {to_jalali_datetime(action.created_at)}"
        self.details_label.setText(header)
        self._show_action_details(action)

    def _show_action_details(self, action: ActionEntry) -> None:
        rendered: str | None = None
        if action.action_type == "inventory_edit":
            rendered = self._render_inventory_edit_details(action.details)
        if not rendered:
            rendered = self._render_structured_action_details(action.details)
        if rendered:
            self._set_html_details(self._wrap_action_body(action, rendered))
            return
        plain = escape(action.details or "")
        fallback = (
            "<div class='action-root'>"
            "<div class='action-card'>"
            "<div class='action-text'>" + plain.replace("\n", "<br>") + "</div>"
            "</div>"
            "</div>"
        )
        self._set_html_details(self._wrap_action_body(action, fallback))

    def _set_html_details(self, body_html: str) -> None:
        font_roles = resolve_export_font_roles()
        font_stack = format_html_font_stack(
            [font_roles["body"], font_roles["header"], font_roles["title"]]
        )
        html = (
            "<html><head><meta charset='utf-8'>"
            "<style>"
            "body{font-family:"
            + font_stack
            + "; text-align:right; margin:0; padding:0;}"
            ".action-shell{padding:2px 0 4px 0;}"
            ".action-meta{margin-bottom:10px; padding:4px 6px; border:1px solid #e2e8f0; border-radius:10px; background:#f8fafc;}"
            ".action-meta-table{width:100%; border-collapse:separate; border-spacing:6px 2px; table-layout:fixed;}"
            ".action-meta-table td{text-align:right; vertical-align:middle;}"
            ".action-meta-type-cell{width:34%;}"
            ".action-meta-admin-cell{width:33%;}"
            ".action-meta-date-cell{width:33%;}"
            ".action-chip{display:inline-block; padding:4px 10px; border-radius:999px; font-size:12px; font-weight:700; border:1px solid transparent; white-space:nowrap;}"
            ".action-chip-type{background:#e0ecff; color:#1d4ed8; border-color:#bfdbfe;}"
            ".action-chip-admin{background:#f1f5f9; color:#334155; border-color:#cbd5e1;}"
            ".action-chip-date{background:#f8fafc; color:#475569; border-color:#e2e8f0;}"
            ".action-main-title{margin-bottom:12px; padding:8px 12px; border-radius:10px; border:1px solid #dbeafe; background:#f8fbff; color:#0f172a; font-weight:700; line-height:1.75;}"
            ".action-root{display:block; color:#0f172a;}"
            ".action-card{margin-top:12px; padding:12px; border:1px solid #cbd5e1; border-radius:10px; background:#f8fafc;}"
            ".action-card:first-child{margin-top:0;}"
            ".action-card-title{font-weight:700; margin-bottom:8px; color:#0f172a;}"
            ".action-card-before{border-color:#bfdbfe; background:#eff6ff;}"
            ".action-card-before .action-card-title{color:#1d4ed8;}"
            ".action-card-after{border-color:#bbf7d0; background:#f0fdf4;}"
            ".action-card-after .action-card-title{color:#15803d;}"
            ".action-text{line-height:1.75; white-space:pre-wrap; color:#1f2937;}"
            ".action-subtitle{margin-top:8px; margin-bottom:6px; padding-bottom:4px; border-bottom:1px dashed #cbd5e1; font-weight:700; color:#1e293b;}"
            ".action-note{margin-top:8px; padding:8px 10px; border-radius:8px; border:1px solid #dbeafe; background:#f8fbff; color:#1e40af; font-weight:700; line-height:1.7;}"
            ".action-empty{padding:8px; border:1px dashed #cbd5e1; border-radius:8px; color:#475569; background:#ffffff;}"
            ".action-kv-wrap{margin-top:8px; border:1px solid #d1d5db; border-radius:8px; background:#ffffff; overflow:hidden;}"
            ".action-kv-table{width:100%; border-collapse:collapse; table-layout:fixed;}"
            ".action-kv-table td{border-top:1px solid #e5e7eb; padding:7px 10px; text-align:right; vertical-align:top;}"
            ".action-kv-table tr:first-child td{border-top:none;}"
            ".action-kv-key-cell{width:34%; background:#f8fafc; color:#334155; font-weight:700;}"
            ".action-kv-value-cell{width:66%; color:#0f172a; unicode-bidi:plaintext;}"
            ".action-list{margin:8px 0 0 0; padding-right:18px; color:#1f2937;}"
            ".action-list li{margin:4px 0;}"
            ".action-table-wrap{margin-top:8px; border:1px solid #d1d5db; border-radius:8px; background:#ffffff; overflow:hidden;}"
            ".action-table{width:100%; border-collapse:collapse; table-layout:fixed;}"
            ".action-table th,.action-table td{text-align:right; vertical-align:top; border:1px solid #e5e7eb; padding:6px 8px;}"
            ".action-table th{background:#f3f4f6; font-weight:700; color:#0f172a;}"
            ".action-table tbody tr:nth-child(even){background:#f8fafc;}"
            "</style></head><body>" + body_html + "</body></html>"
        )
        self.details_text.setHtml(html)
        self.details_text.setAlignment(Qt.AlignRight)

    def _render_inventory_edit_details(self, details: str) -> str | None:
        text = str(details or "").strip()
        if not text:
            return None
        blocks = [part.strip() for part in text.split("\n\n") if part.strip()]
        if len(blocks) < 2:
            return None

        summary = blocks[0]
        section_html: list[str] = []
        for block in blocks[1:]:
            lines = [
                line.strip() for line in block.splitlines() if line.strip()
            ]
            if not lines:
                continue

            title = lines[0]
            try:
                before_idx = lines.index("قبل:")
                after_idx = lines.index("بعد:")
            except ValueError:
                continue
            if after_idx <= before_idx:
                continue

            before_lines = lines[before_idx + 1 : after_idx]
            after_lines = lines[after_idx + 1 :]

            before_table = self._inventory_snapshot_to_html(before_lines)
            after_table = self._inventory_snapshot_to_html(after_lines)
            section_html.append(
                "<div style='margin-top:12px; padding:12px; border:1px solid #cbd5e1; border-radius:10px; background:#f8fafc; direction:rtl; text-align:right;'>"
                f"<div style='font-weight:700; margin-bottom:10px;'>{escape(title)}</div>"
                "<div style='margin-bottom:12px; padding:8px; border:1px solid #d1d5db; border-radius:8px; background:#ffffff;'>"
                "<div style='font-weight:700; margin-bottom:8px;'>قبل</div>"
                f"{before_table}"
                "</div>"
                "<div style='padding:8px; border:1px solid #d1d5db; border-radius:8px; background:#ffffff;'>"
                "<div style='font-weight:700; margin-bottom:8px;'>بعد</div>"
                f"{after_table}"
                "</div>"
                "</div>"
            )

        if not section_html:
            return None

        return (
            "<div style='text-align:right;'>"
            f"<div style='font-weight:700; margin-bottom:10px; line-height:1.6;'>{escape(summary)}</div>"
            + "".join(section_html)
            + "</div>"
        )

    def _wrap_action_body(self, action: ActionEntry, body_html: str) -> str:
        action_type = self._format_action(action)
        admin = action.admin_username or self.tr("نامشخص")
        created_at = to_jalali_datetime(action.created_at)
        return (
            "<div class='action-shell'>"
            "<div class='action-meta'>"
            "<table class='action-meta-table'><tr>"
            "<td class='action-meta-type-cell'>"
            "<span class='action-chip action-chip-type'>"
            + escape(self.tr("نوع: {type}").format(type=action_type))
            + "</span>"
            "</td>"
            "<td class='action-meta-admin-cell'>"
            "<span class='action-chip action-chip-admin'>"
            + escape(self.tr("ادمین: {admin}").format(admin=admin))
            + "</span>"
            "</td>"
            "<td class='action-meta-date-cell'>"
            "<span class='action-chip action-chip-date'>"
            + escape(self.tr("تاریخ: {date}").format(date=created_at))
            + "</span>"
            "</td>"
            "</tr></table>"
            "</div>"
            "<div class='action-main-title'>"
            + escape(action.title or action_type)
            + "</div>"
            + body_html
            + "</div>"
        )

    def _inventory_snapshot_to_html(self, lines: list[str]) -> str:
        if not lines:
            return (
                "<div style='padding:8px; border:1px dashed #cbd5e1; "
                "border-radius:6px; color:#475569;'>(هیچ)</div>"
            )
        marker = lines[0].strip()
        if marker in {"(هیچ)", "(وجود ندارد)", "(حذف شد)"}:
            return (
                "<div style='padding:8px; border:1px dashed #cbd5e1; "
                "border-radius:6px; color:#475569;'>"
                + escape(marker)
                + "</div>"
            )

        header_parts = [part.strip() for part in lines[0].split("|")]
        value_parts: list[str] = []
        if len(lines) > 1:
            value_parts = [part.strip() for part in lines[1].split("|")]
        if not value_parts:
            value_parts = [""] * len(header_parts)
        if len(value_parts) < len(header_parts):
            value_parts.extend([""] * (len(header_parts) - len(value_parts)))
        if len(value_parts) > len(header_parts):
            value_parts = value_parts[: len(header_parts)]
        # QTextEdit rich-text tables often ignore RTL column flow; reverse explicitly.
        header_parts = list(reversed(header_parts))
        value_parts = list(reversed(value_parts))

        head_html = "".join(
            "<th style='border:1px solid #d1d5db; background:#f3f4f6; padding:6px; text-align:right;'>"
            f"{escape(part)}"
            "</th>"
            for part in header_parts
        )
        row_html = "".join(
            "<td style='border:1px solid #d1d5db; padding:6px; text-align:right;'>"
            f"{escape(part)}"
            "</td>"
            for part in value_parts
        )
        return (
            "<div style='display:block; width:100%;'>"
            "<table width='100%' cellspacing='0' cellpadding='0' "
            "style='width:100%; border-collapse:collapse; table-layout:fixed;'>"
            f"<tr>{head_html}</tr><tr>{row_html}</tr>"
            "</table>"
            "</div>"
        )

    def _render_structured_action_details(self, details: str) -> str | None:
        text = str(details or "").strip()
        if not text:
            return None

        blocks = [part.strip() for part in text.split("\n\n") if part.strip()]
        if not blocks:
            blocks = [text]

        cards: list[str] = []
        for block in blocks:
            lines = [
                line.strip() for line in block.splitlines() if line.strip()
            ]
            if not lines:
                continue

            lead_lines, sections = self._extract_before_after_sections(lines)
            if lead_lines:
                cards.append(self._render_detail_card(None, lead_lines))
            if sections:
                for title, section_lines in sections:
                    cards.append(self._render_detail_card(title, section_lines))
                continue

            cards.append(self._render_detail_card(None, lines))

        if not cards:
            return None

        return "<div class='action-root'>" + "".join(cards) + "</div>"

    def _extract_before_after_sections(
        self, lines: list[str]
    ) -> tuple[list[str], list[tuple[str, list[str]]]]:
        lead_lines: list[str] = []
        sections: list[tuple[str, list[str]]] = []
        current_title: str | None = None
        current_lines: list[str] = []

        for line in lines:
            marker = self._section_marker(line)
            if marker:
                if current_title is not None:
                    sections.append((current_title, current_lines))
                elif current_lines:
                    lead_lines.extend(current_lines)
                current_title = marker
                current_lines = []
                continue
            current_lines.append(line)

        if current_title is not None:
            sections.append((current_title, current_lines))
        elif current_lines:
            lead_lines.extend(current_lines)

        return lead_lines, sections

    def _section_marker(self, line: str) -> str | None:
        normalized = line.strip().rstrip(":").strip().lower()
        if normalized in {"before", "قبل"}:
            return self.tr("قبل")
        if normalized in {"after", "بعد"}:
            return self.tr("بعد")
        return None

    def _render_detail_card(self, title: str | None, lines: list[str]) -> str:
        card_class = "action-card"
        if title:
            normalized = title.strip().lower()
            if normalized in {"قبل", "before"}:
                card_class += " action-card-before"
            elif normalized in {"بعد", "after"}:
                card_class += " action-card-after"
        title_html = (
            "<div class='action-card-title'>" + escape(title) + "</div>"
            if title
            else ""
        )
        body_html = self._render_detail_lines(lines)
        return (
            "<div class='"
            + card_class
            + "'>"
            + title_html
            + body_html
            + "</div>"
        )

    def _render_detail_lines(self, lines: list[str]) -> str:
        clean_lines = [line.strip() for line in lines if line.strip()]
        if not clean_lines:
            return "<div class='action-empty'>(هیچ)</div>"

        marker_set = {"(هیچ)", "(وجود ندارد)", "(حذف شد)"}
        if len(clean_lines) == 1 and clean_lines[0] in marker_set:
            return (
                "<div class='action-empty'>" + escape(clean_lines[0]) + "</div>"
            )

        segments: list[tuple[str, list[object]]] = []

        def append_segment(kind: str, item: object) -> None:
            if segments and segments[-1][0] == kind:
                segments[-1][1].append(item)
            else:
                segments.append((kind, [item]))

        for line in clean_lines:
            if line in marker_set:
                append_segment("empty", line)
                continue

            line_item = self._parse_line_item(line)
            if line_item is not None:
                append_segment("line_items", line_item)
                continue

            if line.startswith("- "):
                append_segment("bullets", line[2:].strip())
                continue
            if line.startswith("• "):
                append_segment("bullets", line[2:].strip())
                continue
            if line.startswith("تغییر موجودی:"):
                append_segment("note", line)
                continue
            if line.endswith(":") and len(line.rstrip(":").strip()) >= 2:
                append_segment("subtitle", line.rstrip(":").strip())
                continue

            pair = self._split_key_value_line(line)
            if pair is not None:
                append_segment("kv", pair)
                continue

            append_segment("text", line)

        html_parts: list[str] = []
        for kind, values in segments:
            if kind == "kv":
                pairs = [
                    pair
                    for pair in values
                    if isinstance(pair, tuple) and len(pair) == 2
                ]
                html_parts.append(self._render_key_value_table(pairs))
                continue

            if kind == "line_items":
                rows = [row for row in values if isinstance(row, list)]
                html_parts.append(self._render_line_items_table(rows))
                continue

            if kind == "bullets":
                items = "".join(
                    "<li>" + escape(str(item)) + "</li>"
                    for item in values
                    if str(item).strip()
                )
                if items:
                    html_parts.append(
                        "<ul class='action-list'>" + items + "</ul>"
                    )
                continue

            if kind == "subtitle":
                html_parts.extend(
                    "<div class='action-subtitle'>"
                    + escape(str(value))
                    + "</div>"
                    for value in values
                    if str(value).strip()
                )
                continue

            if kind == "note":
                html_parts.extend(
                    "<div class='action-note'>" + escape(str(value)) + "</div>"
                    for value in values
                    if str(value).strip()
                )
                continue

            if kind == "empty":
                html_parts.extend(
                    "<div class='action-empty'>" + escape(str(value)) + "</div>"
                    for value in values
                )
                continue

            text_html = "<br>".join(
                escape(str(value)) for value in values if str(value).strip()
            )
            if text_html:
                html_parts.append(
                    "<div class='action-text'>" + text_html + "</div>"
                )

        if not html_parts:
            return "<div class='action-empty'>(هیچ)</div>"
        return "".join(html_parts)

    def _render_key_value_table(self, rows: list[tuple[str, str]]) -> str:
        if not rows:
            return ""
        row_html = "".join(
            "<tr><td class='action-kv-key-cell'>"
            + escape(key)
            + "</td><td class='action-kv-value-cell'>"
            + escape(value)
            + "</td></tr>"
            for key, value in rows
        )
        return (
            "<div class='action-kv-wrap'><table class='action-kv-table'>"
            + row_html
            + "</table></div>"
        )

    def _render_line_items_table(
        self, rows: list[list[tuple[str, str]]]
    ) -> str:
        if not rows:
            return ""

        columns: list[str] = []
        for row in rows:
            for key, _ in row:
                if key not in columns:
                    columns.append(key)
        if not columns:
            return ""

        display_columns = list(reversed(columns))
        head_html = "".join(
            "<th>" + escape(column) + "</th>" for column in display_columns
        )

        body_rows: list[str] = []
        for row in rows:
            row_map = {key: value for key, value in row}
            cell_html = "".join(
                "<td>" + escape(str(row_map.get(column, "-"))) + "</td>"
                for column in display_columns
            )
            body_rows.append("<tr>" + cell_html + "</tr>")

        return (
            "<div class='action-table-wrap'>"
            "<table class='action-table'>"
            "<thead><tr>" + head_html + "</tr></thead>"
            "<tbody>" + "".join(body_rows) + "</tbody></table></div>"
        )

    def _parse_line_item(self, line: str) -> list[tuple[str, str]] | None:
        parts = [part.strip() for part in line.split("|") if part.strip()]
        if not parts:
            return None
        match = re.match(r"^(\d+)\)\s*(.+)$", parts[0])
        if not match:
            return None

        row: list[tuple[str, str]] = [
            (self.tr("ردیف"), match.group(1).strip()),
            (self.tr("کالا"), match.group(2).strip()),
        ]
        for part in parts[1:]:
            pair = self._split_key_value_line(part)
            if pair is not None:
                row.append(pair)
            else:
                row.append((self.tr("شرح"), part))
        return row

    def _split_key_value_line(self, line: str) -> tuple[str, str] | None:
        if ":" not in line:
            return None
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if len(key) < 2 or not value:
            return None
        if re.fullmatch(r"[0-9۰-۹\-/\s.]+", key):
            return None
        return key, value

    def _maybe_load_more(self) -> None:
        if self._loading_more or self._loaded_count >= self._total_count:
            return
        bar = self.table.verticalScrollBar()
        if bar.maximum() == 0:
            return
        if bar.value() >= bar.maximum() - 20:
            self._load_more()

    def _load_more(self) -> None:
        if self._loading_more or self._loaded_count >= self._total_count:
            self.load_more_button.setEnabled(False)
            return
        self._loading_more = True
        search = self.search_input.text().strip()
        batch = self.action_service.list_actions(
            limit=self._page_size,
            offset=self._loaded_count,
            search=search if search else None,
        )
        if not batch:
            self._loading_more = False
            self.load_more_button.setEnabled(False)
            return

        start_row = self.table.rowCount()
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        self.table.setRowCount(start_row + len(batch))
        for row_offset, entry in enumerate(batch):
            row_idx = start_row + row_offset
            date_item = QTableWidgetItem(to_jalali_datetime(entry.created_at))
            date_item.setData(Qt.UserRole, entry.action_id)
            self.table.setItem(row_idx, 0, date_item)
            admin_text = entry.admin_username or self.tr("نامشخص")
            self.table.setItem(row_idx, 1, QTableWidgetItem(admin_text))
            self.table.setItem(
                row_idx, 2, QTableWidgetItem(self._format_action(entry))
            )
            self.table.setItem(row_idx, 3, QTableWidgetItem(entry.title))
        self._actions.extend(batch)
        self._loaded_count += len(batch)
        self.table.blockSignals(False)
        self.table.setUpdatesEnabled(True)
        self._loading_more = False
        self.load_more_button.setEnabled(self._loaded_count < self._total_count)
        if start_row == 0 and self._actions:
            self.table.selectRow(0)

    def _format_action(self, entry: ActionEntry) -> str:
        t = lambda text: QCoreApplication.translate(  # noqa: E731
            "ActionsPage", text
        )
        mapping = {
            "sales_import": t("ثبت فروش"),
            "sales_manual_invoice": t("ثبت فاکتور فروش دستی"),
            "sales_import_export": t("خروجی مغایرت‌های فروش"),
            "purchase_invoice": t("ثبت فاکتور خرید"),
            "inventory_edit": t("ویرایش موجودی"),
            "invoice_edit": t("ویرایش فاکتور"),
            "invoice_delete": t("حذف فاکتور"),
            "invoice_product_rename": t("به‌روزرسانی نام کالا در فاکتورها"),
            "invoice_export": t("خروجی فاکتور"),
            "invoice_batch_export": t("خروجی گروهی فاکتورها"),
            "low_stock_export": t("خروجی کمبود موجودی"),
            "inventory_export": t("خروجی موجودی"),
            "basalam_fetch": t("دریافت باسلام"),
            "basalam_export": t("خروجی باسلام"),
            "password_change": t("تغییر رمز عبور"),
            "auto_lock_update": t("تغییر قفل خودکار"),
            "admin_create": t("ایجاد ادمین"),
            "admin_delete": t("حذف ادمین"),
            "reports_export": t("خروجی گزارش"),
            "login": t("ورود"),
            "logout": t("خروج"),
        }
        return mapping.get(entry.action_type, entry.action_type)
