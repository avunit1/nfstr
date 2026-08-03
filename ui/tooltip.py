from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QPoint, QRect, QEvent, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QWidget, QLabel, QVBoxLayout, QToolButton,
                                 QGraphicsOpacityEffect, QApplication)

from . import theme
from .icons import svg_icon

_PIN_COLOR = theme.DARK.success


class InfoPopover(QWidget):

    def __init__(self, reduced_motion: bool = False):
        super().__init__(None, Qt.ToolTip | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.reduced_motion = reduced_motion

        self.container = QWidget(self)
        self.container.setObjectName("Popover")


        self.container.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        self.title_label = QLabel()
        self.title_label.setObjectName("PopoverTitle")
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        self.body_label = QLabel()
        self.body_label.setObjectName("PopoverBody")
        self.body_label.setWordWrap(True)
        self.body_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.body_label)

        self.warning_label = QLabel()
        self.warning_label.setObjectName("PopoverWarning")
        self.warning_label.setWordWrap(True)
        self.warning_label.hide()
        layout.addWidget(self.warning_label)

        self.danger_label = QLabel()
        self.danger_label.setObjectName("PopoverDanger")
        self.danger_label.setWordWrap(True)
        self.danger_label.hide()
        layout.addWidget(self.danger_label)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.addWidget(self.container)

        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._opacity.setOpacity(0.0)
        self._anim = QPropertyAnimation(self._opacity, b"opacity", self)
        self._anim.setDuration(0 if reduced_motion else theme.DUR_FAST)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        self.setFixedWidth(300)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._do_hide)


        self.pinned_owner = None
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def set_content(self, title: str, body: str, warning: str = "", danger: str = ""):
        self.title_label.setText(title)
        self.body_label.setText(body)
        self.body_label.setVisible(bool(body))
        self.warning_label.setText(f"\u26A0 {warning}" if warning else "")
        self.warning_label.setVisible(bool(warning))
        self.danger_label.setText(f"\u2716 {danger}" if danger else "")
        self.danger_label.setVisible(bool(danger))
        self.adjustSize()

    def show_near(self, anchor_global_pos: QPoint, anchor_size):
        screen = QGuiApplication.screenAt(anchor_global_pos) or QGuiApplication.primaryScreen()
        screen_rect = screen.availableGeometry()

        x = anchor_global_pos.x()
        y = anchor_global_pos.y() + anchor_size.height() + 4
        self.adjustSize()
        w = self.width()
        h = self.height()

        if x + w > screen_rect.right():
            x = screen_rect.right() - w - 8
        if x < screen_rect.left():
            x = screen_rect.left() + 8
        if y + h > screen_rect.bottom():
            y = anchor_global_pos.y() - h - 4

        self.move(x, y)
        self._hide_timer.stop()
        self.show()
        self.raise_()
        self._anim.stop()
        self._anim.setStartValue(self._opacity.opacity())
        self._anim.setEndValue(1.0)
        self._anim.start()

    def request_hide(self, delay_ms: int = 120):
        self._hide_timer.start(delay_ms)

    def cancel_hide(self):
        self._hide_timer.stop()

    def _do_hide(self):
        if not self.reduced_motion:
            self._anim.stop()
            self._anim.setStartValue(self._opacity.opacity())
            self._anim.setEndValue(0.0)
            try:
                self._anim.finished.disconnect()
            except (RuntimeError, TypeError):
                pass
            self._anim.finished.connect(self.hide)
            self._anim.start()
        else:
            self.hide()

    def enterEvent(self, event):
        self.cancel_hide()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.request_hide()
        super().leaveEvent(event)


    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress and self.pinned_owner is not None:
            owner = self.pinned_owner
            pos = event.globalPosition().toPoint()
            owner_rect = QRect(owner.mapToGlobal(QPoint(0, 0)), owner.size())
            if not self.geometry().contains(pos) and not owner_rect.contains(pos):
                owner.set_pinned(False)
        return False


class InfoButton(QToolButton):

    def __init__(self, title: str, body: str, warning: str = "", danger: str = "",
                 popover: InfoPopover | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("InfoBtn")
        self.setFixedSize(22, 22)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self._title = title
        self._body = body
        self._warning = warning
        self._danger = danger
        self._popover = popover or InfoPopover()
        self._icon_color = theme.DARK.text_disabled
        self._pinned = False
        self.setIcon(svg_icon("info", self._icon_color, 15))
        self.setIconSize(self.size() * 0.7)
        self.clicked.connect(self._on_clicked)

    def set_palette_colors(self, dim_color: str, hover_color: str):
        self._icon_color = dim_color
        if not self._pinned:
            self.setIcon(svg_icon("info", dim_color, 15))

    def _other_button_is_pinned(self) -> bool:
        return self._popover.pinned_owner not in (None, self)

    def enterEvent(self, event):
        if not self._other_button_is_pinned():
            self._open()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self._popover.pinned_owner is not self:
            self._popover.request_hide()
        super().leaveEvent(event)

    def focusInEvent(self, event):
        if not self._other_button_is_pinned():
            self._open()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        if self._popover.pinned_owner is not self:
            self._popover.request_hide()
        super().focusOutEvent(event)

    def _on_clicked(self):
        self.set_pinned(not self._pinned)
        if not self._pinned and self.underMouse():
            self._open()

    def set_pinned(self, pinned: bool):
        self._pinned = pinned
        if pinned:
            self._popover.pinned_owner = self
            self._open()
        else:
            if self._popover.pinned_owner is self:
                self._popover.pinned_owner = None
            self._popover.request_hide(0)
        self.setIcon(svg_icon("info", _PIN_COLOR if pinned else self._icon_color, 15))

    def _open(self):
        self._popover.set_content(self._title, self._body, self._warning, self._danger)
        pos = self.mapToGlobal(QPoint(0, 0))
        self._popover.show_near(pos, self.size())
