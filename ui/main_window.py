from __future__ import annotations

import json
import logging
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QKeySequence, QShortcut, QIcon
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                 QStackedWidget, QScrollArea, QMessageBox)

from core import process, paths
from core.memory import SafeMemory
from core.codecave import CodeCaveEngine
from core.cache import BuildCache
from core.resolver import SignatureResolver
from core import logging_setup
from features.engine import FeatureEngine

from . import theme
from .sidebar import Sidebar, VEHICLE_SWAP_KEY, SETTINGS_KEY, DEVELOPER_KEY, CATEGORY_ORDER
from .feature_row import FeatureRow
from .tooltip import InfoPopover
from .toast import ToastManager
from .vehicle_view import VehicleView
from .settings_dialog import SettingsView
from . import settings_store
from .developer_panel import DeveloperPanel
from .workers import CallableWorker

WINDOW_TITLE = "NFSTR 1.0"
FEATURE_VALUE_SAVE_DEBOUNCE_MS = 300

SIGNATURES_PATH = paths.bundled_resource("data", "signatures.json")
VEHICLES_PATH = paths.bundled_resource("data", "vehicles.json")
CACHE_PATH = paths.cache_path()

log = logging.getLogger("nfstr.gui")

AUTO_ATTACH_POLL_MS = 2000
LOG_DRAIN_POLL_MS = 300

DEDICATED_TAB_IDS = {"vehicle_swap_car_object"}

DANGER_OVERRIDES = {
    "crash_tunnel_of_pain": {
        "risk": "high",
        "danger": ("Confirmed to corrupt checkpoint-crossing, distance/timer HUD, and "
                    "overtake detection for the rest of the run once enabled -- root-caused "
                    "via live isolation testing across both battle and standard races. Not a "
                    "stage-scoped fix. Avoid enabling unless you're specifically debugging it."),
        "confirm_on_enable": True,
    },
}

_VALUE_DEFAULTS = {
    "traffic_density_scale": 0.05, "traffic_max_density": 0.15,
    "traffic_vehicle_limit": 25, "ai_difficulty_expert": 3,
    "ai_number_of_players": 8, "ai_player_grid_position": 1,
    "game_difficulty_scalar": 5.0, "game_glue_scalar": 0.7,
    "vehicle_damage_threshold": 101, "tod_career_challenge": 4,
    "perf_unlock_framerate": 60.0,
}


def _default_value_for(sig: dict):
    vt = sig.get("value_type")
    return _VALUE_DEFAULTS.get(sig["id"], 1.0 if vt == "float" else 1)


class StatusHeader(QWidget):
    HEIGHT = 64

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("StatusHeader")


        self.setMinimumHeight(self.HEIGHT)
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(10)

        self.dot = QLabel("\u25CF")
        self.dot.setObjectName("StatusDotOff")
        layout.addWidget(self.dot, 0, Qt.AlignVCenter)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)
        self.title_label = QLabel("Not Attached")
        self.title_label.setObjectName("StatusTitle")
        text_col.addWidget(self.title_label)
        self.subtitle_label = QLabel("Launch the game to connect automatically")
        self.subtitle_label.setObjectName("StatusSubtitle")
        text_col.addWidget(self.subtitle_label)
        text_wrap = QWidget()
        text_wrap.setLayout(text_col)


        layout.addWidget(text_wrap, 0, Qt.AlignVCenter)
        layout.addStretch(1)

    def set_state(self, attached: bool, waiting: bool = False):
        self.dot.setObjectName("StatusDotOn" if attached else "StatusDotOff")
        self.dot.style().unpolish(self.dot)
        self.dot.style().polish(self.dot)
        if attached:
            self.title_label.setText("Game Detected")
            self.subtitle_label.setText("Need for Speed: The Run \u00B7 Connected automatically")
        else:
            self.title_label.setText("Not Attached")
            self.subtitle_label.setText(
                "Waiting for the game to launch\u2026" if waiting else
                "Launch Need for Speed: The Run to connect automatically")


