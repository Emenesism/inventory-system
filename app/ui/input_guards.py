from __future__ import annotations

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QAbstractSpinBox


class NumericWheelGuard(QObject):
    """Prevent spinbox value changes via mouse wheel globally."""

    def eventFilter(self, watched, event) -> bool:  # noqa: N802, ANN001
        if isinstance(watched, QAbstractSpinBox):
            if event.type() == QEvent.Wheel:
                event.ignore()
                return True
            return False

        if event.type() != QEvent.Wheel:
            return False
        current = watched
        while current is not None:
            if isinstance(current, QAbstractSpinBox):
                event.ignore()
                return True
            parent_getter = getattr(current, "parent", None)
            current = parent_getter() if callable(parent_getter) else None
        return False
