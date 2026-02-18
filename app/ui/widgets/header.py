from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QWidget,
)


class HeaderBar(QFrame):
    lock_requested = Signal()
    help_requested = Signal()
    menu_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HeaderBar")
        self._chrome_mode: str | None = None

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(20, 10, 20, 10)
        self._layout.setSpacing(10)

        self.menu_button = QToolButton()
        self.menu_button.setObjectName("MenuButton")
        self.menu_button.setText(self.tr("منو"))
        self.menu_button.setToolTip(self.tr("نمایش/پنهان کردن نوار کناری"))
        self.menu_button.clicked.connect(self.menu_requested.emit)
        self.menu_button.setVisible(False)
        self._layout.addWidget(self.menu_button)

        title = QLabel(self.tr("حسابداری و انبار"))
        title.setObjectName("AppTitle")
        self._layout.addWidget(title)

        self.status_label = QLabel(self.tr("موجودی بارگذاری نشده است"))
        self.status_label.setObjectName("StatusLabel")
        self._layout.addWidget(self.status_label)
        self._layout.addStretch(1)

        self.lock_button = QToolButton()
        self.lock_button.setObjectName("LockButton")
        self.lock_button.setText(self.tr("قفل"))
        self.lock_button.setToolTip(self.tr("قفل برنامه"))
        self.lock_button.clicked.connect(self.lock_requested.emit)
        self._layout.addWidget(self.lock_button)

        self.help_button = QToolButton()
        self.help_button.setObjectName("HelpButton")
        self.help_button.setText("؟")
        self.help_button.setToolTip(self.tr("راهنما"))
        self.help_button.clicked.connect(self.help_requested.emit)
        self._layout.addWidget(self.help_button)
        self._apply_responsive_chrome(force=True)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_responsive_chrome()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._apply_responsive_chrome(force=True)

    def set_status(self, message: str) -> None:
        self.status_label.setText(message)

    def set_theme_label(self, theme: str) -> None:
        pass

    def set_menu_button_visible(self, visible: bool) -> None:
        self.menu_button.setVisible(visible)
        self._apply_responsive_chrome(force=True)

    def _apply_responsive_chrome(self, force: bool = False) -> None:
        scale = self._ui_scale_factor()
        mode = "dense" if scale >= 1.15 else "normal"
        if not force and mode == self._chrome_mode:
            return
        self._chrome_mode = mode
        if mode == "dense":
            self._layout.setContentsMargins(16, 6, 16, 6)
            self._layout.setSpacing(8)
            self.menu_button.setStyleSheet(
                "padding: 4px 10px; min-height: 30px;"
            )
            self.lock_button.setStyleSheet(
                "padding: 4px 10px; min-height: 30px;"
            )
            self.help_button.setStyleSheet(
                "padding: 4px 0px; min-height: 30px; min-width: 32px;"
            )
            return
        self._layout.setContentsMargins(20, 10, 20, 10)
        self._layout.setSpacing(10)
        self.menu_button.setStyleSheet("")
        self.lock_button.setStyleSheet("")
        self.help_button.setStyleSheet("")

    def _ui_scale_factor(self) -> float:
        screen = self.screen()
        if screen is None:
            app = QApplication.instance()
            if app is not None:
                screen = app.primaryScreen()
        factors: list[float] = [1.0]
        if screen is not None:
            dpi = float(screen.logicalDotsPerInch() or 96.0)
            if dpi > 0:
                factors.append(dpi / 96.0)
            try:
                ratio = float(screen.devicePixelRatio())
            except Exception:  # noqa: BLE001
                ratio = 1.0
            if ratio > 0:
                factors.append(ratio)
        try:
            widget_ratio = float(self.devicePixelRatioF())
        except Exception:  # noqa: BLE001
            widget_ratio = 1.0
        if widget_ratio > 0:
            factors.append(widget_ratio)
        return max(1.0, min(2.0, max(factors)))
