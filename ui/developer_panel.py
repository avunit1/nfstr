from __future__ import annotations

import os
import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication, QTextCursor
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                 QPushButton, QTextEdit, QLineEdit,
                                 QCheckBox, QFileDialog)

from . import theme

_LEVEL_RE = re.compile(r"\[(DEBUG|INFO|WARNING|ERROR|CRITICAL)\s*\]")
_MAX_BUFFER_LINES = 8000


class KVRow(QWidget):
    def __init__(self, key: str, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 3, 0, 3)
        k = QLabel(key)
        k.setObjectName("KVKey")
        k.setFixedWidth(150)
        layout.addWidget(k)
        self.value_label = QLabel("N/A")
        self.value_label.setObjectName("KVVal")
        self.value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.value_label.setWordWrap(True)
        layout.addWidget(self.value_label, 1)

    def set_value(self, text: str):
        self.value_label.setText(text or "N/A")


class DeveloperPanel(QWidget):
    recalibrate_requested = Signal()

    def __init__(self, log_file_path: str, parent=None):
        super().__init__(parent)
        self.setObjectName("DevPanel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.log_file_path = log_file_path
        self.reduced_motion = False
        self._log_buffer: list[str] = []
        self._paused = False

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(14)

        sub = QLabel("Raw process/memory diagnostics and the full session log. "
                      "Not needed for normal use.")
        sub.setObjectName("CategoryCount")
        root.addWidget(sub)

        status_card = QWidget()
        status_card.setObjectName("Card")
        status_card.setAttribute(Qt.WA_StyledBackground, True)
        grid_wrap = QVBoxLayout(status_card)
        grid_wrap.setContentsMargins(16, 14, 16, 14)
        grid_wrap.setSpacing(0)

        self.kv = {}
        for key in ["Attached", "PID", "Process name", "Module base", "Module size",
                     "SHA256", "ASLR delta", "Calibration", "Unverified signatures"]:
            row = KVRow(key)
            self.kv[key] = row
            grid_wrap.addWidget(row)
        root.addWidget(status_card)

        actions = QHBoxLayout()
        recal_btn = QPushButton("Re-run calibration")
        recal_btn.setObjectName("GhostBtn")
        recal_btn.setCursor(Qt.PointingHandCursor)
        recal_btn.clicked.connect(self.recalibrate_requested.emit)
        actions.addWidget(recal_btn)

        copy_diag_btn = QPushButton("Copy diagnostics")
        copy_diag_btn.setObjectName("GhostBtn")
        copy_diag_btn.setCursor(Qt.PointingHandCursor)
        copy_diag_btn.clicked.connect(self._copy_diagnostics)
        actions.addWidget(copy_diag_btn)
        actions.addStretch(1)
        root.addLayout(actions)

        log_header = QHBoxLayout()
        log_title = QLabel("Session Log")
        log_title.setObjectName("SectionHeading")
        log_header.addWidget(log_title)
        log_header.addStretch(1)

        self.filter_box = QLineEdit()
        self.filter_box.setPlaceholderText("Filter log\u2026")
        self.filter_box.setFixedWidth(220)
        self.filter_box.textChanged.connect(self._rerender)
        log_header.addWidget(self.filter_box)

        self.pause_check = QCheckBox("Pause auto-scroll")
        self.pause_check.toggled.connect(self._on_pause_toggled)
        log_header.addWidget(self.pause_check)

        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("GhostBtn")
        clear_btn.clicked.connect(self._clear)
        log_header.addWidget(clear_btn)

        copy_btn = QPushButton("Copy")
        copy_btn.setObjectName("GhostBtn")
        copy_btn.clicked.connect(self._copy_log)
        log_header.addWidget(copy_btn)

        export_btn = QPushButton("Export\u2026")
        export_btn.setObjectName("GhostBtn")
        export_btn.clicked.connect(self._export)
        log_header.addWidget(export_btn)

        folder_btn = QPushButton("Open logs folder")
        folder_btn.setObjectName("GhostBtn")
        folder_btn.clicked.connect(self._open_folder)
        log_header.addWidget(folder_btn)
        root.addLayout(log_header)

        self.log_view = QTextEdit()
        self.log_view.setObjectName("LogView")
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QTextEdit.NoWrap)
        root.addWidget(self.log_view, 1)

        path_label = QLabel(f"Full debug-level session log always written to: {log_file_path}")
        path_label.setObjectName("FieldHint")
        path_label.setWordWrap(True)
        root.addWidget(path_label)


    def update_status(self, *, attached: bool, pid=None, process_name=None,
                       base_hex=None, size_hex=None, sha256=None, delta_hex=None):
        self.kv["Attached"].set_value("Yes" if attached else "No")
        self.kv["PID"].set_value(str(pid) if pid is not None else "")
        self.kv["Process name"].set_value(process_name or "")
        self.kv["Module base"].set_value(base_hex or "")
        self.kv["Module size"].set_value(size_hex or "")
        self.kv["SHA256"].set_value(sha256 or "")
        self.kv["ASLR delta"].set_value(delta_hex or "")

    def update_calibration(self, verified: int, total: int, unresolved: list[str]):
        self.kv["Calibration"].set_value(f"{verified}/{total} verified")
        self.kv["Unverified signatures"].set_value(", ".join(unresolved) if unresolved else "None")

    def _copy_diagnostics(self):
        lines = [f"{k}: {row.value_label.text()}" for k, row in self.kv.items()]
        QGuiApplication.clipboard().setText("\n".join(lines))


    def append_log_lines(self, lines: list[str]):
        if not lines:
            return
        self._log_buffer.extend(lines)
        if len(self._log_buffer) > _MAX_BUFFER_LINES:
            self._log_buffer = self._log_buffer[-_MAX_BUFFER_LINES:]

        query = self.filter_box.text().strip().lower()
        to_show = [ln for ln in lines if not query or query in ln.lower()]
        if not to_show:
            return
        cursor = self.log_view.textCursor()
        cursor.movePosition(QTextCursor.End)
        for line in to_show:
            cursor.insertHtml(self._colorize(line) + "<br>")
        if not self._paused:
            self.log_view.setTextCursor(cursor)
            self.log_view.ensureCursorVisible()

    def _colorize(self, line: str) -> str:
        p = theme.DARK
        m = _LEVEL_RE.search(line)
        color = p.text_secondary
        if m:
            level = m.group(1)
            color = {"DEBUG": p.text_disabled, "INFO": p.text_secondary,
                      "WARNING": p.warning, "ERROR": p.danger, "CRITICAL": p.danger}.get(level, p.text_secondary)
        safe = (line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        return f'<span style="color:{color};white-space:pre;">{safe}</span>'

    def _rerender(self):
        query = self.filter_box.text().strip().lower()
        self.log_view.clear()
        cursor = self.log_view.textCursor()
        shown = [ln for ln in self._log_buffer if not query or query in ln.lower()]
        for line in shown[-_MAX_BUFFER_LINES:]:
            cursor.insertHtml(self._colorize(line) + "<br>")
        if not self._paused:
            self.log_view.moveCursor(QTextCursor.End)
            self.log_view.ensureCursorVisible()

    def _on_pause_toggled(self, checked: bool):
        self._paused = checked

    def _clear(self):
        self._log_buffer.clear()
        self.log_view.clear()

    def _copy_log(self):
        QGuiApplication.clipboard().setText(self.log_view.toPlainText())

    def _export(self):
        target, _ = QFileDialog.getSaveFileName(self, "Export log", "nfstr_modmenu_log.txt")
        if target:
            with open(target, "w", encoding="utf-8") as f:
                f.write(self.log_view.toPlainText())

    def _open_folder(self):
        folder = os.path.dirname(self.log_file_path)
        try:
            os.startfile(folder)
        except Exception:
            pass
