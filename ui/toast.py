from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, QParallelAnimationGroup
from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QGraphicsOpacityEffect

from . import theme
from .icons import svg_icon

_KIND_STYLE = {
    "success": ("check", lambda p: p.success),
    "warning": ("warning", lambda p: p.warning),
    "error": ("close", lambda p: p.danger),
    "info": ("info", lambda p: p.accent),
}


class Toast(QWidget):
    def __init__(self, parent, text: str, kind: str, palette, reduced_motion: bool, duration_ms: int):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.reduced_motion = reduced_motion
        self.duration_ms = duration_ms

        icon_name, color_fn = _KIND_STYLE.get(kind, _KIND_STYLE["info"])
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 16, 10)
        layout.setSpacing(10)

        icon_label = QLabel()
        icon_label.setPixmap(svg_icon(icon_name, color_fn(palette), 18).pixmap(18, 18))
        layout.addWidget(icon_label)

        text_label = QLabel(text)
        text_label.setObjectName("ToastText")
        text_label.setWordWrap(True)
        layout.addWidget(text_label, 1)

        self.setFixedWidth(320)
        self.adjustSize()

        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._opacity.setOpacity(0.0)

    def start_lifecycle(self, on_finished):
        fade_dur = 0 if self.reduced_motion else theme.DUR_MED
        fade_in = QPropertyAnimation(self._opacity, b"opacity", self)
        fade_in.setDuration(fade_dur)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(QEasingCurve.OutCubic)
        fade_in.start(QPropertyAnimation.DeleteWhenStopped)
        self._fade_in_ref = fade_in

        def begin_exit():
            fade_out = QPropertyAnimation(self._opacity, b"opacity", self)
            fade_out.setDuration(fade_dur)
            fade_out.setStartValue(1.0)
            fade_out.setEndValue(0.0)
            fade_out.setEasingCurve(QEasingCurve.InCubic)
            fade_out.finished.connect(on_finished)
            fade_out.start(QPropertyAnimation.DeleteWhenStopped)
            self._fade_out_ref = fade_out

        QTimer.singleShot(self.duration_ms, begin_exit)


class ToastManager:

    MARGIN = 16
    GAP = 10

    def __init__(self, host: QWidget):
        self.host = host
        self._toasts: list[Toast] = []
        self.reduced_motion = False
        self.palette = theme.DARK
        self.enabled = True

    def set_palette(self, palette):
        self.palette = palette

    def show(self, text: str, kind: str = "info", duration_ms: int = 3800):
        if not self.enabled:
            return
        toast = Toast(self.host, text, kind, self.palette, self.reduced_motion, duration_ms)
        toast.setObjectName("Toast")
        toast.show()
        toast.raise_()
        self._toasts.append(toast)
        self._reflow()

        def cleanup():
            if toast in self._toasts:
                self._toasts.remove(toast)
            toast.deleteLater()
            self._reflow()

        toast.start_lifecycle(cleanup)

    def _reflow(self):
        host_w = self.host.width()
        y = self.MARGIN + 64
        for toast in self._toasts:
            toast.adjustSize()
            x = host_w - toast.width() - self.MARGIN
            target = QPoint(x, y)
            if toast.pos() != target:
                toast.move(target)
            y += toast.height() + self.GAP

    def reposition(self):
        self._reflow()
