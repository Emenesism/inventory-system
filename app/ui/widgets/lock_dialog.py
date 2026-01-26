from __future__ import annotations

from PySide6.QtCore import QRegularExpression, Qt
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
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
            Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.setStyleSheet(
            """
            QDialog {
                background: rgba(15, 23, 42, 0.55);
            }
            QFrame#LockCard {
                background: #F8FAFC;
                border-radius: 16px;
                padding: 8px;
                min-width: 320px;
            }
            QLabel#LockTitle {
                color: #0F172A;
                font-size: 18px;
                font-weight: 700;
            }
            QLabel#LockHint {
                color: #64748B;
                font-size: 12px;
            }
            QLabel#LockError {
                color: #DC2626;
                font-size: 12px;
            }
            """
        )

        card = QFrame()
        card.setObjectName("LockCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(12)

        wrapper = QVBoxLayout()
        wrapper.addStretch(1)
        wrapper.addWidget(card, 0, Qt.AlignHCenter)
        wrapper.addStretch(1)
        layout.addLayout(wrapper)

        title = QLabel("Enter Passcode")
        title.setObjectName("LockTitle")
        card_layout.addWidget(title)

        hint = QLabel("This app is locked.")
        hint.setObjectName("LockHint")
        card_layout.addWidget(hint)

        self.input = QLineEdit()
        self.input.setEchoMode(QLineEdit.Password)
        self.input.setPlaceholderText("Passcode")
        validator = QRegularExpressionValidator(
            QRegularExpression(r"\d{0,8}"), self
        )
        self.input.setValidator(validator)
        self.input.returnPressed.connect(self._try_unlock)
        card_layout.addWidget(self.input)

        self.error_label = QLabel("")
        self.error_label.setObjectName("LockError")
        card_layout.addWidget(self.error_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        unlock_button = QPushButton("Unlock")
        unlock_button.clicked.connect(self._try_unlock)
        button_row.addWidget(unlock_button)
        card_layout.addLayout(button_row)

    def _try_unlock(self) -> None:
        if self.input.text() == self._passcode:
            self.accept()
        else:
            self.error_label.setText("Wrong passcode.")
            self.input.selectAll()

    def reject(self) -> None:
        return
