"""Цвета, шрифты и QSS — те же токены, что в index.html у XM4 Control."""
from PySide6.QtGui import QColor, QFont, QFontDatabase

BG = "#06080b"
PANEL = "#0c1015"
PANEL2 = "#11161d"
LINE = "#1b232d"
LINE2 = "#26313d"
TEXT = "#dfe7ee"
MUTED = "#6b7a89"
DIM = "#3a4653"
CY = "#39d8f0"
OK = "#3ddc84"
BAD = "#ff4d5e"

DEFAULT_ACC = "#ff6a1a"
DEFAULT_ACC2 = "#ffb27a"

_acc = {"acc": QColor(DEFAULT_ACC), "acc2": QColor(DEFAULT_ACC2)}

UI_FAMILY = "Segoe UI"
MONO_FAMILY = "Consolas"


def init_fonts():
    global UI_FAMILY, MONO_FAMILY
    have = set(QFontDatabase.families())
    for f in ("Segoe UI Variable", "Segoe UI", "Inter", "Noto Sans", "DejaVu Sans"):
        if f in have:
            UI_FAMILY = f
            break
    for f in ("Cascadia Mono", "JetBrains Mono", "Consolas", "DejaVu Sans Mono", "Courier New"):
        if f in have:
            MONO_FAMILY = f
            break


def acc() -> QColor:
    return QColor(_acc["acc"])


def acc2() -> QColor:
    return QColor(_acc["acc2"])


def col(hexstr: str, alpha: int | None = None) -> QColor:
    c = QColor(hexstr)
    if alpha is not None:
        c.setAlpha(alpha)
    return c


def set_accent(c: QColor | None):
    """Акцент из обложки (или по умолчанию оранжевый)."""
    if c is None:
        _acc["acc"] = QColor(DEFAULT_ACC)
        _acc["acc2"] = QColor(DEFAULT_ACC2)
        return
    h, s, v, _ = c.getHsvF()
    if h < 0:  # серый
        h = 0.08
        s = 0.0
    s = max(s, 0.55) if s > 0.08 else s
    a = QColor.fromHsvF(h, min(1.0, s), 1.0 if v > 0.75 else 0.92)
    b = QColor.fromHsvF(h, max(0.0, s * 0.5), 1.0)
    _acc["acc"], _acc["acc2"] = a, b


def mono(px: float, bold: bool = False, spacing: float = 0.0) -> QFont:
    f = QFont(MONO_FAMILY)
    f.setPixelSize(int(px))
    f.setBold(bold)
    if spacing:
        f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
    return f


def ui(px: float, bold: bool = False) -> QFont:
    f = QFont(UI_FAMILY)
    f.setPixelSize(int(px))
    f.setBold(bold)
    return f


def qss() -> str:
    a = acc().name()
    a2 = acc2().name()
    m = MONO_FAMILY
    return f"""
* {{ font-family: "{UI_FAMILY}"; color: {TEXT}; }}
QToolTip {{ background:{PANEL2}; color:{TEXT}; border:1px solid {a}; padding:4px 6px; }}
QPushButton {{ background:{PANEL2}; border:1px solid {LINE2}; border-radius:4px; padding:7px 12px; }}
QPushButton:hover {{ border-color:{a}; }}
QPushButton:disabled {{ color:{DIM}; }}
QPushButton#acc {{ background:{a}; border-color:{a}; color:#120700; font-weight:700; }}
QPushButton#acc:hover {{ background:{a2}; }}
QPushButton#ghost {{ background:transparent; border-color:transparent; color:{MUTED};
    font-family:"{m}"; font-weight:600; font-size:10px; padding:5px 8px; }}
QPushButton#ghost:hover {{ color:{a}; }}
QLineEdit {{ background:{BG}; border:1px solid {LINE2}; border-radius:4px; padding:7px 10px;
    font-family:"{m}"; font-size:12px; selection-background-color:{a}; selection-color:#120700; }}
QLineEdit:focus {{ border-color:{CY}; }}
QComboBox {{ background:{BG}; border:1px solid {LINE2}; border-radius:4px; padding:5px 8px;
    font-family:"{m}"; font-size:12px; min-width:110px; }}
QComboBox:hover {{ border-color:{a}; }}
QComboBox::drop-down {{ border:0; width:18px; }}
QComboBox QAbstractItemView {{ background:{PANEL2}; border:1px solid {LINE2};
    selection-background-color:{BG}; selection-color:{a}; outline:0; }}
QListWidget {{ background:{BG}; border:1px solid {LINE}; border-radius:4px; outline:0; }}
QListWidget::item {{ padding:4px 6px; border-radius:3px; }}
QListWidget::item:hover {{ background:{PANEL2}; }}
QListWidget::item:selected {{ background:{PANEL2}; color:{a}; }}
QScrollArea {{ background:transparent; border:0; }}
QScrollBar:vertical {{ background:transparent; width:8px; margin:0; }}
QScrollBar::handle:vertical {{ background:{LINE2}; border-radius:4px; min-height:24px; }}
QScrollBar::handle:vertical:hover {{ background:{DIM}; }}
QScrollBar:horizontal {{ background:transparent; height:8px; margin:0; }}
QScrollBar::handle:horizontal {{ background:{LINE2}; border-radius:4px; min-width:24px; }}
QScrollBar::handle:horizontal:hover {{ background:{DIM}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width:0; height:0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background:transparent; }}
"""
