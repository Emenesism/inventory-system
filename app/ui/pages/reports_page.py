from __future__ import annotations

import logging
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
        title = QLabel("Reports & Logs")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        header.addWidget(title)
        header.addStretch(1)

        refresh_button = QPushButton("Refresh All")
        refresh_button.clicked.connect(self.load_logs_all)
        header.addWidget(refresh_button)

        tail_button = QPushButton("Show Last 1000")
        tail_button.clicked.connect(self.load_logs_tail)
        header.addWidget(tail_button)

        export_button = QPushButton("Export Last 1000")
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
            self._set_log_text("Log file not found yet.")
            return
        self._set_log_text(text)
        self._logger.info("Reports loaded full log history")

    def load_logs_tail(self, line_count: int = 1000) -> None:
        lines = self._read_all_logs().splitlines()
        if not lines:
            self._set_log_text("Log file not found yet.")
            return
        tail = lines[-line_count:]
        self._set_log_text("\n".join(tail))
        self._logger.info("Reports loaded last %s lines", line_count)

    def export_tail(self, line_count: int = 1000) -> None:
        lines = self._read_all_logs().splitlines()
        if not lines:
            self._set_log_text("Log file not found yet.")
            return
        tail = lines[-line_count:]
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Log Tail",
            f"app_log_tail_{line_count}.txt",
            "Text Files (*.txt);;All Files (*)",
        )
        if not file_path:
            return
        Path(file_path).write_text("\n".join(tail), encoding="utf-8")
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
                "خروجی گزارش‌ها",
                f"تعداد خطوط: {line_count}\nمسیر: {file_path}",
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

    def _ordered_log_paths(self) -> list[Path]:
        if not self.log_path.exists():
            return []
        base = self.log_path
        backups: list[tuple[int, Path]] = []
        for path in base.parent.glob(f"{base.name}.*"):
            suffix = path.name.replace(f"{base.name}.", "")
            if suffix.isdigit():
                backups.append((int(suffix), path))
        backups.sort(reverse=True)
        ordered = [path for _, path in backups]
        ordered.append(base)
        return ordered

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
