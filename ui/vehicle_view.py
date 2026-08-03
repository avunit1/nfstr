from __future__ import annotations

import re

from PySide6.QtCore import (Qt, QAbstractListModel, QModelIndex, QRect,
                              QSize, Signal, QTimer, QEvent, QRectF)
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
                                 QLabel, QListView, QStyledItemDelegate,
                                 QStyle, QPushButton, QSizePolicy)

from . import theme
from .icons import svg_pixmap


_KNOWN_MANUFACTURERS = sorted([
    "Aston Martin", "Mercedes-Benz", "Mercedes", "Alfa Romeo", "Land Rover",
    "Audi", "Bentley", "BMW", "Bugatti", "Cadillac", "Chevrolet", "Chrysler",
    "Dodge", "Ferrari", "Ford", "GMC", "Gumpert", "Hennessey", "Holden",
    "Hyundai", "Infiniti", "Jaguar", "Jeep", "Koenigsegg", "Lamborghini",
    "Lexus", "Lotus", "Maserati", "Mazda", "McLaren", "Mitsubishi", "Nissan",
    "Noble", "Pagani", "Pontiac", "Porsche", "RUF", "Saleen", "Scion",
    "Shelby", "Spyker", "SSC", "Subaru", "Toyota", "Vauxhall", "Volkswagen",
    "Volvo", "Zenvo", "Ariel", "Wiesmann", "TVR",
], key=len, reverse=True)

_YEAR_RE = re.compile(r"_(\d{2})(?:_|$)")


def derive_manufacturer(vehicle_name: str) -> str:
    base = vehicle_name.split(" - ")[0].strip()
    for brand in _KNOWN_MANUFACTURERS:
        if base.startswith(brand):
            return brand
    return base.split(" ")[0] if base else ""


def derive_year(entry_id: str) -> int | None:
    m = _YEAR_RE.search(entry_id)
    if not m:
        return None
    yy = int(m.group(1))
    return 1900 + yy if yy > 30 else 2000 + yy


ROLE_DATA = Qt.UserRole + 1
ROW_HEIGHT = 58
STAR_SIZE = 18


class VehicleListModel(QAbstractListModel):
    def __init__(self, vehicles: list[dict], favorites: set[str], parent=None):
        super().__init__(parent)
        self._all = []
        for v in vehicles:
            item = dict(v)
            item["manufacturer"] = derive_manufacturer(v["vehicle"])
            item["year"] = derive_year(v["entry"])
            self._all.append(item)
        self._favorites = favorites
        self._visible: list[dict] = list(self._all)

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._visible)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        item = self._visible[index.row()]
        if role == Qt.DisplayRole:
            return item["vehicle"]
        if role == ROLE_DATA:
            return item
        if role == Qt.UserRole + 2:
            return item["entry"] in self._favorites
        return None

    def item_at(self, row: int) -> dict | None:
        if 0 <= row < len(self._visible):
            return self._visible[row]
        return None

    def is_favorite(self, entry_id: str) -> bool:
        return entry_id in self._favorites

    def toggle_favorite(self, entry_id: str):
        if entry_id in self._favorites:
            self._favorites.discard(entry_id)
        else:
            self._favorites.add(entry_id)

    def set_filter(self, query: str, favorites_only: bool):
        q = query.strip().lower()

        def matches(v: dict) -> bool:
            if favorites_only and v["entry"] not in self._favorites:
                return False
            if not q:
                return True
            if q in v["vehicle"].lower() or q in v["entry"].lower() or q in v["section"].lower():
                return True
            if q in v["manufacturer"].lower():
                return True
            if v["year"] and q in str(v["year"]):
                return True
            return False

        self.beginResetModel()
        self._visible = [v for v in self._all if matches(v)]
        self.endResetModel()

    def total_count(self) -> int:
        return len(self._all)

    def visible_count(self) -> int:
        return len(self._visible)


