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
        self.body_area.setStyleSheet(
            "QScrollArea#HelpBody { border: none; background: transparent; }"
        )

        self.body = QLabel()
        self.body.setObjectName("HelpBodyText")
        self.body.setTextFormat(Qt.RichText)
        self.body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.body.setLayoutDirection(Qt.RightToLeft)
        self.body.setAlignment(Qt.AlignTop | Qt.AlignRight | Qt.AlignAbsolute)
        self.body.setWordWrap(True)
        self.body.setMargin(10)
        self.body.setStyleSheet("background: transparent; font-size: 14px;")

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
        self.body.setText(self._html_to_rich_rtl_text(body_html))

    @staticmethod
    def _html_to_rich_rtl_text(html_text: str) -> str:
        text = html.unescape(html_text)

        def _render_list(inner_html: str, ordered: bool) -> str:
            items = re.findall(
                r"<li[^>]*>(.*?)</li>",
                inner_html,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if not items:
                return ""
            lines: list[str] = []
            for idx, item in enumerate(items, 1):
                marker = f"{idx}." if ordered else "•"
                lines.append(
                    '<p dir="rtl" align="right" style="margin: 0 0 8px 0;">'
                    f"<b>{marker}</b> {item.strip()}</p>"
                )
            return "".join(lines)

        text = re.sub(
            r"<\s*code[^>]*>(.*?)</\s*code\s*>",
            lambda m: (
                '<span style="font-family: monospace; direction: ltr; '
                'unicode-bidi: embed;">' + m.group(1).strip() + "</span>"
            ),
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        text = re.sub(
            r"<\s*p[^>]*>(.*?)</\s*p\s*>",
            lambda m: (
                '<p dir="rtl" align="right" style="margin: 0 0 12px 0;">'
                + m.group(1).strip()
                + "</p>"
            ),
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        text = re.sub(
            r"<\s*h3[^>]*>(.*?)</\s*h3\s*>",
            lambda m: (
                '<p dir="rtl" align="right" '
                'style="margin: 14px 0 10px 0; font-size: 21px;"><b>'
                + m.group(1).strip()
                + "</b></p>"
            ),
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        text = re.sub(
            r"<ol[^>]*>(.*?)</ol>",
            lambda m: _render_list(m.group(1), ordered=True),
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        text = re.sub(
            r"<ul[^>]*>(.*?)</ul>",
            lambda m: _render_list(m.group(1), ordered=False),
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        text = re.sub(r"</?\s*div[^>]*>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"<\s*br\s*/?>", "<br/>", text, flags=re.IGNORECASE)
        text = re.sub(
            r"</?\s*(ul|ol|li)\b[^>]*>", "", text, flags=re.IGNORECASE
        )
        text = re.sub(r"\n{2,}", "\n", text).strip()

        return (
            '<div dir="rtl" style="text-align: right; line-height: 1.95; '
            'unicode-bidi: plaintext;">' + text + "</div>"
        )
