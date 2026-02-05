from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from app.services.admin_service import AdminService, AdminUser


class LockDialog(QDialog):
    def __init__(
        self,
        admin_service: AdminService,
        parent=None,
        username: str = "",
    ) -> None:
        super().__init__(parent)
        self._admin_service = admin_service
        self.authenticated_admin: AdminUser | None = None
        self.close_requested = False
        self.setWindowTitle("Locked")
        self.setWindowModality(Qt.WindowModal)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setObjectName("LockDialog")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

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

        title = QLabel("Unlock")
        title.setObjectName("LockTitle")
        card_layout.addWidget(title)

        hint = QLabel("This app is locked.")
        hint.setObjectName("LockHint")
        card_layout.addWidget(hint)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")
        self.username_input.setText(username)
        self.username_input.returnPressed.connect(self._try_unlock)
        card_layout.addWidget(self.username_input)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Password")
        self.password_input.returnPressed.connect(self._try_unlock)
        card_layout.addWidget(self.password_input)

        self.error_label = QLabel("")
        self.error_label.setObjectName("LockError")
        card_layout.addWidget(self.error_label)

        button_row = QHBoxLayout()
        close_button = QPushButton("Close app")
        close_button.clicked.connect(self._close_app)
        close_button.setAutoDefault(False)
        close_button.setDefault(False)
        button_row.addWidget(close_button)
        button_row.addStretch(1)
        unlock_button = QPushButton("Unlock")
        unlock_button.clicked.connect(self._try_unlock)
        unlock_button.setDefault(True)
        unlock_button.setAutoDefault(True)
        button_row.addWidget(unlock_button)
        card_layout.addLayout(button_row)

        if not username:
            self.username_input.setFocus()
        else:
            self.password_input.setFocus()

    def _try_unlock(self) -> None:
        username = self.username_input.text().strip()
        password = self.password_input.text()
        admin = self._admin_service.authenticate(username, password)
        if admin is not None:
            self.authenticated_admin = admin
            self.accept()
            return
        self.error_label.setText("Wrong username or password.")
        self.password_input.selectAll()
        self.password_input.setFocus()

    def _close_app(self) -> None:
        self.close_requested = True
        QDialog.reject(self)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.close_requested:
            super().closeEvent(event)
            return
        event.ignore()

    def reject(self) -> None:
        return
