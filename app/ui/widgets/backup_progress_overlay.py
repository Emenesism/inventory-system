from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer, Slot
from PySide6.QtWidgets import QFrame, QLabel, QProgressBar, QVBoxLayout, QWidget


class BackupProgressOverlay(QFrame):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        self.status_label = QLabel("در حال آماده‌سازی نسخه پشتیبان...")
        self.status_label.setProperty("textRole", "muted")
        self.status_label.setWordWrap(True)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFixedHeight(14)
        self.progress_bar.setTextVisible(False)

        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)

        self._close_timer = QTimer(self)
        self._close_timer.setSingleShot(True)
        self._close_timer.timeout.connect(self.hide)

        parent.installEventFilter(self)

    def show_overlay(self) -> None:
        self._close_timer.stop()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setValue(0)
        self.adjustSize()
        self._reposition()
        self.raise_()
        self.show()

    @Slot(str)
    def set_status(self, text: str) -> None:
        self.status_label.setText(text)
        self.adjustSize()
        self._reposition()

    @Slot(bool, str)
    def mark_finished(self, success: bool, message: str) -> None:
        self.status_label.setText(message)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1 if success else 0)
        self.adjustSize()
        self._reposition()
        self._close_timer.start(1500)

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if not parent:
            return
        x = int((parent.width() - self.width()) / 2)
        y = int((parent.height() - self.height()) / 2)
        self.move(max(x, 0), max(y, 0))

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self.parentWidget() and event.type() in {
            QEvent.Resize,
            QEvent.Move,
        }:
            self._reposition()
        return super().eventFilter(obj, event)
