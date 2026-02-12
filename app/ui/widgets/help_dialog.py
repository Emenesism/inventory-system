from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


class HelpDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HelpDialog")
        self.setWindowTitle(self.tr("راهنما"))
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(960, 640)
        self.setMinimumSize(860, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        self.title_label = QLabel(self.tr("راهنما"))
        self.title_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.title_label.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(self.title_label)

        self.body = QTextBrowser()
        self.body.setObjectName("HelpBody")
        self.body.setReadOnly(True)
        self.body.setOpenExternalLinks(False)
        self.body.setLayoutDirection(Qt.RightToLeft)
        self.body.setStyleSheet("font-size: 13px;")
        option = self.body.document().defaultTextOption()
        option.setAlignment(Qt.AlignRight)
        option.setTextDirection(Qt.RightToLeft)
        self.body.document().setDefaultTextOption(option)
        layout.addWidget(self.body, 1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        close_button = QPushButton(self.tr("بستن"))
        close_button.clicked.connect(self.accept)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

    def set_content(self, title: str, body_html: str) -> None:
        self.title_label.setText(title)
        self.body.setHtml(body_html)
