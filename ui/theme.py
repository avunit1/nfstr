from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    bg: str
    sidebar: str
    surface: str
    surface_hover: str
    surface_active: str
    border: str
    text_primary: str
    text_secondary: str
    text_disabled: str
    accent: str
    accent_hover: str
    accent_text: str
    success: str
    warning: str
    danger: str
    danger_hover: str
    overlay: str


DARK = Palette(
    bg="#0B0D10",
    sidebar="#111318",
    surface="#161A20",
    surface_hover="#1D222B",
    surface_active="#20272F",
    border="#252B36",
    text_primary="#F3F4F6",
    text_secondary="#9CA3AF",
    text_disabled="#5B6472",
    accent="#4F8CFF",
    accent_hover="#6AA2FF",
    accent_text="#FFFFFF",
    success="#22C55E",
    warning="#F59E0B",
    danger="#EF4444",
    danger_hover="#F87171",
    overlay="rgba(4, 5, 7, 0.55)",
)


DARKER = Palette(
    bg="#07080A",
    sidebar="#0A0C10",
    surface="#0F1216",
    surface_hover="#161A20",
    surface_active="#191E25",
    border="#1C212B",
    text_primary="#ECEDEF",
    text_secondary="#8B94A3",
    text_disabled="#4C5560",
    accent="#4F8CFF",
    accent_hover="#6AA2FF",
    accent_text="#FFFFFF",
    success="#22C55E",
    warning="#F59E0B",
    danger="#EF4444",
    danger_hover="#F87171",
    overlay="rgba(2, 3, 4, 0.6)",
)

RISK_COLOR = {"low": DARK.success, "medium": DARK.warning, "high": DARK.danger}

FONT_FAMILY = '"Segoe UI Variable Text", "Segoe UI", "Inter", "Segoe UI Semibold", sans-serif'
FONT_FAMILY_MONO = '"Cascadia Code", "Cascadia Mono", "Consolas", monospace'

RADIUS = 10
RADIUS_SM = 7
RADIUS_LG = 14


DUR_FAST = 120
DUR_MED = 160
DUR_SLOW = 220


