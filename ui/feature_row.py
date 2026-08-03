from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                                 QSpinBox, QDoubleSpinBox, QSizePolicy)

from . import theme
from .toggle_switch import ToggleSwitch
from .tooltip import InfoButton, InfoPopover


class FeatureRow(QFrame):

    toggled = Signal(str, bool)
    apply_requested = Signal(str)
    value_changed = Signal(str, object)

    def __init__(self, sig: dict, popover: InfoPopover, reduced_motion: bool = False,
                 risk_override: str | None = None, warning_override: str = "",
                 danger_override: str = "", initial_value=None, parent=None):
        super().__init__(parent)
        self.sig = sig
        self.sid = sig["id"]
        self.patch_type = sig["patch_type"]
        self.reduced_motion = reduced_motion
        self.setObjectName("FeatureRow")
        self.setProperty("hovered", False)
        self.setProperty("flagged", bool(danger_override))
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumHeight(48)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 10, 10)
        layout.setSpacing(10)

        risk = risk_override or sig.get("risk", "medium")
        self.risk_dot = QLabel("\u25CF")
        self.risk_dot.setFixedWidth(12)
        self.risk_dot.setStyleSheet(f"color: {theme.RISK_COLOR.get(risk, '#616161')}; font-size: 10px;")
        self.risk_dot.setToolTip(f"Risk: {risk}")
        layout.addWidget(self.risk_dot)

        self.label = QLabel(sig["label"])
        self.label.setObjectName("FeatureLabel")
        self.label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(self.label, 1)

        self.value_input = None
        is_adjustable = sig.get("value_offset") is not None or self.patch_type == "cave_field_freeze"
        if is_adjustable and self.patch_type != "pointer_write":
            self.value_input = self._make_value_input(sig, initial_value)
            self.value_input.setFixedWidth(84)
            self.value_input.valueChanged.connect(
                lambda v: self.value_changed.emit(self.sid, v))
            layout.addWidget(self.value_input)

        self.info_btn = InfoButton(
            title=sig["label"],
            body=sig.get("desc", "") or "No description available.",
            warning=warning_override,
            danger=danger_override,
            popover=popover,
        )
        layout.addWidget(self.info_btn)

        if self.patch_type == "pointer_write":
            self.apply_value_input = self._make_value_input(sig, initial_value or 0)
            self.apply_value_input.setFixedWidth(90)
            self.apply_value_input.valueChanged.connect(
                lambda v: self.value_changed.emit(self.sid, v))
            layout.addWidget(self.apply_value_input)

            self.apply_btn = QPushButton("Apply")
            self.apply_btn.setObjectName("ApplyBtn")
            self.apply_btn.setCursor(Qt.PointingHandCursor)
            self.apply_btn.setFixedWidth(72)
            self.apply_btn.clicked.connect(lambda: self.apply_requested.emit(self.sid))
            layout.addWidget(self.apply_btn)
            self.toggle = None
        else:
            self.toggle = ToggleSwitch(reduced_motion=reduced_motion)
            self.toggle.toggled.connect(self._on_toggle_flipped)
            layout.addWidget(self.toggle)
            self.apply_btn = None

        self.setAttribute(Qt.WA_Hover, True)
        self.installEventFilter(self)

    def _make_value_input(self, sig, initial_value):
        vt = sig.get("value_type", "int")
        if vt == "float":
            box = QDoubleSpinBox()
            box.setDecimals(3)
            box.setRange(-1_000_000.0, 1_000_000.0)
            box.setSingleStep(0.05)
            box.setValue(float(initial_value if initial_value is not None else 1.0))
        else:
            box = QSpinBox()
            box.setRange(-2_147_483_648, 2_147_483_647)
            box.setValue(int(initial_value if initial_value is not None else 1))
        return box


    def eventFilter(self, obj, event):
        if obj is self:
            if event.type() == QEvent.Enter:
                self.setProperty("hovered", True)
                self._repolish()
            elif event.type() == QEvent.Leave:
                self.setProperty("hovered", False)
                self._repolish()
        return super().eventFilter(obj, event)

    def _repolish(self):
        self.style().unpolish(self)
        self.style().polish(self)

    def _on_toggle_flipped(self, checked: bool):
        self.toggled.emit(self.sid, checked)


    def current_value(self):
        if self.patch_type == "pointer_write":
            return self.apply_value_input.value()
        if self.value_input is not None:
            return self.value_input.value()
        return None

    def set_checked_silent(self, checked: bool, animate: bool = False):
        if self.toggle is not None:
            self.toggle.setChecked(checked, animate=animate, emit=False)

    def revert_toggle(self):
        if self.toggle is not None:
            self.toggle.setChecked(not self.toggle.isChecked(), animate=True, emit=False)

    def set_apply_enabled(self, enabled: bool):
        if self.apply_btn is not None:
            self.apply_btn.setEnabled(enabled)

    def set_row_enabled(self, enabled: bool):
        self.label.setProperty("dim", not enabled)
        self._repolish_label()
        if self.toggle is not None:
            self.toggle.setEnabled(enabled)
        if self.apply_btn is not None:
            self.apply_btn.setEnabled(enabled)
            self.apply_value_input.setEnabled(enabled)
        if self.value_input is not None:
            self.value_input.setEnabled(enabled)

    def _repolish_label(self):
        self.label.style().unpolish(self.label)
        self.label.style().polish(self.label)