class VehicleDelegate(QStyledItemDelegate):
    favorite_toggled = Signal(str)

    def __init__(self, palette, parent=None):
        super().__init__(parent)
        self.palette_obj = palette
        self._name_font = QFont()
        self._name_font.setPointSize(11)
        self._name_font.setWeight(QFont.DemiBold)
        self._meta_font = QFont()
        self._meta_font.setPointSize(9)

    def sizeHint(self, option, index) -> QSize:
        return QSize(option.rect.width(), ROW_HEIGHT)

    def _star_rect(self, option) -> QRect:
        r = option.rect
        return QRect(r.right() - STAR_SIZE - 14, r.top() + (r.height() - STAR_SIZE) // 2, STAR_SIZE, STAR_SIZE)

    def paint(self, painter: QPainter, option, index: QModelIndex):
        item = index.data(ROLE_DATA)
        if item is None:
            return
        p = self.palette_obj
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)
        rect = QRectF(option.rect).adjusted(2, 2, -2, -2)
        if selected:
            painter.setBrush(QColor(p.surface_active))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(rect, 8, 8)
        elif hovered:
            painter.setBrush(QColor(p.surface_hover))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(rect, 8, 8)

        text_left = option.rect.left() + 14
        text_right = self._star_rect(option).left() - 10

        painter.setFont(self._name_font)
        painter.setPen(QColor(p.text_primary))
        name_rect = QRect(text_left, option.rect.top() + 9, text_right - text_left, 20)
        fm = QFontMetrics(self._name_font)
        elided = fm.elidedText(item["vehicle"], Qt.ElideRight, name_rect.width())
        painter.drawText(name_rect, Qt.AlignVCenter | Qt.AlignLeft, elided)

        meta_bits = [item["entry"]]
        if item.get("year"):
            meta_bits.append(str(item["year"]))
        if item.get("section") and item["section"] != "Base Game":
            meta_bits.append(item["section"])
        meta_text = "  \u00B7  ".join(meta_bits)
        painter.setFont(self._meta_font)
        painter.setPen(QColor(p.text_secondary))
        meta_rect = QRect(text_left, option.rect.top() + 31, text_right - text_left, 16)
        meta_elided = QFontMetrics(self._meta_font).elidedText(meta_text, Qt.ElideRight, meta_rect.width())
        painter.drawText(meta_rect, Qt.AlignVCenter | Qt.AlignLeft, meta_elided)

        star_rect = self._star_rect(option)
        is_fav = index.data(Qt.UserRole + 2)
        star_pix = svg_pixmap("star_filled" if is_fav else "star_outline",
                                p.warning if is_fav else p.text_disabled, STAR_SIZE)
        painter.drawPixmap(star_rect, star_pix)

        painter.restore()

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            if self._star_rect(option).contains(event.position().toPoint()):
                item = index.data(ROLE_DATA)
                if item:
                    self.favorite_toggled.emit(item["entry"])
                return True
        return False


class SearchLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._icon_label = QLabel(self)
        self._icon_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setObjectName("SearchBox")
        self._refresh_icon()

    def set_icon_color(self, color: str):
        self._icon_pix = svg_pixmap("search", color, 15)
        self._icon_label.setPixmap(self._icon_pix)
        self._icon_label.adjustSize()
        self._position_icon()

    def _refresh_icon(self):
        self.set_icon_color(theme.DARK.text_disabled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_icon()

    def _position_icon(self):
        y = (self.height() - self._icon_label.height()) // 2
        self._icon_label.move(11, max(0, y))


class VehicleView(QWidget):
    apply_requested = Signal(dict)
    status_message = Signal(str)
    favorites_changed = Signal()

    def __init__(self, vehicles: list[dict], favorites: set[str], parent=None):
        super().__init__(parent)
        self.palette_obj = theme.DARK
        self.model = VehicleListModel(vehicles, favorites)
        self._attached = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 18)
        outer.setSpacing(12)

        header_row = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Vehicle Swap")
        title.setObjectName("CategoryTitle")
        title_col.addWidget(title)
        self.count_label = QLabel()
        self.count_label.setObjectName("CategoryCount")
        title_col.addWidget(self.count_label)
        header_row.addLayout(title_col)
        header_row.addStretch(1)
        outer.addLayout(header_row)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self.search_box = SearchLineEdit()
        self.search_box.setPlaceholderText("Search by name, internal ID, manufacturer, or year\u2026")
        self.search_box.textChanged.connect(self._on_search_changed)
        search_row.addWidget(self.search_box, 1)

        self.favorites_btn = QPushButton("\u2605 Favorites")
        self.favorites_btn.setObjectName("GhostBtn")
        self.favorites_btn.setCheckable(True)
        self.favorites_btn.setCursor(Qt.PointingHandCursor)
        self.favorites_btn.toggled.connect(self._refresh)
        search_row.addWidget(self.favorites_btn)
        outer.addLayout(search_row)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(60)
        self._debounce.timeout.connect(self._refresh)

        self.list_view = QListView()
        self.list_view.setObjectName("VehicleList")
        self.list_view.setModel(self.model)
        self.list_view.setUniformItemSizes(True)
        self.list_view.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.list_view.setSelectionMode(QListView.SingleSelection)
        self.list_view.setMouseTracking(True)
        self.delegate = VehicleDelegate(self.palette_obj)
        self.delegate.favorite_toggled.connect(self._on_favorite_toggled)
        self.list_view.setItemDelegate(self.delegate)
        self.list_view.doubleClicked.connect(self._on_double_clicked)
        self.list_view.selectionModel().selectionChanged.connect(self._on_selection_changed)
        outer.addWidget(self.list_view, 1)

        footer = QHBoxLayout()
        self.selected_label = QLabel("No vehicle selected")
        self.selected_label.setObjectName("FieldHint")
        footer.addWidget(self.selected_label, 1)

        self.apply_btn = QPushButton("Apply Swap")
        self.apply_btn.setObjectName("ApplyBtn")
        self.apply_btn.setCursor(Qt.PointingHandCursor)
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self._on_apply_clicked)
        footer.addWidget(self.apply_btn)
        outer.addLayout(footer)

        hint = QLabel("Works in single-player Challenge Series/story events while in a race or garage. "
                       "Does not work in multiplayer.")
        hint.setObjectName("FieldHint")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        self._refresh()

    def set_palette(self, palette):
        self.palette_obj = palette
        self.delegate.palette_obj = palette
        self.search_box.set_icon_color(palette.text_disabled)
        self.list_view.viewport().update()

    def set_attached(self, attached: bool):
        self._attached = attached
        self._update_apply_enabled()

    def _on_search_changed(self, _text: str):
        self._debounce.start()

    def _refresh(self):
        self.model.set_filter(self.search_box.text(), self.favorites_btn.isChecked())
        total = self.model.total_count()
        visible = self.model.visible_count()
        self.count_label.setText(f"{visible:,} of {total:,} vehicles"
                                   if visible != total else f"{total:,} vehicles")
        self.list_view.viewport().update()

    def _on_favorite_toggled(self, entry_id: str):
        self.model.toggle_favorite(entry_id)
        self.favorites_changed.emit()
        self.list_view.viewport().update()

    def _on_selection_changed(self, *_args):
        idx = self.list_view.currentIndex()
        item = self.model.item_at(idx.row()) if idx.isValid() else None
        if item:
            self.selected_label.setText(f"Selected: {item['vehicle']}")
        else:
            self.selected_label.setText("No vehicle selected")
        self._update_apply_enabled()

    def _update_apply_enabled(self):
        idx = self.list_view.currentIndex()
        self.apply_btn.setEnabled(self._attached and idx.isValid())

    def _on_double_clicked(self, index: QModelIndex):
        item = self.model.item_at(index.row())
        if item:
            self._request_apply(item)

    def _on_apply_clicked(self):
        idx = self.list_view.currentIndex()
        item = self.model.item_at(idx.row()) if idx.isValid() else None
        if item:
            self._request_apply(item)

    def _request_apply(self, item: dict):
        if not self._attached:
            self.status_message.emit("Attach to the game before swapping a vehicle.")
            return
        self.apply_requested.emit(item)

    def favorites(self) -> set[str]:
        return self.model._favorites
