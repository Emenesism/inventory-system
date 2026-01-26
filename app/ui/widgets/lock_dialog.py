from __future__ import annotations

from PySide6.QtCore import QRegularExpression, Qt
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


class LockDialog(QDialog):
    def __init__(self, passcode: str, parent=None) -> None:
        super().__init__(parent)
        self._passcode = passcode or "1111"
        self.setWindowTitle("Locked")
        self.setModal(True)
        self.setWindowFlags(
            Qt.Dialog
            | Qt.CustomizeWindowHint
            | Qt.WindowTitleHint
            | Qt.WindowStaysOnTopHint
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("Enter Passcode")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(title)

        self.input = QLineEdit()
        self.input.setEchoMode(QLineEdit.Password)
        self.input.setPlaceholderText("Passcode")
        validator = QRegularExpressionValidator(
            QRegularExpression(r"\d{0,8}"), self
        )
        self.input.setValidator(validator)
        self.input.returnPressed.connect(self._try_unlock)
        layout.addWidget(self.input)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #DC2626;")
        layout.addWidget(self.error_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        unlock_button = QPushButton("Unlock")
        unlock_button.clicked.connect(self._try_unlock)
        button_row.addWidget(unlock_button)
        layout.addLayout(button_row)

    def _try_unlock(self) -> None:
        if self.input.text() == self._passcode:
            self.accept()
        else:
            self.error_label.setText("Wrong passcode.")
            self.input.selectAll()

    def reject(self) -> None:
        return
