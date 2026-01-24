from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class Toast(QFrame):
    def __init__(self, message: str, kind: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setProperty("toastType", kind)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        label = QLabel(message)
        label.setWordWrap(True)
        layout.addWidget(label)

        self.adjustSize()

    def show_for(self, duration_ms: int = 2800) -> None:
        self.show()
        QTimer.singleShot(duration_ms, self.close)


class ToastManager:
    def __init__(self, parent: QWidget) -> None:
        self.parent = parent

    def show(self, message: str, kind: str = "info") -> None:
        toast = Toast(message, kind, self.parent)
        toast.adjustSize()
        margin = 24
        x = self.parent.width() - toast.width() - margin
        y = self.parent.height() - toast.height() - margin
        toast.move(max(x, margin), max(y, margin))
        toast.raise_()
        toast.show_for()
