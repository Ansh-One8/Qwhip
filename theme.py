"""
The "glass" look shared by every qwhip window.

On Windows 11 we ask Windows itself to draw a frosted, blurred "Acrylic" background
behind our window (the same effect the Start menu uses). Our widgets are then drawn
as semi-transparent glass cards on top of it, with a soft blue tint.

On older Windows (no Acrylic) we fall back to a solid dark background, so the app
always stays readable.
"""

import ctypes
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QVBoxLayout

# DwmSetWindowAttribute ids (from the Windows SDK)
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_SYSTEMBACKDROP_TYPE = 38
DWMWCP_ROUND = 2
DWMSBT_TRANSIENTWINDOW = 3  # "Acrylic": strong blur, like the Start menu
FIRST_ACRYLIC_BUILD = 22621  # Windows 11 22H2


def glass_supported():
    return sys.platform == "win32" and sys.getwindowsversion().build >= FIRST_ACRYLIC_BUILD


class _MARGINS(ctypes.Structure):
    _fields_ = [("left", ctypes.c_int), ("right", ctypes.c_int),
                ("top", ctypes.c_int), ("bottom", ctypes.c_int)]


def apply_glass(window):
    """Turn on the frosted background for a top-level window. Returns True if it worked.
    Call this before the window is shown for the first time."""
    if not glass_supported():
        return False
    window.setAttribute(Qt.WA_TranslucentBackground)  # let Windows' blur show through
    hwnd = int(window.winId())
    dwm = ctypes.windll.dwmapi

    def set_attribute(attribute, value):
        v = ctypes.c_int(value)
        return dwm.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(v), ctypes.sizeof(v)) == 0

    set_attribute(DWMWA_USE_IMMERSIVE_DARK_MODE, 1)  # dark title bar + dark acrylic tint
    set_attribute(DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND)
    # Make the blur cover the whole window, not just the title bar.
    dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(_MARGINS(-1, -1, -1, -1)))
    return set_attribute(DWMWA_SYSTEMBACKDROP_TYPE, DWMSBT_TRANSIENTWINDOW)


def style(glass, extra=""):
    """The shared stylesheet. `glass` = is the Acrylic background active?"""
    if glass:
        # A soft blue tint over the blur, like the reference design.
        root = ("background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
                "stop:0 rgba(40, 80, 190, 70), stop:0.6 rgba(15, 25, 60, 90), stop:1 rgba(10, 14, 30, 120));")
    else:
        root = "background: #161b22;"
    return f"""
#surface {{ {root} }}
QWidget {{ color: #eef2ff; font-size: 13px; font-family: "Segoe UI Variable", "Segoe UI"; background: transparent; }}
QToolTip {{ background: #1f2533; color: #eef2ff; border: 1px solid rgba(255,255,255,40); }}

/* glass cards */
#card, #row, QGroupBox {{
    background: rgba(255, 255, 255, 16);
    border: 1px solid rgba(255, 255, 255, 34);
    border-radius: 14px;
}}
#row:hover {{ background: rgba(255, 255, 255, 24); }}
QGroupBox {{ margin-top: 18px; padding: 12px 10px 10px 10px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; color: rgba(238, 242, 255, 150); }}
#notice {{ background: rgba(255, 196, 70, 30); border: 1px solid rgba(255, 196, 70, 90); border-radius: 12px; }}
#undo {{ background: rgba(255, 255, 255, 22); border: 1px solid rgba(255, 255, 255, 45); border-radius: 12px; }}

#num {{ color: rgba(238, 242, 255, 120); font-size: 18px; font-weight: 600; min-width: 22px; }}
#dim, #window, #hint {{ color: rgba(238, 242, 255, 130); font-size: 11px; }}
#empty {{ color: rgba(238, 242, 255, 140); font-size: 13px; padding: 40px; }}
#ok {{ color: #7ee2a8; }}
#bad, #error {{ color: #ff9b94; }}

/* inputs */
QLineEdit, QKeySequenceEdit, QComboBox {{
    background: rgba(0, 0, 0, 70);
    border: 1px solid rgba(255, 255, 255, 38);
    border-radius: 8px; padding: 6px 8px;
}}
QLineEdit:focus, QKeySequenceEdit:focus {{ border-color: rgba(120, 170, 255, 220); }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{ background: #1f2533; border: 1px solid rgba(255,255,255,40);
    selection-background-color: #3b6ff0; }}

/* buttons */
QPushButton {{
    background: rgba(255, 255, 255, 26);
    border: 1px solid rgba(255, 255, 255, 46);
    border-radius: 9px; padding: 6px 12px;
}}
QPushButton:hover {{ background: rgba(255, 255, 255, 44); }}
QPushButton:pressed {{ background: rgba(255, 255, 255, 18); }}
QPushButton#small {{ padding: 2px 7px; min-width: 14px; border-radius: 7px; }}
QPushButton#primary {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #5b8cff, stop:1 #2f62e6);
    border: 1px solid rgba(160, 195, 255, 160); font-weight: 600; padding: 7px 18px;
}}
QPushButton#primary:hover {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #73a0ff, stop:1 #3d70f0); }}
QPushButton:disabled {{ color: rgba(238, 242, 255, 70); background: rgba(255, 255, 255, 10); }}

QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid rgba(255,255,255,110);
    border-radius: 4px; background: rgba(0, 0, 0, 60); }}
QCheckBox::indicator:checked {{ background: #4c7dff; border-color: #8fb0ff; }}

QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QScrollBar:vertical {{ width: 8px; background: transparent; }}
QScrollBar::handle:vertical {{ background: rgba(255,255,255,50); border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
{extra}
"""


def make_glass(window, extra=""):
    """Try Acrylic on `window` and return (surface, glass).

    Put your layout on `surface`: a full-size panel inside the window that paints the
    tint (over Acrylic) or a solid background (without it). Painting it on a child
    widget, not the window itself, works reliably whether or not the window is
    see-through.
    """
    glass = apply_glass(window)
    surface = QFrame(window)
    surface.setObjectName("surface")
    outer = QVBoxLayout(window)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.addWidget(surface)
    window.setStyleSheet(style(glass, extra))
    return surface, glass
