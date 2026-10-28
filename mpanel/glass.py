"""Второй дизайн «Liquid»: клип на всю панель, поверх — лёгкие стеклянные карточки."""
import math
import time

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen,
                           QPolygonF, QRadialGradient)
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QListView, QListWidget, QVBoxLayout,
                               QWidget)

from . import theme as T
from .clip import ClipPlayer
from .widgets import Backdrop, Cover, ElideLabel, IconButton, TrackDelegate, VizWidget, fmt

WHITE = "#f4f8fb"
SOFT = "#aab6c2"


class Glass(QWidget):
    """Полупрозрачная «стеклянная» карточка со скруглением и светлой кромкой."""

    def __init__(self, parent=None, radius=22, alpha=150):
        super().__init__(parent)
        self.radius = radius
        self.alpha = alpha

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        r = QRectF(0.5, 0.5, w - 1, h - 1)
        rad = self.radius
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(14, 16, 22, int(self.alpha * 0.72)))
        p.drawRoundedRect(r, rad, rad)
        # мягкий свет сверху — без глянца
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0, QColor(255, 255, 255, 16))
        g.setColorAt(0.35, QColor(255, 255, 255, 0))
        p.setBrush(g)
        p.drawRoundedRect(r, rad, rad)
        # тонкая кромка: ярче у верхнего края
        b = QLinearGradient(0, 0, 0, h)
        b.setColorAt(0, QColor(255, 255, 255, 70))
        b.setColorAt(0.4, QColor(255, 255, 255, 24))
        b.setColorAt(1, QColor(255, 255, 255, 38))
        p.setPen(QPen(QBrush(b), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, rad, rad)


class Pill(QWidget):
    """Маленькая стеклянная «таблетка» с текстом."""

    def __init__(self, text="", accent=False):
        super().__init__()
        self.text_, self.accent = text, accent
        self.setFixedHeight(24)

    def set_text(self, t, accent=None):
        self.text_ = t
        if accent is not None:
            self.accent = accent
        self.updateGeometry()
        self.update()

    def sizeHint(self):
        f = T.ui(11.5, True)
        from PySide6.QtGui import QFontMetrics
        return QSize(QFontMetrics(f).horizontalAdvance(self.text_) + 22, 24)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        if self.accent:
            fill, border, fg = QColor(255, 255, 255, 235), QColor(255, 255, 255, 0), QColor("#0d0f14")
        else:
            fill, border, fg = QColor(255, 255, 255, 14), QColor(255, 255, 255, 30), QColor(WHITE)
        p.setBrush(fill)
        p.setPen(QPen(border, 1))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        p.setFont(T.ui(11, True))
        p.setPen(fg)
        p.drawText(self.rect(), Qt.AlignCenter, self.text_)


class GlassIcon(IconButton):
    """Круглая стеклянная кнопка с иконкой."""

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        on = self.isCheckable() and self.isChecked()
        hov = self.underMouse()
        r = QRectF(0.5, 0.5, w - 1, h - 1)
        p.setPen(Qt.NoPen)
        if self.primary:
            if hov:
                p.setBrush(QColor(255, 255, 255, 40))
                p.drawEllipse(r.adjusted(-3, -3, 3, 3))
            p.setBrush(QColor(255, 255, 255, 245 if hov else 232))
            p.drawEllipse(r)
            fg = QColor("#0d0f14")
        else:
            if on:
                p.setBrush(QColor(255, 255, 255, 230))
                fg = QColor("#0d0f14")
            else:
                p.setBrush(QColor(255, 255, 255, 34 if hov else 0))
                fg = QColor(WHITE)
            p.drawEllipse(r)
        self._icon(p, fg, w, h)

    def _icon(self, p, fg, w, h):
        k = self.kind
        u = min(w, h) / 40.0
        cx, cy = w / 2, h / 2
        new = ("clock", "list", "disc", "swap", "chev_d", "chev_u", "close", "back", "eye", "novideo")
        if k not in new:
            return super()._icon(p, fg, w, h)
        p.setPen(QPen(fg, max(1.6, 1.8 * u), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        if k == "clock":
            p.drawEllipse(QPointF(cx, cy), 9 * u, 9 * u)
            p.drawLine(QPointF(cx, cy), QPointF(cx, cy - 5.5 * u))
            p.drawLine(QPointF(cx, cy), QPointF(cx + 4 * u, cy + 2 * u))
        elif k == "list":
            for dy in (-6, 0, 6):
                p.drawLine(QPointF(cx - 2 * u, cy + dy * u), QPointF(cx + 9 * u, cy + dy * u))
                p.drawPoint(QPointF(cx - 8 * u, cy + dy * u))
        elif k == "disc":
            p.drawEllipse(QPointF(cx, cy), 9 * u, 9 * u)
            p.drawEllipse(QPointF(cx, cy), 2.4 * u, 2.4 * u)
        elif k == "swap":
            p.drawLine(QPointF(cx - 8 * u, cy - 4 * u), QPointF(cx + 8 * u, cy - 4 * u))
            p.drawLine(QPointF(cx + 8 * u, cy - 4 * u), QPointF(cx + 4 * u, cy - 8 * u))
            p.drawLine(QPointF(cx + 8 * u, cy + 4 * u), QPointF(cx - 8 * u, cy + 4 * u))
            p.drawLine(QPointF(cx - 8 * u, cy + 4 * u), QPointF(cx - 4 * u, cy + 8 * u))
        elif k in ("chev_d", "chev_u"):
            d = 1 if k == "chev_d" else -1
            p.drawLine(QPointF(cx - 6 * u, cy - 3 * u * d), QPointF(cx, cy + 3 * u * d))
            p.drawLine(QPointF(cx, cy + 3 * u * d), QPointF(cx + 6 * u, cy - 3 * u * d))
        elif k == "close":
            p.drawLine(QPointF(cx - 5 * u, cy - 5 * u), QPointF(cx + 5 * u, cy + 5 * u))
            p.drawLine(QPointF(cx + 5 * u, cy - 5 * u), QPointF(cx - 5 * u, cy + 5 * u))
        elif k == "back":   # вернуться к музыке
            p.drawLine(QPointF(cx + 6 * u, cy), QPointF(cx - 6 * u, cy))
            p.drawLine(QPointF(cx - 6 * u, cy), QPointF(cx - 1 * u, cy - 5 * u))
            p.drawLine(QPointF(cx - 6 * u, cy), QPointF(cx - 1 * u, cy + 5 * u))
        elif k == "novideo":
            p.drawRoundedRect(QRectF(cx - 9 * u, cy - 6 * u, 18 * u, 12 * u), 3 * u, 3 * u)
            p.drawLine(QPointF(cx - 11 * u, cy + 9 * u), QPointF(cx + 11 * u, cy - 9 * u))
        elif k == "eye":
            path = QPainterPath()
            path.moveTo(cx - 10 * u, cy)
            path.quadTo(cx, cy - 10 * u, cx + 10 * u, cy)
            path.quadTo(cx, cy + 10 * u, cx - 10 * u, cy)
            p.drawPath(path)
            p.drawEllipse(QPointF(cx, cy), 2.6 * u, 2.6 * u)


class ThinSlider(QWidget):
    """Тонкий «жидкий» ползунок 0..1."""
    changed = Signal(float)

    def __init__(self):
        super().__init__()
        self.v = 0.0
        self._drag = False
        self.setFixedHeight(22)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)

    def set_value(self, v):
        if not self._drag:
            v = max(0.0, min(1.0, v))
            if abs(v - self.v) > 1e-4:
                self.v = v
                self.update()

    def _set_from(self, x):
        self.v = max(0.0, min(1.0, (x - 7) / max(1, self.width() - 14)))
        self.update()
        self.changed.emit(self.v)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = True
            self._set_from(e.position().x())

    def mouseMoveEvent(self, e):
        if self._drag:
            self._set_from(e.position().x())

    def mouseReleaseEvent(self, e):
        self._drag = False

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cy = h / 2
        x0, x1 = 7, w - 7
        hov = self.underMouse() or self._drag
        th = 5 if hov else 4
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 50))
        p.drawRoundedRect(QRectF(x0, cy - th / 2, x1 - x0, th), th / 2, th / 2)
        xv = x0 + (x1 - x0) * self.v
        p.setBrush(QColor(255, 255, 255, 235))
        p.drawRoundedRect(QRectF(x0, cy - th / 2, max(0, xv - x0), th), th / 2, th / 2)
        if hov:
            p.setBrush(QColor("#ffffff"))
            p.drawEllipse(QPointF(xv, cy), 6, 6)


