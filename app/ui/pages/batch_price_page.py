from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)


class BatchPricePage(QWidget):
    apply_requested = Signal(str, str, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("Batch Price Update")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        header.addWidget(title)
        header.addStretch(1)
        layout.addLayout(header)

        helper = QLabel("Apply a single change to all products' buy prices.")
        helper.setStyleSheet("color: #9CA3AF;")
        layout.addWidget(helper)

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)

        mode_row = QHBoxLayout()
        mode_label = QLabel("Mode:")
        mode_row.addWidget(mode_label)

        self.percent_radio = QRadioButton("Percent")
        self.fixed_radio = QRadioButton("Fixed Amount")
        self.percent_radio.setChecked(True)
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.percent_radio)
        self.mode_group.addButton(self.fixed_radio)

        mode_row.addWidget(self.percent_radio)
        mode_row.addWidget(self.fixed_radio)
        mode_row.addStretch(1)
        card_layout.addLayout(mode_row)

        value_row = QHBoxLayout()
        value_label = QLabel("Change:")
        value_row.addWidget(value_label)

        self.direction_combo = QComboBox()
        self.direction_combo.addItems(["Increase", "Decrease"])
        value_row.addWidget(self.direction_combo)

        self.value_input = QDoubleSpinBox()
        self.value_input.setRange(0.01, 1_000_000)
        self.value_input.setDecimals(2)
        self.value_input.setValue(10.0)
        value_row.addWidget(self.value_input)

        self.unit_label = QLabel("%")
        value_row.addWidget(self.unit_label)
        value_row.addStretch(1)
        card_layout.addLayout(value_row)

        self.percent_radio.toggled.connect(self._update_unit_label)
        self.fixed_radio.toggled.connect(self._update_unit_label)

        self.apply_button = QPushButton("Apply To All Products")
        self.apply_button.clicked.connect(self._emit_apply)
        card_layout.addWidget(self.apply_button)

        layout.addWidget(card)

    def set_enabled_state(self, enabled: bool) -> None:
        self.percent_radio.setEnabled(enabled)
        self.fixed_radio.setEnabled(enabled)
        self.direction_combo.setEnabled(enabled)
        self.value_input.setEnabled(enabled)
        self.apply_button.setEnabled(enabled)

    def _update_unit_label(self) -> None:
        self.unit_label.setText("%" if self.percent_radio.isChecked() else "")

    def _emit_apply(self) -> None:
        mode = "percent" if self.percent_radio.isChecked() else "fixed"
        direction = (
            "increase"
            if self.direction_combo.currentText() == "Increase"
            else "decrease"
        )
        self.apply_requested.emit(mode, direction, self.value_input.value())