class CategoryPage(QWidget):
    def __init__(self, category: str, entries: list[dict], popover: InfoPopover,
                 reduced_motion: bool, feature_values: dict, parent=None):
        super().__init__(parent)
        self.rows: dict[str, FeatureRow] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 18)
        outer.setSpacing(4)

        header = QHBoxLayout()
        title = QLabel(category)
        title.setObjectName("CategoryTitle")
        header.addWidget(title)
        header.addStretch(1)
        count = QLabel(f"{len(entries)} feature{'s' if len(entries) != 1 else ''}")
        count.setObjectName("CategoryCount")
        header.addWidget(count)
        outer.addLayout(header)
        outer.addSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll, 1)

        inner = QWidget()
        scroll.setWidget(inner)
        col = QVBoxLayout(inner)
        col.setContentsMargins(2, 2, 2, 2)
        col.setSpacing(9)

        for sig in entries:
            override = DANGER_OVERRIDES.get(sig["id"], {})
            is_adjustable = sig.get("value_offset") is not None or sig["patch_type"] == "cave_field_freeze"
            if is_adjustable:
                saved = feature_values.get(sig["id"])
                initial_value = saved if saved is not None else _default_value_for(sig)
            else:
                initial_value = None
            row = FeatureRow(
                sig, popover, reduced_motion=reduced_motion,
                risk_override=override.get("risk"),
                danger_override=override.get("danger", ""),
                initial_value=initial_value,
            )
            self.rows[sig["id"]] = row
            col.addWidget(row)
        col.addStretch(1)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = settings_store.load()
        self.reduced_motion = self.settings.reduced_motion
        self.palette_obj = theme.get_palette(self.settings.theme)

        self.log_file_path = logging_setup.setup_logging()
        log.info("GUI starting (PySide6). Bundled resources at: %s", paths.bundled_resource())
        log.info("Writable data/cache dir: %s", paths.writable_dir())

        self.signatures = json.load(open(SIGNATURES_PATH, encoding="utf-8"))
        self.by_id = {s["id"]: s for s in self.signatures}
        self.vehicles = json.load(open(VEHICLES_PATH, encoding="utf-8"))
        log.info("Loaded %d signatures, %d vehicles", len(self.signatures), len(self.vehicles))

        self.target = None
        self.resolver = None
        self.mem = None
        self.cave = None
        self.engine = None
        self._attaching = False
        self._attach_worker = None
        self._calibrate_worker = None

        self._popover = InfoPopover(reduced_motion=self.reduced_motion)
        self.all_rows: dict[str, FeatureRow] = {}

        self._build_window_chrome()
        self._build_body()
        self.toasts = ToastManager(self)
        self.toasts.reduced_motion = self.reduced_motion
        self.toasts.set_palette(self.palette_obj)
        self.toasts.enabled = self.settings.enable_notifications

        self._apply_theme()
        self._restore_geometry()

        self._select_initial_page()

        self._dev_shortcut = QShortcut(QKeySequence("Ctrl+Shift+D"), self)
        self._dev_shortcut.activated.connect(self._open_dev_panel)

        self._log_timer = QTimer(self)
        self._log_timer.timeout.connect(self._drain_log)
        self._log_timer.start(LOG_DRAIN_POLL_MS)

        self._attach_timer = QTimer(self)
        self._attach_timer.timeout.connect(self._auto_attach_poll)
        self._attach_timer.start(AUTO_ATTACH_POLL_MS)


        self._value_save_timer = QTimer(self)
        self._value_save_timer.setSingleShot(True)
        self._value_save_timer.setInterval(FEATURE_VALUE_SAVE_DEBOUNCE_MS)
        self._value_save_timer.timeout.connect(lambda: settings_store.save(self.settings))

        self._set_rows_enabled(False)
        self._try_attach(initial=True, silent=True)

        if self.settings.start_minimized:
            QTimer.singleShot(0, self.showMinimized)


    def _build_window_chrome(self):


        self.setObjectName("RootShell")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setWindowTitle(WINDOW_TITLE)
        self.setWindowIcon(QIcon(paths.icon_path()))
        self.setMinimumSize(1000, 650)

        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(0)

        self.status_header = StatusHeader()
        self.root_layout.addWidget(self.status_header)

    def _build_body(self):
        self.normal_body = QWidget()
        body_layout = QHBoxLayout(self.normal_body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        self.root_layout.addWidget(self.normal_body, 1)

        self.sidebar = Sidebar()
        self.sidebar.section_changed.connect(self._on_section_changed)
        body_layout.addWidget(self.sidebar)

        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("ContentArea")
        self.content_stack.setAttribute(Qt.WA_StyledBackground, True)
        body_layout.addWidget(self.content_stack, 1)

        self.page_index: dict[str, int] = {}
        present_categories = sorted(
            {s["category"] for s in self.signatures if not s.get("internal")},
            key=lambda c: CATEGORY_ORDER.index(c) if c in CATEGORY_ORDER else 999,
        )
        for cat in present_categories:
            entries = [s for s in self.signatures
                       if s.get("category") == cat and not s.get("internal")
                       and s["id"] not in DEDICATED_TAB_IDS]
            if not entries:
                continue
            page = CategoryPage(cat, entries, self._popover, self.reduced_motion,
                                 self.settings.feature_values)
            self.all_rows.update(page.rows)
            idx = self.content_stack.addWidget(page)
            self.page_index[cat] = idx

        favorites = set(self.settings.favorite_vehicle_entries or [])
        self.vehicle_view = VehicleView(self.vehicles, favorites)
        self.vehicle_view.apply_requested.connect(self._on_vehicle_apply)
        self.vehicle_view.status_message.connect(lambda m: self.toasts.show(m, "warning"))
        self.vehicle_view.favorites_changed.connect(self._persist_favorites)
        idx = self.content_stack.addWidget(self.vehicle_view)
        self.page_index[VEHICLE_SWAP_KEY] = idx

        self.settings_view = SettingsView(self.settings)
        self.settings_view.changed.connect(self._on_settings_changed)
        idx = self.content_stack.addWidget(self.settings_view)
        self.page_index[SETTINGS_KEY] = idx


        self.dev_panel = DeveloperPanel(self.log_file_path)
        self.dev_panel.recalibrate_requested.connect(self._recalibrate)
        idx = self.content_stack.addWidget(self.dev_panel)
        self.page_index[DEVELOPER_KEY] = idx

        self.sidebar.populate(present_categories)


        for sid, row in self.all_rows.items():
            row.toggled.connect(self._on_feature_toggled)
            row.apply_requested.connect(self._on_apply_requested)
            row.value_changed.connect(self._on_feature_value_changed)

    def _select_initial_page(self):
        key = None
        if self.settings.remember_selected_category and self.settings.last_category:
            key = self.settings.last_category
        if key not in self.page_index:
            key = next(iter(self.page_index), None)
        if key is not None:
            self._on_section_changed(key, persist=False)
            self.sidebar.set_active(key)


    def _apply_theme(self):
        p = self.palette_obj
        self.setStyleSheet(theme.build_stylesheet(p))
        self.sidebar.set_icon_color(p.text_secondary)
        self.toasts.set_palette(p)
        self.vehicle_view.set_palette(p)
        for row in self.all_rows.values():
            if row.toggle is not None:
                row.toggle.set_palette(p)

    def _on_settings_changed(self, settings: settings_store.Settings):
        self.settings = settings
        new_reduced_motion = settings.reduced_motion
        if new_reduced_motion != self.reduced_motion:
            self.reduced_motion = new_reduced_motion
            self.toasts.reduced_motion = new_reduced_motion
            for row in self.all_rows.values():
                if row.toggle is not None:
                    row.toggle.reduced_motion = new_reduced_motion
        self.toasts.enabled = settings.enable_notifications
        new_palette = theme.get_palette(settings.theme)
        if new_palette is not self.palette_obj:
            self.palette_obj = new_palette
            self._apply_theme()


    def _on_section_changed(self, key: str, persist: bool = True):
        idx = self.page_index.get(key)
        if idx is None:
            return
        self.content_stack.setCurrentIndex(idx)
        self.sidebar.set_active(key)
        if persist and self.settings.remember_selected_category:
            self.settings.last_category = key
            settings_store.save(self.settings)

    def _open_dev_panel(self):
        self._on_section_changed(DEVELOPER_KEY)


    def _on_feature_toggled(self, sid: str, checked: bool):
        sig = self.by_id[sid]
        row = self.all_rows[sid]

        if checked and DANGER_OVERRIDES.get(sid, {}).get("confirm_on_enable"):
            resp = QMessageBox.warning(
                self, "Are you sure?",
                f"\u201C{sig['label']}\u201D is known to corrupt game state for the rest of "
                "the run once enabled. See the (i) icon for details.\n\nEnable anyway?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if resp != QMessageBox.Yes:
                row.revert_toggle()
                return

        if not self.engine:
            row.revert_toggle()
            self.toasts.show("Attach to the game first.", "warning")
            return

        kwargs = {}
        if row.value_input is not None:
            kwargs["value"] = row.current_value()
            if sig["patch_type"] in ("pointer_write", "freeze"):
                kwargs["value_type"] = sig.get("value_type", "u32")

        try:
            ok = self.engine.toggle(sig, checked, **kwargs)
        except Exception:
            log.exception("Unexpected error toggling %s", sid)
            ok = False

        if not ok:
            row.revert_toggle()
            self.toasts.show(f"Could not toggle \u201C{sig['label']}\u201D. See Developer "
                               "Tools \u2192 Log for details.", "error")
        else:
            self.toasts.show(f"{sig['label']} {'enabled' if checked else 'disabled'}", "success")

    def _on_apply_requested(self, sid: str):
        sig = self.by_id[sid]
        row = self.all_rows[sid]
        if not self.engine:
            self.toasts.show("Attach to the game first.", "warning")
            return
        kwargs = {"value": row.current_value(), "value_type": sig.get("value_type", "u32")}
        try:
            ok = self.engine.enable(sig, **kwargs)
        except Exception:
            log.exception("Unexpected error applying %s", sid)
            ok = False
        if ok:
            self.toasts.show(f"{sig['label']} applied", "success")
        else:
            self.toasts.show(f"Failed to apply \u201C{sig['label']}\u201D. See Developer "
                               "Tools \u2192 Log for details.", "error")

    def _on_feature_value_changed(self, sid: str, value):
        self.settings.feature_values[sid] = value
        self._value_save_timer.start()

    def _on_vehicle_apply(self, vehicle: dict):
        sig = self.by_id["vehicle_swap_car_object"]
        try:
            ok = self.engine.enable(sig, value=vehicle["hash_u32"], value_type="u32")
        except Exception:
            log.exception("Unexpected error applying vehicle swap")
            ok = False
        if ok:
            self.toasts.show(f"Swapped to {vehicle['vehicle']}", "success")
        else:
            self.toasts.show(f"Failed to swap to {vehicle['vehicle']}. See Developer "
                               "Tools \u2192 Log for details.", "error")
        self._persist_favorites()

    def _persist_favorites(self):
        self.settings.favorite_vehicle_entries = sorted(self.vehicle_view.favorites())
        settings_store.save(self.settings)

    def _set_rows_enabled(self, enabled: bool):
        for row in self.all_rows.values():
            row.set_row_enabled(enabled)
        self.vehicle_view.set_attached(enabled)


    def _log(self, msg: str):
        log.info(msg)

    def _try_attach(self, initial: bool = False, silent: bool = False):
        if self._attaching or self.target is not None:
            return
        self._attaching = True
        worker = CallableWorker(process.attach, timeout=0)
        worker.finished_ok.connect(lambda target: self._on_attach_success(target))
        worker.failed.connect(lambda msg: self._on_attach_failed(msg, initial, silent))
        self._attach_worker = worker
        worker.start()

    def _on_attach_success(self, target):
        self._attaching = False
        self.target = target
        self.mem = SafeMemory(target.pm)
        self.cave = CodeCaveEngine(target.pm.process_handle, self.mem)
        cache = BuildCache(CACHE_PATH)
        self.resolver = SignatureResolver(target, self.signatures, cache)
        self.engine = FeatureEngine(self.resolver, self.mem, self.cave,
                                      all_signatures=self.by_id, log=self._log)

        self.status_header.set_state(attached=True)
        self._set_rows_enabled(True)
        self.dev_panel.update_status(
            attached=True, pid=target.pid, process_name=target.process_name,
            base_hex=hex(target.base), size_hex=hex(target.size),
            sha256=target.sha256 or "unknown",
            delta_hex=("+" if target.delta >= 0 else "-") + hex(abs(target.delta)),
        )
        self.toasts.show(f"Attached to {target.process_name}", "success")
        self._recalibrate()

    def _on_attach_failed(self, msg: str, initial: bool, silent: bool):
        self._attaching = False
        self.target = None
        self.status_header.set_state(attached=False, waiting=self.settings.auto_attach)
        if not initial and not silent:
            self.toasts.show(f"Not attached: {msg}", "warning")

    def _recalibrate(self):
        if not self.target or not self.resolver:
            self.toasts.show("Attach to the game first.", "warning")
            return

        resolver = self.resolver

        def work():
            resolver.resolve_all()
            ok = sum(1 for r in resolver.resolved.values() if r.verified)
            total = len(resolver.sigs)
            unresolved = [sid for sid, r in resolver.resolved.items() if not r.verified]
            return ok, total, unresolved

        worker = CallableWorker(work)
        worker.finished_ok.connect(self._on_calibration_done)
        worker.failed.connect(lambda msg: log.error("Calibration failed: %s", msg))
        self._calibrate_worker = worker
        worker.start()

    def _on_calibration_done(self, result):
        ok, total, unresolved = result
        self.dev_panel.update_calibration(ok, total, unresolved)
        kind = "success" if ok == total else "warning"
        self.toasts.show(f"Calibration complete: {ok}/{total} signatures verified", kind)

    def _auto_attach_poll(self):
        try:
            if self.settings.auto_attach:
                if self.target is None and not self._attaching:
                    self._try_attach(initial=True, silent=True)
                elif self.target is not None:
                    if not process.is_process_alive(self.target):
                        self._on_process_lost()
        except Exception:
            log.exception("Error in auto-attach poll loop")

    def _on_process_lost(self):
        if self.engine:
            try:
                self.engine.shutdown()
            except Exception:
                log.exception("Error shutting down engine after process loss")
        self.target = self.resolver = self.mem = self.cave = self.engine = None
        self.status_header.set_state(attached=False, waiting=self.settings.auto_attach)
        self._set_rows_enabled(False)
        for row in self.all_rows.values():
            row.set_checked_silent(False)
        self.dev_panel.update_status(attached=False)
        self.toasts.show("Game process exited. Not attached.", "warning")

    def _drain_log(self):
        lines = logging_setup.drain_queue()
        if lines:
            self.dev_panel.append_log_lines(lines)


    def _restore_geometry(self):
        if self.settings.remember_window_size and self.settings.window_width and self.settings.window_height:
            self.resize(QSize(max(1000, self.settings.window_width),
                                max(650, self.settings.window_height)))
        else:
            self.resize(QSize(1180, 760))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "toasts"):
            self.toasts.reposition()

    def closeEvent(self, event):
        log.info("Shutting down...")
        try:
            if self.settings.remember_window_size and not self.isMaximized():
                self.settings.window_width = self.width()
                self.settings.window_height = self.height()
            self._persist_favorites()
            settings_store.save(self.settings)
        except Exception:
            log.exception("Error persisting settings on close")
        try:
            if self.engine:
                self.engine.shutdown()
        except Exception:
            log.exception("Error during shutdown")
        super().closeEvent(event)
