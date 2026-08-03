from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QButtonGroup, QSizePolicy

from .icons import svg_icon, CATEGORY_ICONS

CATEGORY_ORDER = [
    "Performance", "Crash Fixes", "Timers", "Assists", "Vehicle",
    "Game", "AI / Race Setup", "Traffic", "World", "UI",
]

VEHICLE_SWAP_KEY = "__vehicle_swap__"
SETTINGS_KEY = "__settings__"
DEVELOPER_KEY = "__developer__"


class Sidebar(QWidget):
    section_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(196)
        self.setAttribute(Qt.WA_StyledBackground, True)

        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(8, 10, 8, 10)
        self.layout_.setSpacing(2)

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: dict[str, QPushButton] = {}
        self._icon_names: dict[str, str] = {}
        self._icon_color = "#9CA3AF"

    def populate(self, present_categories: list[str]):
        while self.layout_.count():
            item = self.layout_.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.buttons.clear()
        self._icon_names.clear()

        heading = QLabel("FEATURES")
        heading.setObjectName("SidebarSection")
        self.layout_.addWidget(heading)

        ordered = [c for c in CATEGORY_ORDER if c in present_categories]
        ordered += [c for c in present_categories if c not in CATEGORY_ORDER]
        for cat in ordered:
            self._add_button(cat, cat, CATEGORY_ICONS.get(cat, "layers"))

        heading2 = QLabel("LIBRARY")
        heading2.setObjectName("SidebarSection")
        self.layout_.addWidget(heading2)
        self._add_button(VEHICLE_SWAP_KEY, "Vehicle Swap", "car")

        self.layout_.addStretch(1)

        heading3 = QLabel("APP")
        heading3.setObjectName("SidebarSection")
        self.layout_.addWidget(heading3)
        self._add_button(SETTINGS_KEY, "Settings", "settings")
        self._add_button(DEVELOPER_KEY, "Developer", "wrench")

    def _add_button(self, key: str, text: str, icon_name: str):
        btn = QPushButton(text)
        btn.setObjectName("SidebarItem")
        btn.setCheckable(True)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setIcon(svg_icon(icon_name, self._icon_color, 16))
        btn.setIconSize(btn.iconSize())
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn.clicked.connect(lambda: self.section_changed.emit(key))
        self.group.addButton(btn)
        self.buttons[key] = btn
        self._icon_names[key] = icon_name
        self.layout_.addWidget(btn)

    def set_active(self, key: str):
        btn = self.buttons.get(key)
        if btn is not None:
            btn.setChecked(True)

    def set_icon_color(self, color: str):
        self._icon_color = color
        for key, btn in self.buttons.items():
            icon_name = self._icon_names.get(key, "layers")
            btn.setIcon(svg_icon(icon_name, color, 16))
