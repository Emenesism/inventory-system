from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ReportsPage(QWidget):
    def __init__(self, log_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.log_path = log_path
        self._logger = logging.getLogger(self.__class__.__name__)
        self._last_loaded_text = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

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

        layout.addLayout(header)

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        card_layout.addWidget(self.log_view)

        layout.addWidget(card)
        self.load_logs_all()

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
