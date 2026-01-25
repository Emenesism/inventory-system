from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("Reports & Logs")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        header.addWidget(title)
        header.addStretch(1)

        refresh_button = QPushButton("Refresh Logs")
        refresh_button.clicked.connect(self.load_logs)
        header.addWidget(refresh_button)

        layout.addLayout(header)

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        card_layout.addWidget(self.log_view)

        layout.addWidget(card)
        self.load_logs()

    def load_logs(self) -> None:
        if self.log_path.exists():
            self.log_view.setPlainText(
                self.log_path.read_text(encoding="utf-8")
            )
        else:
            self.log_view.setPlainText("Log file not found yet.")
