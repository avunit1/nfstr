from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                 QComboBox, QScrollArea, QFrame, QSizePolicy)

from .toggle_switch import ToggleSwitch
from .settings_store import Settings, save as save_settings


class SettingRow(QFrame):
    def __init__(self, title: str, hint: str, control: QWidget, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setAttribute(Qt.WA_StyledBackground, True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 13, 16, 13)
        layout.setSpacing(12)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        label = QLabel(title)
        label.setObjectName("FieldLabel")
        text_col.addWidget(label)
        if hint:
            hint_label = QLabel(hint)
            hint_label.setObjectName("FieldHint")
            hint_label.setWordWrap(True)
            text_col.addWidget(hint_label)
        text_wrap = QWidget()
        text_wrap.setLayout(text_col)
        text_wrap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(text_wrap, 1)
        layout.addWidget(control)


class SettingsView(QWidget):
    changed = Signal(Settings)

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(4)

        title = QLabel("Settings")
        title.setObjectName("CategoryTitle")
        outer.addWidget(title)
        sub = QLabel("Preferences are saved automatically to %APPDATA%\\nfstr_data\\settings.json.")
        sub.setObjectName("CategoryCount")
        outer.addWidget(sub)
        outer.addSpacing(14)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll, 1)

        inner = QWidget()
        scroll.setWidget(inner)
        col = QVBoxLayout(inner)
        col.setContentsMargins(2, 2, 2, 2)
        col.setSpacing(10)

        heading = QLabel("APPEARANCE")
        heading.setObjectName("SidebarSection")
        col.addWidget(heading)

        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Dark", "dark")
        self.theme_combo.addItem("Darker", "darker")
        self.theme_combo.addItem("System", "system")
        idx = max(0, self.theme_combo.findData(settings.theme))
        self.theme_combo.setCurrentIndex(idx)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        col.addWidget(SettingRow("Theme", "Dark or Darker surface contrast.", self.theme_combo))

        self.reduced_motion_toggle = self._toggle(settings.reduced_motion, self._on_reduced_motion)
        col.addWidget(SettingRow("Reduced motion", "Disables toggle/tooltip/toast animations.", self.reduced_motion_toggle))

        heading2 = QLabel("BEHAVIOR")
        heading2.setObjectName("SidebarSection")
        col.addWidget(heading2)

        self.auto_attach_toggle = self._toggle(settings.auto_attach, self._on_auto_attach)
        col.addWidget(SettingRow("Auto-attach to game", "Attach automatically when the game process is detected.", self.auto_attach_toggle))

        self.start_min_toggle = self._toggle(settings.start_minimized, self._on_start_minimized)
        col.addWidget(SettingRow("Start minimized", "Launch directly to the taskbar/tray.", self.start_min_toggle))

        self.remember_size_toggle = self._toggle(settings.remember_window_size, self._on_remember_size)
        col.addWidget(SettingRow("Remember window size", "Restore the last window size on launch.", self.remember_size_toggle))

        self.remember_cat_toggle = self._toggle(settings.remember_selected_category, self._on_remember_category)
        col.addWidget(SettingRow("Remember selected category", "Reopen the last-viewed sidebar section on launch.", self.remember_cat_toggle))

        self.notif_toggle = self._toggle(settings.enable_notifications, self._on_notifications)
        col.addWidget(SettingRow("Enable notifications", "Show toast notifications for attach state and toggle results.", self.notif_toggle))

        col.addStretch(1)

    def _toggle(self, checked: bool, handler) -> ToggleSwitch:
        t = ToggleSwitch(reduced_motion=self.settings.reduced_motion)
        t.setChecked(checked, animate=False)
        t.toggled.connect(handler)
        return t

    def _persist_and_emit(self):
        save_settings(self.settings)
        self.changed.emit(self.settings)

    def _on_theme_changed(self, _idx):
        self.settings.theme = self.theme_combo.currentData()
        self._persist_and_emit()

    def _on_reduced_motion(self, checked: bool):
        self.settings.reduced_motion = checked
        self._persist_and_emit()

    def _on_auto_attach(self, checked: bool):
        self.settings.auto_attach = checked
        self._persist_and_emit()

    def _on_start_minimized(self, checked: bool):
        self.settings.start_minimized = checked
        self._persist_and_emit()

    def _on_remember_size(self, checked: bool):
        self.settings.remember_window_size = checked
        self._persist_and_emit()

    def _on_remember_category(self, checked: bool):
        self.settings.remember_selected_category = checked
        self._persist_and_emit()

    def _on_notifications(self, checked: bool):
        self.settings.enable_notifications = checked
        self._persist_and_emit()