def build_stylesheet(p: Palette) -> str:
    return f"""
    * {{
        font-family: {FONT_FAMILY};
        outline: none;
    }}

    QWidget {{
        background-color: transparent;
        color: {p.text_primary};
        font-size: 13px;
    }}

    QMainWindow, #RootShell {{
        background-color: {p.bg};
    }}

    #StatusHeader {{
        background-color: {p.bg};
        border-bottom: 1px solid {p.border};
    }}
    QLabel#StatusTitle {{
        font-size: 14px;
        font-weight: 600;
        color: {p.text_primary};
    }}
    QLabel#StatusSubtitle {{
        font-size: 12px;
        color: {p.text_secondary};
    }}
    QLabel#StatusDotOn {{
        color: {p.success};
        font-size: 15px;
    }}
    QLabel#StatusDotOff {{
        color: {p.danger};
        font-size: 15px;
    }}

    #Sidebar {{
        background-color: {p.sidebar};
        border-right: 1px solid {p.border};
    }}
    QPushButton#SidebarItem {{
        text-align: left;
        border: none;
        border-radius: {RADIUS_SM}px;
        padding: 9px 12px;
        color: {p.text_secondary};
        font-size: 13px;
        font-weight: 500;
        background: transparent;
    }}
    QPushButton#SidebarItem:hover {{
        background-color: {p.surface_hover};
        color: {p.text_primary};
    }}
    QPushButton#SidebarItem:checked {{
        background-color: {p.surface_active};
        color: {p.text_primary};
        border-left: 3px solid {p.accent};
        padding-left: 9px;
    }}
    QLabel#SidebarSection {{
        color: {p.text_disabled};
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1px;
        padding: 14px 12px 4px 12px;
    }}

    #ContentArea {{
        background-color: {p.bg};
    }}
    QLabel#CategoryTitle {{
        font-size: 18px;
        font-weight: 600;
        color: {p.text_primary};
    }}
    QLabel#CategoryCount {{
        font-size: 12px;
        color: {p.text_secondary};
    }}

    #FeatureRow {{
        background-color: {p.surface};
        border: 1px solid {p.border};
        border-radius: {RADIUS}px;
    }}
    #FeatureRow[hovered="true"] {{
        background-color: {p.surface_hover};
    }}
    #FeatureRow[flagged="true"] {{
        border: 1px solid {p.danger};
    }}
    QLabel#FeatureLabel {{
        font-size: 13.5px;
        font-weight: 500;
        color: {p.text_primary};
    }}
    QLabel#FeatureLabel[dim="true"] {{
        color: {p.text_disabled};
    }}

    QToolButton#InfoBtn {{
        border: none;
        border-radius: 9px;
        background-color: transparent;
        color: {p.text_disabled};
        font-weight: 700;
        font-size: 11px;
    }}
    QToolButton#InfoBtn:hover {{
        background-color: {p.surface_active};
        color: {p.text_secondary};
    }}

    QPushButton#ApplyBtn {{
        background-color: {p.accent};
        color: {p.accent_text};
        border: none;
        border-radius: {RADIUS_SM}px;
        padding: 6px 14px;
        font-weight: 600;
        font-size: 12px;
    }}
    QPushButton#ApplyBtn:hover {{ background-color: {p.accent_hover}; }}
    QPushButton#ApplyBtn:disabled {{
        background-color: {p.surface_active};
        color: {p.text_disabled};
    }}

    QPushButton#GhostBtn {{
        background-color: {p.surface};
        color: {p.text_secondary};
        border: 1px solid {p.border};
        border-radius: {RADIUS_SM}px;
        padding: 7px 12px;
        font-weight: 500;
        font-size: 12px;
    }}
    QPushButton#GhostBtn:hover {{
        background-color: {p.surface_hover};
        color: {p.text_primary};
    }}
    QPushButton#GhostBtn:checked {{
        background-color: {p.surface_active};
        color: {p.accent};
        border-color: {p.accent};
    }}

    QPushButton#DangerBtn {{
        background-color: transparent;
        color: {p.danger};
        border: 1px solid {p.danger};
        border-radius: {RADIUS_SM}px;
        padding: 7px 12px;
        font-weight: 600;
        font-size: 12px;
    }}
    QPushButton#DangerBtn:hover {{
        background-color: {p.danger};
        color: white;
    }}

    QLineEdit, QSpinBox, QDoubleSpinBox {{
        background-color: {p.surface};
        border: 1px solid {p.border};
        border-radius: {RADIUS_SM}px;
        padding: 7px 10px;
        color: {p.text_primary};
        font-size: 13px;
        selection-background-color: {p.accent};
    }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 1px solid {p.accent};
    }}
    QLineEdit#SearchBox {{
        padding: 9px 12px 9px 34px;
        font-size: 13.5px;
        background-color: {p.surface};
    }}
    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
        width: 0px; border: none;
    }}

    QScrollArea {{ border: none; background: transparent; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}

    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {p.border};
        border-radius: 4px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {p.text_disabled}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

    QScrollBar:horizontal {{
        background: transparent; height: 10px; margin: 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: {p.border}; border-radius: 4px; min-width: 30px;
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}

    QListView#VehicleList {{
        background-color: {p.surface};
        border: 1px solid {p.border};
        border-radius: {RADIUS}px;
        padding: 4px;
    }}
    QListView#VehicleList::item {{
        border-radius: {RADIUS_SM}px;
    }}
    QListView#VehicleList::item:selected {{
        background-color: {p.surface_active};
    }}

    #Toast {{
        background-color: {p.surface};
        border: 1px solid {p.border};
        border-radius: {RADIUS}px;
    }}
    QLabel#ToastText {{
        color: {p.text_primary};
        font-size: 12.5px;
        font-weight: 500;
    }}

    #Popover {{
        background-color: {p.surface_active};
        border: 1px solid {p.border};
        border-radius: {RADIUS}px;
    }}
    QLabel#PopoverTitle {{
        color: {p.text_primary};
        font-size: 13px;
        font-weight: 700;
    }}
    QLabel#PopoverBody {{
        color: {p.text_secondary};
        font-size: 12.5px;
    }}
    QLabel#PopoverWarning {{
        color: {p.warning};
        font-size: 12px;
        font-weight: 600;
    }}
    QLabel#PopoverDanger {{
        color: {p.danger};
        font-size: 12px;
        font-weight: 700;
    }}

    QLabel#SectionHeading {{
        font-size: 15px;
        font-weight: 600;
        color: {p.text_primary};
    }}
    QLabel#FieldLabel {{
        font-size: 13px;
        font-weight: 500;
        color: {p.text_primary};
    }}
    QLabel#FieldHint {{
        font-size: 11.5px;
        color: {p.text_secondary};
    }}

    #Card {{
        background-color: {p.surface};
        border: 1px solid {p.border};
        border-radius: {RADIUS}px;
    }}

    #DevPanel {{
        background-color: {p.bg};
    }}
    QTextEdit#LogView, QPlainTextEdit#LogView {{
        background-color: {p.surface};
        border: 1px solid {p.border};
        border-radius: {RADIUS_SM}px;
        color: {p.text_secondary};
        font-family: {FONT_FAMILY_MONO};
        font-size: 12px;
        padding: 8px;
    }}
    QLabel#KVKey {{
        color: {p.text_secondary};
        font-size: 12px;
    }}
    QLabel#KVVal {{
        color: {p.text_primary};
        font-family: {FONT_FAMILY_MONO};
        font-size: 12px;
    }}

    QComboBox {{
        background-color: {p.surface};
        border: 1px solid {p.border};
        border-radius: {RADIUS_SM}px;
        padding: 7px 10px;
        color: {p.text_primary};
    }}
    QComboBox QAbstractItemView {{
        background-color: {p.surface_active};
        border: 1px solid {p.border};
        selection-background-color: {p.accent};
        color: {p.text_primary};
        outline: none;
    }}

    QCheckBox {{
        color: {p.text_primary};
        font-size: 13px;
        spacing: 8px;
    }}
    QCheckBox::indicator {{
        width: 16px; height: 16px;
        border-radius: 4px;
        border: 1.5px solid {p.border};
        background: {p.surface};
    }}
    QCheckBox::indicator:checked {{
        background: {p.accent};
        border-color: {p.accent};
    }}

    QToolTip {{
        background-color: {p.surface_active};
        color: {p.text_primary};
        border: 1px solid {p.border};
        padding: 4px;
    }}
    """


def get_palette(name: str) -> Palette:
    return DARKER if name == "darker" else DARK
