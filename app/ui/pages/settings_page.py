from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.config import AppConfig
from app.services.invoice_service import InvoiceService


class SettingsPage(QWidget):
    def __init__(
        self,
        config: AppConfig,
        invoice_service: InvoiceService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.invoice_service = invoice_service

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Settings")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(title)

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)

        row = QHBoxLayout()
        label = QLabel("Backup folder:")
        row.addWidget(label)

        self.path_label = QLabel(self._current_path_text())
        row.addWidget(self.path_label, 1)

        choose_button = QPushButton("Choose")
        choose_button.clicked.connect(self._choose_folder)
        row.addWidget(choose_button)

        clear_button = QPushButton("Default")
        clear_button.clicked.connect(self._clear_folder)
        row.addWidget(clear_button)

        card_layout.addLayout(row)
        layout.addWidget(card)

        layout.addStretch(1)

    def _current_path_text(self) -> str:
        return self.config.backup_dir or "Same folder as file"

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Backup Folder")
        if not folder:
            return
        self._set_backup_dir(folder)

    def _clear_folder(self) -> None:
        self._set_backup_dir(None)

    def _set_backup_dir(self, path: str | None) -> None:
        self.config.backup_dir = path
        self.config.save()
        backup_dir = Path(path) if path else None
        self.invoice_service.set_backup_dir(backup_dir)
        self.path_label.setText(self._current_path_text())
