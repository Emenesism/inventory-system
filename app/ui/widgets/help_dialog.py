from __future__ import annotations

import html
import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
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
        # Use AlignAbsolute so visual-right stays right in RTL locale.
        self.title_label.setAlignment(
            Qt.AlignRight | Qt.AlignAbsolute | Qt.AlignVCenter
        )
        self.title_label.setStyleSheet("font-size: 20px; font-weight: 700;")
        layout.addWidget(self.title_label)

        self.body_area = QScrollArea()
        self.body_area.setObjectName("HelpBody")
        self.body_area.setWidgetResizable(True)
        self.body_area.setFrameShape(QFrame.NoFrame)
        self.body_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.body_area.setLayoutDirection(Qt.RightToLeft)

        self.body = QLabel()
        self.body.setObjectName("HelpBodyText")
        self.body.setTextFormat(Qt.PlainText)
        self.body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.body.setLayoutDirection(Qt.RightToLeft)
        self.body.setAlignment(Qt.AlignTop | Qt.AlignRight | Qt.AlignAbsolute)
        self.body.setWordWrap(True)
        self.body.setMargin(10)

        self.body_area.setWidget(self.body)
        layout.addWidget(self.body_area, 1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        close_button = QPushButton(self.tr("بستن"))
        close_button.clicked.connect(self.accept)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

    def set_content(self, title: str, body_html: str) -> None:
        self.title_label.setText(title)
        self.body.setText(self._html_to_plain_rtl_text(body_html))

    @staticmethod
    def _html_to_plain_rtl_text(html_text: str) -> str:
        text = html_text

        def _replace_ol(match) -> str:  # noqa: ANN001
            inner = match.group(1)
            items = re.findall(
                r"<li[^>]*>(.*?)</li>", inner, flags=re.IGNORECASE | re.DOTALL
            )
            if not items:
                return "\n"
            lines = [
                f"{idx}. {item.strip()}" for idx, item in enumerate(items, 1)
            ]
            return "\n" + "\n".join(lines) + "\n"

        def _replace_ul(match) -> str:  # noqa: ANN001
            inner = match.group(1)
            items = re.findall(
                r"<li[^>]*>(.*?)</li>", inner, flags=re.IGNORECASE | re.DOTALL
            )
            if not items:
                return "\n"
            lines = [f"• {item.strip()}" for item in items]
            return "\n" + "\n".join(lines) + "\n"

        text = re.sub(
            r"<ol[^>]*>(.*?)</ol>",
            _replace_ol,
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        text = re.sub(
            r"<ul[^>]*>(.*?)</ul>",
            _replace_ul,
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        text = re.sub(r"<\s*br\s*/?>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"</\s*h3\s*>", "\n\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<\s*h3[^>]*>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"</\s*p\s*>", "\n\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<\s*p[^>]*>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"</?\s*div[^>]*>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<\s*code[^>]*>", "`", text, flags=re.IGNORECASE)
        text = re.sub(r"</\s*code\s*>", "`", text, flags=re.IGNORECASE)
        text = re.sub(r"<\s*/?\s*(strong|b)\s*>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text, flags=re.IGNORECASE)
        text = html.unescape(text).replace("\xa0", " ")

        lines = [line.strip() for line in text.splitlines()]
        normalized: list[str] = []
        previous_blank = False
        for line in lines:
            if not line:
                if not previous_blank:
                    normalized.append("")
                previous_blank = True
                continue
            normalized.append("\u200f" + line)
            previous_blank = False

        return "\n".join(normalized).strip()
