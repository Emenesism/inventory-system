from __future__ import annotations

import logging
import os
from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGraphicsBlurEffect,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services.action_log_service import ActionLogService


class ReportsPage(QWidget):
    def __init__(
        self,
        log_path: Path,
        action_log_service: ActionLogService | None = None,
        current_admin_provider=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.log_path = log_path
        self._logger = logging.getLogger(self.__class__.__name__)
        self._last_loaded_text = ""
        self.action_log_service = action_log_service
        self._current_admin_provider = current_admin_provider

        self._content = QWidget()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel(self.tr("گزارش‌ها و لاگ‌ها"))
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        header.addWidget(title)
        header.addStretch(1)

        refresh_button = QPushButton(self.tr("بارگذاری کامل"))
        refresh_button.clicked.connect(self.load_logs_all)
        header.addWidget(refresh_button)

        tail_button = QPushButton(self.tr("نمایش 1000 خط آخر"))
        tail_button.clicked.connect(self.load_logs_tail)
        header.addWidget(tail_button)

        export_button = QPushButton(self.tr("خروجی 1000 خط آخر"))
        export_button.clicked.connect(self.export_tail)
        header.addWidget(export_button)

        content_layout.addLayout(header)

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        card_layout.addWidget(self.log_view)

        content_layout.addWidget(card)
        layout.addWidget(self._content)

        self._overlay = QFrame(self)
        self._overlay.setStyleSheet(
            "background: rgba(15, 23, 42, 0.55); border-radius: 16px;"
        )
        overlay_layout = QVBoxLayout(self._overlay)
        overlay_layout.setContentsMargins(0, 0, 0, 0)
        overlay_layout.addStretch(1)
        self._overlay.hide()

        self.load_logs_all()
        self.set_accessible(False)

    def load_logs_all(self) -> None:
        text = self._read_all_logs()
        if not text:
            self._set_log_text(self._missing_log_message())
            return
        self._set_log_text(text)
        self._logger.info("Reports loaded full log history")

    def load_logs_tail(self, line_count: int = 1000) -> None:
        lines = self._read_tail_lines(line_count)
        if not lines:
            fallback_text = self._read_all_logs()
            if fallback_text:
                lines = fallback_text.splitlines()[-line_count:]
        if not lines:
            self._set_log_text(self._missing_log_message())
            return
        self._set_log_text("\n".join(lines))
        self._logger.info("Reports loaded last %s lines", line_count)

    def export_tail(self, line_count: int = 1000) -> None:
        lines = self._read_tail_lines(line_count)
        if not lines:
            fallback_text = self._read_all_logs()
            if fallback_text:
                lines = fallback_text.splitlines()[-line_count:]
        if not lines:
            self._set_log_text(self._missing_log_message())
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("خروجی لاگ"),
            f"app_log_tail_{line_count}.txt",
            self.tr("فایل متنی (*.txt);;همه فایل‌ها (*)"),
        )
        if not file_path:
            return
        Path(file_path).write_text("\n".join(lines), encoding="utf-8")
        self._logger.info(
            "Reports exported last %s lines to %s", line_count, file_path
        )
        if self.action_log_service:
            admin = (
                self._current_admin_provider()
                if self._current_admin_provider
                else None
            )
            self.action_log_service.log_action(
                "reports_export",
                self.tr("خروجی گزارش‌ها"),
                self.tr("تعداد خطوط: {count}\nمسیر: {path}").format(
                    count=line_count, path=file_path
                ),
                admin=admin,
            )

    def _set_log_text(self, text: str) -> None:
        self._last_loaded_text = text
        self.log_view.setPlainText(text)

    def _read_all_logs(self) -> str:
        log_paths = self._ordered_log_paths()
        if not log_paths:
            return ""
        parts: list[str] = []
        for path in log_paths:
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                self._logger.exception("Failed reading log file %s", path)
                continue
            if content:
                parts.append(content)
        return "\n".join(parts).strip()

    def _read_tail_lines(self, line_count: int) -> list[str]:
        if line_count <= 0:
            return []
        log_paths = self._ordered_log_paths()
        if not log_paths:
            return []
        needed = line_count
        # Newest file first for tail collection, then restore chronological order.
        newest_first_segments: list[list[str]] = []
        for path in reversed(log_paths):
            if needed <= 0:
                break
            lines = self._read_file_tail_lines(path, needed)
            if not lines:
                continue
            newest_first_segments.append(lines)
            needed -= len(lines)
        if not newest_first_segments:
            return []
        ordered: list[str] = []
        for segment in reversed(newest_first_segments):
            ordered.extend(segment)
        if len(ordered) > line_count:
            return ordered[-line_count:]
        return ordered

    def _read_file_tail_lines(self, path: Path, line_count: int) -> list[str]:
        if line_count <= 0:
            return []
        try:
            with path.open("rb") as handle:
                handle.seek(0, os.SEEK_END)
                position = handle.tell()
                if position <= 0:
                    return []
                data = b""
                newline_count = 0
                chunk_size = 16 * 1024
                while position > 0 and newline_count <= line_count:
                    read_size = min(chunk_size, position)
                    position -= read_size
                    handle.seek(position)
                    chunk = handle.read(read_size)
                    if not chunk:
                        break
                    data = chunk + data
                    newline_count += chunk.count(b"\n")
        except OSError:
            self._logger.exception("Failed reading log file %s", path)
            return []

        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()
        if not lines:
            return []
        if len(lines) > line_count:
            return lines[-line_count:]
        return lines

    def _ordered_log_paths(self) -> list[Path]:
        base = self.log_path
        backups: list[tuple[int, Path]] = []
        for path in base.parent.glob(f"{base.name}.*"):
            suffix = path.name.replace(f"{base.name}.", "")
            if suffix.isdigit():
                backups.append((int(suffix), path))
        backups.sort(reverse=True)
        ordered = [path for _, path in backups]
        if base.exists():
            ordered.append(base)
        return ordered

    def _missing_log_message(self) -> str:
        base_message = self.tr(
            "فایل لاگ هنوز ایجاد نشده است.\nمسیر مورد انتظار: {path}"
        ).format(path=str(self.log_path))
        available = self._available_log_files()
        if not available:
            return base_message
        preview = "\n".join(str(path) for path in available[:6])
        return self.tr("{base}\nفایل‌های پیدا شده:\n{files}").format(
            base=base_message, files=preview
        )

    def _available_log_files(self) -> list[Path]:
        directory = self.log_path.parent
        if not directory.exists():
            return []
        base_name = self.log_path.name
        files = [
            path for path in directory.glob(f"{base_name}*") if path.is_file()
        ]
        files.sort()
        return files

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