class Aurora(QWidget):
    """Живой фон, пока клип не загружен: мягкие цветные пятна в цвет акцента."""

    def __init__(self):
        super().__init__()
        self._t = QTimer(self)
        self._t.setInterval(40)
        self._t.timeout.connect(self._step)
        self._t.start()

    def _step(self):
        if self.isVisible():
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        W, H = self.width(), self.height()
        p.fillRect(self.rect(), QColor(5, 7, 11))
        t = time.monotonic()
        a, a2, cy = T.acc(), T.acc2(), QColor(T.CY)
        for i, (c, al, rad) in enumerate(((a, 62, 0.62), (cy, 40, 0.55), (a2, 44, 0.5))):
            x = W * (0.5 + 0.38 * math.sin(t * (0.21 + i * 0.07) + i * 2.1))
            y = H * (0.5 + 0.34 * math.cos(t * (0.17 + i * 0.05) + i * 1.3))
            g = QRadialGradient(QPointF(x, y), max(W, H) * rad)
            cc = QColor(c)
            cc.setAlpha(al)
            g.setColorAt(0, cc)
            cc.setAlpha(0)
            g.setColorAt(1, cc)
            p.fillRect(self.rect(), g)


LIST_QSS = """
QListWidget{background:transparent;border:0;outline:0}
QListWidget::item{padding:4px 6px;border-radius:10px;color:#f4f8fb}
QListWidget::item:hover{background:rgba(255,255,255,22)}
QListWidget::item:selected{background:rgba(255,255,255,34);color:#ffffff}
QLabel{color:#f4f8fb}
"""


