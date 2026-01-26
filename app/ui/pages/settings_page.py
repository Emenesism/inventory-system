from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
        on_theme_changed=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.invoice_service = invoice_service
        self.on_theme_changed = on_theme_changed

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

        pass_row = QHBoxLayout()
        pass_label = QLabel("Passcode:")
        pass_row.addWidget(pass_label)

        self.passcode_input = QLineEdit()
        self.passcode_input.setEchoMode(QLineEdit.Password)
        self.passcode_input.setPlaceholderText("Default: 1111")
        self.passcode_input.setText(self.config.passcode or "1111")
        pass_row.addWidget(self.passcode_input, 1)

        save_button = QPushButton("Save")
        save_button.clicked.connect(self._save_passcode)
        pass_row.addWidget(save_button)

        reset_button = QPushButton("Reset")
        reset_button.clicked.connect(self._reset_passcode)
        pass_row.addWidget(reset_button)

        card_layout.addLayout(pass_row)

        theme_row = QHBoxLayout()
        theme_label = QLabel("Theme:")
        theme_row.addWidget(theme_label)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Light", "Dark"])
        self.theme_combo.setCurrentText(
            "Dark" if self.config.theme == "dark" else "Light"
        )
        self.theme_combo.currentTextChanged.connect(self._apply_theme)
        theme_row.addWidget(self.theme_combo)
        theme_row.addStretch(1)

        card_layout.addLayout(theme_row)
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

    def _save_passcode(self) -> None:
        code = self.passcode_input.text().strip() or "1111"
        self.config.passcode = code
        self.config.save()
        self.passcode_input.setText(code)

    def _reset_passcode(self) -> None:
        self.config.passcode = "1111"
        self.config.save()
        self.passcode_input.setText("1111")

    def _apply_theme(self, value: str) -> None:
        self.config.theme = "dark" if value == "Dark" else "light"
        self.config.save()
        if self.on_theme_changed:
            self.on_theme_changed(self.config.theme)
