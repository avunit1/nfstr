from __future__ import annotations

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtGui import QPainter

_CACHE: dict[tuple[str, str, int], QIcon] = {}

_PATHS = {
    "info": '<circle cx="12" cy="12" r="9" fill="none" stroke="{c}" stroke-width="1.6"/>'
            '<line x1="12" y1="11" x2="12" y2="16.5" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>'
            '<circle cx="12" cy="7.6" r="1.15" fill="{c}"/>',
    "close": '<line x1="6" y1="6" x2="18" y2="18" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/>'
             '<line x1="18" y1="6" x2="6" y2="18" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/>',
    "minimize": '<line x1="6" y1="14" x2="18" y2="14" stroke="{c}" stroke-width="1.6" stroke-linecap="round"/>',
    "maximize": '<rect x="6.5" y="6.5" width="11" height="11" rx="1.5" fill="none" stroke="{c}" stroke-width="1.5"/>',
    "restore": '<rect x="8.5" y="5.5" width="9" height="9" rx="1.3" fill="none" stroke="{c}" stroke-width="1.4"/>'
               '<path d="M6.5 8.5 H5.5 A1.5 1.5 0 0 0 4 10 V17.5 A1.5 1.5 0 0 0 5.5 19 H13 '
               'A1.5 1.5 0 0 0 14.5 17.5 V16.5" fill="none" stroke="{c}" stroke-width="1.4"/>',
    "settings": '<circle cx="12" cy="12" r="2.6" fill="none" stroke="{c}" stroke-width="1.5"/>'
                '<path d="M12 3.5v2.3M12 18.2v2.3M20.5 12h-2.3M5.8 12H3.5'
                'M17.6 6.4l-1.6 1.6M8 16l-1.6 1.6M17.6 17.6L16 16M8 8 6.4 6.4" '
                'fill="none" stroke="{c}" stroke-width="1.5" stroke-linecap="round"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6" fill="none" stroke="{c}" stroke-width="1.7"/>'
              '<line x1="15" y1="15" x2="20" y2="20" stroke="{c}" stroke-width="1.7" stroke-linecap="round"/>',
    "star_outline": '<path d="M12 4.5l2.2 4.6 5 .7-3.6 3.6.9 5-4.5-2.4-4.5 2.4.9-5-3.6-3.6 5-.7z" '
                     'fill="none" stroke="{c}" stroke-width="1.4" stroke-linejoin="round"/>',
    "star_filled": '<path d="M12 4.5l2.2 4.6 5 .7-3.6 3.6.9 5-4.5-2.4-4.5 2.4.9-5-3.6-3.6 5-.7z" '
                    'fill="{c}" stroke="{c}" stroke-width="1.4" stroke-linejoin="round"/>',
    "chevron_down": '<polyline points="6,9 12,15 18,9" fill="none" stroke="{c}" '
                     'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
    "chevron_right": '<polyline points="9,6 15,12 9,18" fill="none" stroke="{c}" '
                      'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
    "dot": '<circle cx="12" cy="12" r="5" fill="{c}"/>',
    "wrench": '<path d="M14.7 6.3a3.6 3.6 0 0 0-4.9 4l-6.1 6.1 2.1 2.1 6.1-6.1a3.6 3.6 0 0 0 '
              '4-4.9l-2.4 2.4-1.9-.6-.6-1.9 2.4-2.4z" fill="none" stroke="{c}" '
              'stroke-width="1.4" stroke-linejoin="round" stroke-linecap="round"/>',
    "warning": '<path d="M12 4.5 21 19.5H3z" fill="none" stroke="{c}" stroke-width="1.6" stroke-linejoin="round"/>'
               '<line x1="12" y1="10" x2="12" y2="14.5" stroke="{c}" stroke-width="1.7" stroke-linecap="round"/>'
               '<circle cx="12" cy="17" r="1" fill="{c}"/>',
    "check": '<polyline points="5,13 10,18 19,7" fill="none" stroke="{c}" '
              'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
    "car": '<path d="M4 15.5 5.3 11a2 2 0 0 1 1.9-1.4h9.6a2 2 0 0 1 1.9 1.4l1.3 4.5" '
           'fill="none" stroke="{c}" stroke-width="1.4" stroke-linejoin="round"/>'
           '<rect x="3.2" y="15.3" width="17.6" height="3.6" rx="1.3" fill="none" stroke="{c}" stroke-width="1.4"/>'
           '<circle cx="7.3" cy="18.9" r="1.3" fill="{c}"/><circle cx="16.7" cy="18.9" r="1.3" fill="{c}"/>',
    "gauge": '<circle cx="12" cy="13" r="7.5" fill="none" stroke="{c}" stroke-width="1.4"/>'
             '<line x1="12" y1="13" x2="15.2" y2="9.5" stroke="{c}" stroke-width="1.5" stroke-linecap="round"/>'
             '<line x1="12" y1="6.5" x2="12" y2="5" stroke="{c}" stroke-width="1.4"/>',
    "shield": '<path d="M12 3.5 19 6.5v5.2c0 4.6-3 7.8-7 9-4-1.2-7-4.4-7-9V6.5z" '
              'fill="none" stroke="{c}" stroke-width="1.4" stroke-linejoin="round"/>',
    "flag": '<line x1="6" y1="4" x2="6" y2="20" stroke="{c}" stroke-width="1.4" stroke-linecap="round"/>'
            '<path d="M6 5h11l-2.5 3.5L17 12H6z" fill="none" stroke="{c}" stroke-width="1.4" stroke-linejoin="round"/>',
    "layers": '<polygon points="12,4 21,9 12,14 3,9" fill="none" stroke="{c}" stroke-width="1.4" stroke-linejoin="round"/>'
              '<polyline points="3,13 12,18 21,13" fill="none" stroke="{c}" stroke-width="1.4" stroke-linejoin="round"/>',
    "globe": '<circle cx="12" cy="12" r="8" fill="none" stroke="{c}" stroke-width="1.4"/>'
             '<ellipse cx="12" cy="12" rx="3.4" ry="8" fill="none" stroke="{c}" stroke-width="1.2"/>'
             '<line x1="4" y1="12" x2="20" y2="12" stroke="{c}" stroke-width="1.2"/>',
    "timer": '<circle cx="12" cy="13" r="7.5" fill="none" stroke="{c}" stroke-width="1.4"/>'
             '<line x1="12" y1="13" x2="12" y2="9" stroke="{c}" stroke-width="1.4" stroke-linecap="round"/>'
             '<line x1="9.5" y1="3.5" x2="14.5" y2="3.5" stroke="{c}" stroke-width="1.4" stroke-linecap="round"/>',
    "zap": '<polygon points="13,3 5,14 11,14 9,21 19,10 13,10" fill="{c}"/>',
    "sliders": '<line x1="5" y1="6" x2="19" y2="6" stroke="{c}" stroke-width="1.4"/>'
               '<line x1="5" y1="12" x2="19" y2="12" stroke="{c}" stroke-width="1.4"/>'
               '<line x1="5" y1="18" x2="19" y2="18" stroke="{c}" stroke-width="1.4"/>'
               '<circle cx="9" cy="6" r="1.6" fill="{c}"/><circle cx="15" cy="12" r="1.6" fill="{c}"/>'
               '<circle cx="8" cy="18" r="1.6" fill="{c}"/>',
}


def _render_svg(name: str, color: str, size: int) -> QPixmap:
    body = _PATHS.get(name, _PATHS["dot"]).format(c=color)
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{body}</svg>'
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))


    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter)
    painter.end()
    return QPixmap.fromImage(img)


def svg_icon(name: str, color: str, size: int = 20) -> QIcon:
    key = (name, color, size)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    icon = QIcon(_render_svg(name, color, size))
    _CACHE[key] = icon
    return icon


def svg_pixmap(name: str, color: str, size: int = 20) -> QPixmap:
    return _render_svg(name, color, size)


CATEGORY_ICONS = {
    "Performance": "gauge",
    "Crash Fixes": "shield",
    "Timers": "timer",
    "Assists": "sliders",
    "Vehicle": "car",
    "Game": "layers",
    "AI / Race Setup": "flag",
    "Traffic": "car",
    "World": "globe",
    "UI": "layers",
}
