from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QWidget,
)


class HeaderBar(QFrame):
    lock_requested = Signal()
    help_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HeaderBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(10)

        title = QLabel(self.tr("حسابداری و انبار"))
        title.setObjectName("AppTitle")
        layout.addWidget(title)

        self.status_label = QLabel(self.tr("موجودی بارگذاری نشده است"))
        self.status_label.setObjectName("StatusLabel")
        layout.addWidget(self.status_label)
        layout.addStretch(1)

        self.lock_button = QToolButton()
        self.lock_button.setObjectName("LockButton")
        self.lock_button.setText(self.tr("قفل"))
        self.lock_button.setToolTip(self.tr("قفل برنامه"))
        self.lock_button.clicked.connect(self.lock_requested.emit)
        layout.addWidget(self.lock_button)

        self.help_button = QToolButton()
        self.help_button.setObjectName("HelpButton")
        self.help_button.setText("؟")
        self.help_button.setToolTip(self.tr("راهنما"))
        self.help_button.clicked.connect(self.help_requested.emit)
        layout.addWidget(self.help_button)

    def set_status(self, message: str) -> None:
        self.status_label.setText(message)

    def set_theme_label(self, theme: str) -> None:
        pass