class GlassView(QWidget):
    """Полноэкранный вид: клип — фон, интерфейс — стеклянные карточки."""

    def __init__(self, analyzer):
        super().__init__()
        self.setMinimumSize(900, 600)
        self.overlays_on = True
        self.standalone = False
        self.search_open = False
        self.album_open = False
        self.drawer_tab = None          # None | 'hist' | 'clips'

        self.bg = Aurora()
        self.bg.setParent(self)
        self.clip = ClipPlayer(fill=True, transparent=True)
        self.clip.setParent(self)
        self.backdrop = Backdrop(analyzer)
        self.backdrop.setParent(self)
        self.backdrop.hide()

        self._build_album()
        self._build_top()
        self._build_status()
        self._build_drawer()
        self._build_bar(analyzer)
        self._overlay = [self.album_card, self.album_drawer, self.top, self.status, self.drawer, self.bar]
        for w in self._overlay:
            w.raise_()
        self.album_drawer.hide()
        self.drawer.hide()

    # ----------------------------------------------------------------- сборка
    def _build_album(self):
        c = Glass(self, 26, 150)
        lay = QHBoxLayout(c)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(12)
        self.a_cover = Cover(64)
        lay.addWidget(self.a_cover)
        col = QVBoxLayout()
        col.setSpacing(1)
        col.addStretch(1)
        self.a_title = ElideLabel("Альбом", T.ui(15, True), WHITE)
        self.a_sub = ElideLabel("", T.ui(12), SOFT)
        col.addWidget(self.a_title)
        col.addWidget(self.a_sub)
        col.addStretch(1)
        lay.addLayout(col, 1)
        self.b_album = GlassIcon("chev_d", 32, tip="Треклист альбома")
        self.b_album.clicked.connect(self.toggle_album)
        lay.addWidget(self.b_album)
        self.album_card = c

        d = Glass(self, 24, 175)
        dl = QVBoxLayout(d)
        dl.setContentsMargins(10, 10, 10, 12)
        d.setStyleSheet(LIST_QSS)
        self.tracks = QListWidget()
        self.tracks.setItemDelegate(TrackDelegate(self.tracks))
        self.tracks.setMouseTracking(True)
        dl.addWidget(self.tracks)
        self.album_drawer = d

    def _build_top(self):
        t = Glass(self, 26, 150)
        lay = QHBoxLayout(t)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Найти клип…")
        self.search.setFixedWidth(240)
        self.search.setStyleSheet(
            "QLineEdit{background:rgba(255,255,255,20);border:1px solid rgba(255,255,255,50);"
            "border-radius:18px;padding:6px 14px;color:#f4f8fb;font-size:13px;}"
            "QLineEdit:focus{border-color:rgba(255,255,255,140);}")
        self.search.hide()
        lay.addWidget(self.search)
        self.b_search = GlassIcon("search", 38, tip="Найти клип (/)")
        self.b_hist = GlassIcon("clock", 38, tip="История альбомов")
        self.b_clips = GlassIcon("list", 38, tip="Другие клипы")
        self.b_eye = GlassIcon("eye", 38, tip="Скрыть интерфейс (C)")
        self.b_noclip = GlassIcon("novideo", 38, tip="Режим без клипа — для слабого интернета (N)")
        self.b_noclip.setCheckable(True)
        self.b_own = GlassIcon("disc", 38, tip="Играть клип со звуком (свой плеер)")
        self.b_swap = GlassIcon("swap", 38, tip="Классический дизайн (D)")
        self.b_pin = GlassIcon("pin", 38, tip="Поверх всех окон (P)")
        self.b_full = GlassIcon("full", 38, tip="Во весь экран (F)")
        for b in (self.b_hist, self.b_clips):
            b.setCheckable(True)
        self.b_pin.setCheckable(True)
        self.b_search.clicked.connect(self.toggle_search)
        self.b_hist.clicked.connect(lambda: self.show_drawer("hist"))
        self.b_clips.clicked.connect(lambda: self.show_drawer("clips"))
        self.b_eye.clicked.connect(lambda: self.set_overlays(False))
        for b in (self.b_search, self.b_own, self.b_noclip, self.b_hist, self.b_clips, self.b_eye, self.b_swap, self.b_pin, self.b_full):
            lay.addWidget(b)
        self.top = t

    def _build_status(self):
        s = Glass(self, 24, 150)
        lay = QHBoxLayout(s)
        lay.setContentsMargins(16, 5, 8, 5)
        lay.setSpacing(6)
        self.st_text = ElideLabel("Нет медиа-сессии", T.ui(12, True), WHITE)
        lay.addWidget(self.st_text, 1)
        self.st_drift = QLabel("")
        self.st_drift.setFont(T.ui(12, True))
        self.st_drift.setStyleSheet(f"color:{SOFT}")
        lay.addWidget(self.st_drift)
        self.b_sync = GlassIcon("sync", 30, tip="Синхронизировать клип с музыкой")
        self.b_offm = GlassIcon("minus", 30, tip="Сдвиг клипа −0.5 с")
        self.l_off = QLabel("+0.0с")
        self.l_off.setFont(T.ui(12, True))
        self.l_off.setStyleSheet(f"color:{SOFT}")
        self.b_offp = GlassIcon("plus", 30, tip="Сдвиг клипа +0.5 с")
        self.b_ext = GlassIcon("ext", 30, tip="Открыть клип в браузере")
        for w in (self.b_sync, self.b_offm, self.l_off, self.b_offp, self.b_ext):
            lay.addWidget(w)
        self.b_back = GlassIcon("back", 30, tip="Вернуться к музыке")
        self.b_back.hide()
        lay.addWidget(self.b_back)
        self.status = s

    def _build_drawer(self):
        d = Glass(self, 24, 175)
        d.setStyleSheet(LIST_QSS)
        lay = QVBoxLayout(d)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)
        self.dr_title = QLabel("")
        self.dr_title.setFont(T.ui(13, True))
        lay.addWidget(self.dr_title)
        self.shelf = QListWidget()
        self.shelf.setViewMode(QListView.IconMode)
        self.shelf.setIconSize(QSize(84, 84))
        self.shelf.setResizeMode(QListView.Adjust)
        self.shelf.setMovement(QListView.Static)
        self.shelf.setWrapping(True)
        self.shelf.setSpacing(4)
        self.shelf.setGridSize(QSize(100, 120))
        self.shelf.setTextElideMode(Qt.ElideRight)
        self.shelf.setFont(T.ui(11))
        self.results = QListWidget()
        self.results.setIconSize(QSize(80, 45))
        self.results.setSpacing(2)
        lay.addWidget(self.shelf, 1)
        lay.addWidget(self.results, 1)
        self.drawer = d

    def _build_bar(self, analyzer):
        b = Glass(self, 30, 160)
        lay = QHBoxLayout(b)
        lay.setContentsMargins(22, 14, 22, 14)
        lay.setSpacing(22)
        # --- слева: информация о треке
        left = QVBoxLayout()
        left.setSpacing(2)
        self.title = ElideLabel("—", T.ui(24, True), WHITE)
        self.sub = ElideLabel("", T.ui(13), SOFT)
        left.addWidget(self.title)
        left.addWidget(self.sub)
        left.addSpacing(6)
        pills = QHBoxLayout()
        pills.setSpacing(6)
        self.p_state = Pill("PAUSE")
        self.p_src = Pill("—")
        self.p_dur = Pill("--:--")
        self.p_viz = Pill("SIM")
        for w in (self.p_state, self.p_src, self.p_dur, self.p_viz):
            pills.addWidget(w)
        pills.addStretch(1)
        left.addLayout(pills)
        self.clip_line = ElideLabel("", T.ui(11.5), SOFT)
        left.addWidget(self.clip_line)
        lay.addLayout(left, 5)
        # --- центр: транспорт и прогресс
        mid = QVBoxLayout()
        mid.setSpacing(4)
        tr = QHBoxLayout()
        tr.setSpacing(10)
        tr.addStretch(1)
        self.b_prev = GlassIcon("prev", 40, tip="Предыдущий")
        self.b_play = GlassIcon("play", 54, primary=True, tip="Плей / пауза")
        self.b_next = GlassIcon("next", 40, tip="Следующий")
        for w in (self.b_prev, self.b_play, self.b_next):
            tr.addWidget(w)
        tr.addStretch(1)
        mid.addLayout(tr)
        pr = QHBoxLayout()
        pr.setSpacing(8)
        self.t_cur = QLabel("0:00")
        self.t_end = QLabel("--:--")
        for t in (self.t_cur, self.t_end):
            t.setFont(T.ui(12, True))
            t.setStyleSheet(f"color:{SOFT}")
            t.setMinimumWidth(40)
        self.t_end.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.prog = ThinSlider()
        pr.addWidget(self.t_cur)
        pr.addWidget(self.prog, 1)
        pr.addWidget(self.t_end)
        mid.addLayout(pr)
        lay.addLayout(mid, 6)
        # --- справа: громкость системы, громкость клипа, мини-визуализатор
        right = QVBoxLayout()
        right.setSpacing(5)
        vr = QHBoxLayout()
        vr.setSpacing(8)
        self.b_mute = GlassIcon("vol", 30, tip="Звук (M)")
        self.vol = ThinSlider()
        vr.addWidget(self.b_mute)
        vr.addWidget(self.vol, 1)
        right.addLayout(vr)
        cr = QHBoxLayout()
        cr.setSpacing(8)
        self.b_cmute = GlassIcon("mute", 30, tip="Включить звук клипа")
        self.cvol = ThinSlider()
        self.cvol.setToolTip("Громкость клипа")
        lab = QLabel("КЛИП")
        lab.setFont(T.ui(10, True))
        lab.setStyleSheet(f"color:{SOFT}")
        cr.addWidget(self.b_cmute)
        cr.addWidget(self.cvol, 1)
        cr.addWidget(lab)
        right.addLayout(cr)
        self.viz = VizWidget(analyzer, compact=True)
        self.viz.setFixedHeight(30)
        right.addWidget(self.viz)
        lay.addLayout(right, 4)
        self.bar = b

    # ----------------------------------------------------------------- геометрия
    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._relayout()

    def _relayout(self):
        W, H = self.width(), self.height()
        m = 20
        self.bg.setGeometry(0, 0, W, H)
        self.clip.setGeometry(0, 0, W, H)
        self.backdrop.setGeometry(0, 0, W, H)
        self.album_card.setGeometry(m, m, 300, 90)
        top_h = max(120, H - m - 90 - 8 - 162 - m)
        self.album_drawer.setGeometry(m, m + 98, 300, min(420, top_h))
        tw = self.top.layout().sizeHint().width()
        self.top.setGeometry(W - m - tw, m + 6, tw, 52)
        dh = max(160, min(560, H - (m + 66) - 162 - m - 6))
        self.drawer.setGeometry(W - m - 360, m + 66, 360, dh)
        space = W - 2 * (m + max(300, tw)) - 20
        sw = max(0, min(640, space))
        self.status.setGeometry((W - sw) // 2, m + 6, sw, 46)
        self.status.setVisible(sw >= 400 and self.overlays_on)
        bw = min(W - 2 * m, 1240)
        self.bar.setGeometry((W - bw) // 2, H - m - 140, bw, 140)

    # ----------------------------------------------------------------- состояния интерфейса
    def set_overlays(self, on: bool):
        self.overlays_on = on
        for w in (self.album_card, self.top, self.bar):
            w.setVisible(on)
        self.album_drawer.setVisible(on and self.album_open)
        self.drawer.setVisible(on and self.drawer_tab is not None)
        self.status.setVisible(on)
        if not on:
            self._peek = QLabel("Нажми C, чтобы вернуть интерфейс", self)
            self._peek.setStyleSheet("color:rgba(255,255,255,170);background:rgba(8,11,16,120);"
                                     "border-radius:12px;padding:6px 12px;font-size:12px")
            self._peek.adjustSize()
            self._peek.move(self.width() - self._peek.width() - 20, 20)
            self._peek.show()
            QTimer.singleShot(2200, self._peek.deleteLater)
        else:
            self._relayout()

    def toggle_overlays(self):
        self.set_overlays(not self.overlays_on)

    def toggle_search(self):
        self.search_open = not self.search_open
        self.search.setVisible(self.search_open)
        self._relayout()
        if self.search_open:
            self.search.setFocus()
            self.search.selectAll()

    def open_search(self):
        if not self.search_open:
            self.toggle_search()
        else:
            self.search.setFocus()
            self.search.selectAll()

    def toggle_album(self):
        self.album_open = not self.album_open
        self.album_drawer.setVisible(self.album_open and self.overlays_on)
        self.b_album.set_kind("chev_u" if self.album_open else "chev_d")

    def show_drawer(self, tab):
        self.drawer_tab = None if self.drawer_tab == tab else tab
        self.b_hist.setChecked(self.drawer_tab == "hist")
        self.b_clips.setChecked(self.drawer_tab == "clips")
        self.shelf.setVisible(self.drawer_tab == "hist")
        self.results.setVisible(self.drawer_tab == "clips")
        self.dr_title.setText({"hist": "История альбомов", "clips": "Другие клипы", None: ""}[self.drawer_tab])
        self.drawer.setVisible(self.drawer_tab is not None and self.overlays_on)
        self.drawer.raise_()

    # ----------------------------------------------------------------- данные из главного окна
    def set_track(self, title, sub, app, dur_txt):
        self.title.setText(title or "—")
        self.sub.setText(sub)
        self.p_src.set_text(app or "—")
        self.p_dur.set_text(dur_txt)

    def set_playing(self, playing):
        self.p_state.set_text("PLAY" if playing else "PAUSE", playing)
        self.b_play.set_kind("pause" if playing else "play")

    def set_cover(self, pm):
        self.a_cover.set_pixmap(pm)

    def set_album(self, title, sub):
        self.a_title.setText(title or "Альбом")
        self.a_sub.setText(sub or "")

    def set_progress(self, pos, dur):
        self.t_cur.setText(fmt(pos))
        self.t_end.setText(fmt(dur) if dur > 0 else "--:--")
        self.prog.set_value(pos / dur if dur > 0 else 0.0)

    def set_volume01(self, v, muted):
        self.vol.set_value(0.0 if muted else v)
        self.b_mute.set_kind("mute" if muted else "vol")

    def set_status(self, text):
        self.st_text.setText(text)

    def set_standalone(self, on):
        self.standalone = on
        self.b_back.setVisible(on)
        self.p_viz.set_text("СВОЙ ЗВУК" if on else self.p_viz.text_, on)

    def set_missing(self, missing: bool):
        self.backdrop.setVisible(missing)
        for w in self._overlay:
            w.raise_()

    def set_clip_volume(self, v01, audio_on):
        self.cvol.set_value(v01 if audio_on else 0.0)
        self.b_cmute.set_kind("vol" if audio_on and v01 > 0 else "mute")
