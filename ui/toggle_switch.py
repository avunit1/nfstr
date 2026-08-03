from __future__ import annotations

from PySide6.QtCore import (Qt, QPropertyAnimation, QEasingCurve, Property,
                             Signal, QRectF, QSize)
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import QWidget, QSizePolicy

from . import theme


class ToggleSwitch(QWidget):
    toggled = Signal(bool)

    def __init__(self, parent=None, reduced_motion: bool = False):
        super().__init__(parent)
        self._checked = False
        self._pos = 0.0
        self._hover = False
        self._enabled_track = True
        self.reduced_motion = reduced_motion
        self.palette_obj = theme.DARK

        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setFixedSize(QSize(42, 24))

        self._anim = QPropertyAnimation(self, b"thumb_pos", self)
        self._anim.setDuration(theme.DUR_MED)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)


    def _get_pos(self) -> float:
        return self._pos

    def _set_pos(self, v: float):
        self._pos = v
        self.update()

    thumb_pos = Property(float, _get_pos, _set_pos)


    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, value: bool, animate: bool = True, emit: bool = False):
        value = bool(value)
        if value == self._checked and abs(self._pos - (1.0 if value else 0.0)) < 1e-6:
            return
        self._checked = value
        target = 1.0 if value else 0.0
        if animate and not self.reduced_motion:
            self._anim.stop()
            self._anim.setStartValue(self._pos)
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self._set_pos(target)
        if emit:
            self.toggled.emit(value)

    def setDisabledLook(self, disabled: bool):
        self._enabled_track = not disabled
        self.setEnabled(not disabled)
        self.update()

    def set_palette(self, p):
        self.palette_obj = p
        self.update()


    def mouseReleaseEvent(self, event):
        if self.isEnabled() and event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self.setChecked(not self._checked, animate=True, emit=True)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter) and self.isEnabled():
            self.setChecked(not self._checked, animate=True, emit=True)
            return
        super().keyPressEvent(event)

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def focusInEvent(self, event):
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self.update()
        super().focusOutEvent(event)


    def paintEvent(self, event):
        p = self.palette_obj
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        track_rect = QRectF(0, 2, self.width(), self.height() - 4)
        off_color = QColor(p.border)
        on_color = QColor(p.accent if self._enabled_track else p.text_disabled)
        track_color = QColor()
        track_color.setRedF(off_color.redF() + (on_color.redF() - off_color.redF()) * self._pos)
        track_color.setGreenF(off_color.greenF() + (on_color.greenF() - off_color.greenF()) * self._pos)
        track_color.setBlueF(off_color.blueF() + (on_color.blueF() - off_color.blueF()) * self._pos)

        if self._hover and self.isEnabled():
            track_color = track_color.lighter(112)

        painter.setPen(Qt.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(track_rect, track_rect.height() / 2, track_rect.height() / 2)

        if self.hasFocus():
            focus_pen = QColor(p.accent)
            focus_pen.setAlpha(140)
            painter.setPen(focus_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(track_rect.adjusted(-1.5, -1.5, 1.5, 1.5),
                                      track_rect.height() / 2 + 1, track_rect.height() / 2 + 1)

        thumb_d = self.height() - 8
        travel = self.width() - thumb_d - 8
        thumb_x = 4 + travel * self._pos
        thumb_rect = QRectF(thumb_x, 4, thumb_d, thumb_d)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#FFFFFF") if self.isEnabled() else QColor(p.text_disabled))
        painter.drawEllipse(thumb_rect)
        painter.end()
