"""Главное окно Media Panel."""
import hashlib
import os
import sys
import time
from urllib.parse import quote

os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--autoplay-policy=no-user-gesture-required")

from . import clip as clipmod  # noqa: E402  (QtWebEngine — до QApplication)
from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, QTimer, QUrl  # noqa: E402
from PySide6.QtGui import (QColor, QDesktopServices, QIcon, QImage, QPainter,  # noqa: E402
                           QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import (QApplication, QComboBox, QHBoxLayout, QLabel,  # noqa: E402
                               QLineEdit, QListView, QListWidget, QListWidgetItem,
                               QScrollArea, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget,
                               QGridLayout)

from . import catalog, core, theme as T  # noqa: E402
from .audio import Analyzer  # noqa: E402
from .core import Settings, bg, data_dir, http_get  # noqa: E402
from .media import DemoMedia, MediaState, WinMedia  # noqa: E402
from .sysvol import SysVolume  # noqa: E402
from .widgets import (AspectBox, Chip, Cover, Dot, ElideLabel, IconButton, KeyHint,  # noqa: E402
                      Panel, SegMeter, SettingRow, Switch, TagButton, VizWidget)

PROG_SEGS = 60


def fmt(sec: float) -> str:
    sec = int(max(0, sec))
    h, m, s = sec // 3600, (sec // 60) % 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def dominant_color(pm: QPixmap):
    """Самый «цветной» оттенок обложки; для серых обложек — None."""
    img = pm.toImage().scaled(24, 24, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    r = g = b = wsum = 0.0
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            h, s, v, _ = c.getHsvF()
            w = (s ** 2) * v
            r += c.redF() * w
            g += c.greenF() * w
            b += c.blueF() * w
            wsum += w
    if wsum < 1.5:
        return None
    return QColor.fromRgbF(r / wsum, g / wsum, b / wsum)


def make_icon() -> QIcon:
    pm = QPixmap(128, 128)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(T.BG))
    p.setPen(QPen(QColor(T.LINE2), 2))
    p.drawRoundedRect(QRectF(4, 4, 120, 120), 24, 24)
    a = QColor(T.DEFAULT_ACC)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(a, 8))
    p.drawEllipse(QPointF(64, 64), 34, 34)
    p.setBrush(QColor(T.CY))
    p.setPen(Qt.NoPen)
    p.drawEllipse(QPointF(64, 64), 9, 9)
    p.end()
    return QIcon(pm)


class TrackDelegate(QStyledItemDelegate):
    def paint(self, p, opt, idx):
        d = idx.data(Qt.UserRole) or {}
        r = opt.rect
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        cur = bool(d.get("current"))
        hov = bool(opt.state & QStyle.State_MouseOver)
        rr = QRectF(r).adjusted(1, 1, -1, -1)
        if cur:
            c = T.acc()
            c.setAlpha(30)
            p.setBrush(c)
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(rr, 3, 3)
        elif hov:
            p.setBrush(QColor(T.PANEL2))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(rr, 3, 3)
        p.setFont(T.mono(11, True))
        fm = p.fontMetrics()
        y = r.top() + (r.height() + fm.ascent() - fm.descent()) // 2
        p.setPen(T.acc() if cur else QColor(T.MUTED))
        p.drawText(r.left() + 8, y, "▶" if cur else f"{int(d.get('n', 0)):02d}")
        dur = fmt(d.get("dur", 0)) if d.get("dur") else ""
        dw = fm.horizontalAdvance(dur)
        p.drawText(r.right() - dw - 8, y, dur)
        p.setFont(T.ui(13, cur))
        p.setPen(T.acc2() if cur else QColor(T.TEXT))
        fm2 = p.fontMetrics()
        tx = fm2.elidedText(d.get("title", ""), Qt.ElideRight, r.width() - 40 - dw - 24)
        y2 = r.top() + (r.height() + fm2.ascent() - fm2.descent()) // 2
        p.drawText(r.left() + 36, y2, tx)
        p.restore()

    def sizeHint(self, opt, idx):
        return QSize(0, 28)


class Toast(QLabel):
    def __init__(self, parent):
        super().__init__(parent)
        self.setFont(T.mono(12, True))
        self.hide()
        self._t = QTimer(self)
        self._t.setSingleShot(True)
        self._t.timeout.connect(self.hide)

    def show_text(self, text):
        self.setStyleSheet(f"background:{T.PANEL2};border:1px solid {T.acc().name()};color:{T.TEXT};"
                           f"padding:8px 14px;border-radius:4px;")
        self.setText(text)
        self.adjustSize()
        p = self.parentWidget()
        self.move((p.width() - self.width()) // 2, p.height() - self.height() - 46)
        self.show()
        self.raise_()
        self._t.start(1800)


class MainWindow(QWidget):
    def __init__(self, demo=False):
        super().__init__()
        self.setWindowTitle("Media Panel")
        self.setWindowIcon(make_icon())
        self.resize(1400, 920)
        self.setMinimumSize(1020, 700)
        self.cfg = Settings()
        self.demo = demo
        self.state = MediaState()
        self.track_key = None
        self.last_playing = None
        self.catalog = None
        self.cover_pm = None
        self.history = list(self.cfg.get("history") or [])
        self.clip_items: list = []
        self.clip_idx = -1
        self.clip_req = 0
        self.clip_fail = 0
        self.clip_time = 0.0
        self.offset = float(self.cfg.get("clip_offset") or 0.0)
        self.album_req = 0
        self._bg_cache = None
        self._dark_done = False
        self._pending_vol = None

        # --- источники
        self.sysvol = SysVolume()
        self.an = Analyzer()
        if not demo:
            self.an.start()
        self.media = (DemoMedia if demo else WinMedia)(self.on_state, self.on_thumb)

        self._build()
        self._apply_settings()
        self.toast = Toast(self)

        self.media.start()
        QApplication.instance().installEventFilter(self)

        self.t_prog = QTimer(self)
        self.t_prog.timeout.connect(self._tick_progress)
        self.t_prog.start(200)
        self.t_vol = QTimer(self)
        self.t_vol.timeout.connect(self._poll_volume)
        self.t_vol.start(700)
        QTimer.singleShot(2800, self._check_backend)
        self._rebuild_shelf()

    # ============================================================== построение интерфейса
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 12)
        root.setSpacing(12)
        root.addWidget(self._build_header())
        grid = QGridLayout()
        grid.setSpacing(12)
        self.play_panel = self._build_play()
        self.clip_panel = self._build_clip()
        self.alb_panel = self._build_albums()
        self.set_panel = self._build_settings()
        grid.addWidget(self.play_panel, 0, 0)
        grid.addWidget(self.clip_panel, 0, 1)
        grid.addWidget(self.alb_panel, 1, 0)
        grid.addWidget(self.set_panel, 1, 1)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 2)
        grid.setRowStretch(0, 6)
        grid.setRowStretch(1, 3)
        root.addLayout(grid, 1)
        foot = QHBoxLayout()
        foot.setSpacing(18)
        for keys, txt in ((["Space"], "плей/пауза"), (["←", "→"], "трек"), (["↑", "↓"], "громкость"),
                          (["M"], "звук"), (["V"], "визуал"), (["C"], "клип"), (["/"], "поиск"),
                          (["F"], "весь экран"), (["P"], "поверх окон")):
            foot.addWidget(KeyHint(keys, txt))
        foot.addStretch(1)
        root.addLayout(foot)

    def _build_header(self):
        pn = Panel(None, margins=(18, 12, 18, 12))
        row = QHBoxLayout()
        row.setSpacing(24)
        # громкость крупно
        left = QVBoxLayout()
        left.setSpacing(6)
        big = QHBoxLayout()
        big.setSpacing(2)
        self.h_vol = QLabel("--")
        self.h_vol.setFont(T.mono(40, True))
        pct = QLabel("%")
        pct.setFont(T.mono(16))
        pct.setStyleSheet(f"color:{T.MUTED}")
        big.addWidget(self.h_vol)
        big.addWidget(pct, 0, Qt.AlignBottom)
        big.addStretch(1)
        left.addLayout(big)
        self.h_cells = SegMeter(0, 10, 0, color="ok", floor=0, seg_h=8, interactive=False)
        self.h_cells.setFixedWidth(170)
        left.addWidget(self.h_cells)
        row.addLayout(left)
        # название
        mid = QVBoxLayout()
        mid.setSpacing(4)
        name = QLabel("MEDIA PANEL")
        name.setFont(T.mono(18, True, 0.4))
        self.h_meta = QLabel()
        self.h_meta.setTextFormat(Qt.RichText)
        self.h_meta.setFont(T.mono(12))
        self.h_meta.setStyleSheet(f"color:{T.MUTED}")
        link = QHBoxLayout()
        link.setSpacing(8)
        self.dot = Dot()
        self.h_state = QLabel("НЕТ СЕССИИ")
        self.h_state.setFont(T.mono(11, True, 1.2))
        self.h_state.setStyleSheet(f"color:{T.MUTED}")
        link.addWidget(self.dot)
        link.addWidget(self.h_state)
        link.addStretch(1)
        mid.addWidget(name)
        mid.addWidget(self.h_meta)
        mid.addLayout(link)
        row.addLayout(mid, 1)
        # кнопки
        self.b_pin = IconButton("pin", 38, tip="Поверх всех окон (P)")
        self.b_pin.setCheckable(True)
        self.b_clipvis = IconButton("clip", 38, tip="Показать / скрыть клип (C)")
        self.b_clipvis.setCheckable(True)
        self.b_full = IconButton("full", 38, tip="Во весь экран (F)")
        self.b_pin.clicked.connect(lambda: self._set_on_top(self.b_pin.isChecked()))
        self.b_clipvis.clicked.connect(lambda: self._set_clip_visible(self.b_clipvis.isChecked()))
        self.b_full.clicked.connect(self._toggle_full)
        for b in (self.b_pin, self.b_clipvis, self.b_full):
            row.addWidget(b, 0, Qt.AlignVCenter)
        pn.lay.addLayout(row)
        self._update_meta()
        return pn

    def _build_play(self):
        pn = Panel("01", "Воспроизведение")
        np_row = QHBoxLayout()
        np_row.setSpacing(18)
        self.cover = Cover(150)
        np_row.addWidget(self.cover, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.l_title = ElideLabel("—", T.ui(26, True))
        self.l_sub = ElideLabel("", T.ui(14), T.MUTED)
        col.addWidget(self.l_title)
        col.addWidget(self.l_sub)
        col.addSpacing(10)
        chips = QHBoxLayout()
        chips.setSpacing(6)
        self.c_state = Chip("STATE", "PAUSE")
        self.c_src = Chip("SRC", "—")
        self.c_dur = Chip("DUR", "--:--")
        self.c_lvl = Chip("LVL", "-∞ dB")
        self.c_viz = Chip("VIZ", "SIM")
        for c in (self.c_state, self.c_src, self.c_dur, self.c_lvl, self.c_viz):
            chips.addWidget(c)
        chips.addStretch(1)
        col.addLayout(chips)
        col.addStretch(1)
        np_row.addLayout(col, 1)
        pn.lay.addLayout(np_row)

        self.viz = VizWidget(self.an)
        pn.lay.addWidget(self.viz, 1)

        pr = QHBoxLayout()
        pr.setSpacing(12)
        self.t_cur = QLabel("0:00")
        self.t_end = QLabel("--:--")
        for t in (self.t_cur, self.t_end):
            t.setFont(T.mono(12, True))
            t.setStyleSheet(f"color:{T.MUTED}")
            t.setMinimumWidth(46)
        self.t_end.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.prog = SegMeter(0, PROG_SEGS - 1, 0, color="cy", seg_h=8)
        self.prog.changed.connect(self._seek_frac)
        pr.addWidget(self.t_cur)
        pr.addWidget(self.prog, 1)
        pr.addWidget(self.t_end)
        pn.lay.addLayout(pr)

        ctl = QHBoxLayout()
        ctl.setSpacing(18)
        tr = QHBoxLayout()
        tr.setSpacing(6)
        self.b_prev = IconButton("prev", 40, tip="Предыдущий трек")
        self.b_play = IconButton("play", 54, primary=True, tip="Плей / пауза")
        self.b_next = IconButton("next", 40, tip="Следующий трек")
        self.b_prev.clicked.connect(lambda: self.media.cmd("prev"))
        self.b_next.clicked.connect(lambda: self.media.cmd("next"))
        self.b_play.clicked.connect(lambda: self.media.cmd("toggle"))
        tr.addWidget(self.b_prev)
        tr.addWidget(self.b_play)
        tr.addWidget(self.b_next)
        ctl.addLayout(tr)
        vb = QVBoxLayout()
        vb.setSpacing(5)
        lr = QHBoxLayout()
        lbl = QLabel("ГРОМКОСТЬ")
        lbl.setFont(T.mono(10.5, True, 1.2))
        lbl.setStyleSheet(f"color:{T.MUTED}")
        self.v_val = QLabel("--")
        self.v_val.setFont(T.mono(15, True))
        lr.addWidget(lbl)
        lr.addStretch(1)
        lr.addWidget(self.v_val)
        vb.addLayout(lr)
        self.vol = SegMeter(0, 30, 0, floor=0)
        self.vol.changed.connect(self._user_volume)
        vb.addWidget(self.vol)
        ctl.addLayout(vb, 1)
        self.b_mute = IconButton("vol", 40, tip="Выключить звук (M)")
        self.b_mute.clicked.connect(self._toggle_mute)
        ctl.addWidget(self.b_mute)
        pn.lay.addLayout(ctl)
        if not self.sysvol.ok:
            self.vol.setEnabled(False)
            self.b_mute.setEnabled(False)
            self.vol.setToolTip("Системная громкость недоступна")
        return pn

    def _build_clip(self):
        pn = Panel("02", "Клип")
        self.t_autoclip = TagButton("AUTO")
        self.t_autoclip.setToolTip("Автоматически искать клип при смене трека")
        self.t_autoclip.toggled.connect(lambda v: self.cfg.set("auto_clip", bool(v)))
        pn.head.addWidget(self.t_autoclip)
        self.clip = clipmod.ClipPlayer()
        self.clip.ready.connect(self._clip_ready)
        self.clip.failed.connect(self._clip_failed)
        self.clip.tick.connect(self._clip_tick)
        pn.lay.addWidget(AspectBox(self.clip, 240))

        row = QHBoxLayout()
        row.setSpacing(5)
        self.clip_status = ElideLabel("Клип идёт без звука параллельно с музыкой", T.mono(11), T.MUTED)
        row.addWidget(self.clip_status, 1)
        self.l_drift = QLabel("")
        self.l_drift.setFont(T.mono(11, True))
        self.l_drift.setStyleSheet(f"color:{T.MUTED}")
        row.addWidget(self.l_drift)
        self.b_offm = IconButton("minus", 28, tip="Сдвиг клипа −0.5 с")
        self.l_off = QLabel()
        self.l_off.setFont(T.mono(11, True))
        self.l_off.setMinimumWidth(48)
        self.l_off.setAlignment(Qt.AlignCenter)
        self.b_offp = IconButton("plus", 28, tip="Сдвиг клипа +0.5 с")
        self.b_sync = IconButton("sync", 28, tip="Синхронизировать клип с музыкой")
        self.b_cprev = IconButton("prev", 28, tip="Предыдущий вариант клипа")
        self.b_cnext = IconButton("next", 28, tip="Следующий вариант клипа")
        self.b_ext = IconButton("ext", 28, tip="Открыть в браузере")
        self.b_offm.clicked.connect(lambda: self._shift(-0.5))
        self.b_offp.clicked.connect(lambda: self._shift(0.5))
        self.b_sync.clicked.connect(self._sync_clip)
        self.b_cprev.clicked.connect(lambda: self._clip_step(-1))
        self.b_cnext.clicked.connect(lambda: self._clip_step(1))
        self.b_ext.clicked.connect(self._open_ext)
        for w in (self.b_offm, self.l_off, self.b_offp, self.b_sync, self.b_cprev, self.b_cnext, self.b_ext):
            row.addWidget(w)
        pn.lay.addLayout(row)
        self._update_off()

        sr = QHBoxLayout()
        sr.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Найти клип: исполнитель — название")
        self.search.returnPressed.connect(self._manual_search)
        self.b_search = IconButton("search", 34, tip="Найти")
        self.b_search.clicked.connect(self._manual_search)
        sr.addWidget(self.search, 1)
        sr.addWidget(self.b_search)
        pn.lay.addLayout(sr)

        self.results = QListWidget()
        self.results.setIconSize(QSize(80, 45))
        self.results.setSpacing(2)
        self.results.setMinimumHeight(110)
        self.results.itemClicked.connect(lambda it: self._play_clip(self.results.row(it)))
        pn.lay.addWidget(self.results, 1)
        return pn

    def _build_albums(self):
        pn = Panel("03", "Альбомы")
        row = QHBoxLayout()
        row.setSpacing(14)
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
        self.shelf.itemClicked.connect(self._shelf_clicked)
        row.addWidget(self.shelf, 5)
        right = QVBoxLayout()
        right.setSpacing(2)
        self.a_title = ElideLabel("Выбери альбом из истории", T.ui(15, True))
        self.a_sub = ElideLabel("", T.ui(12), T.MUTED)
        right.addWidget(self.a_title)
        right.addWidget(self.a_sub)
        right.addSpacing(4)
        self.tracks = QListWidget()
        self.tracks.setItemDelegate(TrackDelegate(self.tracks))
        self.tracks.setMouseTracking(True)
        self.tracks.itemClicked.connect(self._track_clicked)
        right.addWidget(self.tracks, 1)
        row.addLayout(right, 6)
        pn.lay.addLayout(row, 1)
        return pn

    def _build_settings(self):
        pn = Panel("04", "Визуализатор и функции")
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget()
        inner.setObjectName("inner")
        inner.setStyleSheet("#inner{background:transparent}")
        sa.viewport().setStyleSheet("background:transparent")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 6, 0)
        lay.setSpacing(0)
        self.s_mode = QComboBox()
        for m in VizWidget.MODES:
            self.s_mode.addItem(VizWidget.MODE_NAMES[m], m)
        self.s_mode.currentIndexChanged.connect(self._viz_mode_changed)
        self.s_sens = SegMeter(1, 10, self.cfg.get("sens"), seg_h=12)
        self.s_sens.setFixedWidth(150)
        self.s_sens.changed.connect(self._sens_changed)
        self.s_peaks = Switch(self.cfg.get("peaks"))
        self.s_peaks.toggled.connect(lambda v: (self.cfg.set("peaks", v), setattr(self.viz, "peaks", v)))
        self.s_accent = Switch(self.cfg.get("auto_accent"))
        self.s_accent.toggled.connect(self._accent_toggled)
        self.s_follow = Switch(self.cfg.get("clip_follow"))
        self.s_follow.toggled.connect(self._follow_toggled)
        self.s_top = Switch(self.cfg.get("on_top"))
        self.s_top.toggled.connect(self._set_on_top)
        rows = [
            ("Режим визуализации", "Столбцы, зеркало, круг или осциллограф (V)", self.s_mode),
            ("Чувствительность", "Высота столбцов и размах волны", self.s_sens),
            ("Пики на столбцах", "Задерживающиеся «колпачки»", self.s_peaks),
            ("Цвет из обложки", "Акцент интерфейса подстраивается под альбом", self.s_accent),
            ("Клип следует за паузой", "Пауза и воспроизведение клипа вместе с музыкой", self.s_follow),
            ("Поверх всех окон", "Панель остаётся над остальными окнами (P)", self.s_top),
        ]
        for i, (t, h, c) in enumerate(rows):
            lay.addWidget(SettingRow(t, h, c, first=(i == 0)))
        self.s_info = QLabel()
        self.s_info.setWordWrap(True)
        self.s_info.setFont(T.mono(11))
        self.s_info.setStyleSheet(f"color:{T.MUTED};padding-top:12px")
        lay.addWidget(self.s_info)
        lay.addStretch(1)
        sa.setWidget(inner)
        pn.lay.addWidget(sa, 1)
        return pn

    # ============================================================== настройки
    def _apply_settings(self):
        mode = self.cfg.get("viz_mode")
        i = max(0, self.s_mode.findData(mode))
        self.s_mode.blockSignals(True)
        self.s_mode.setCurrentIndex(i)
        self.s_mode.blockSignals(False)
        self.viz.set_mode(self.s_mode.currentData())
        self.viz.peaks = bool(self.cfg.get("peaks"))
        self._sens_changed(self.cfg.get("sens"), save=False)
        self.t_autoclip.setChecked(bool(self.cfg.get("auto_clip")))
        self.b_clipvis.setChecked(bool(self.cfg.get("clip_visible")))
        self.clip_panel.setVisible(bool(self.cfg.get("clip_visible")))
        on_top = bool(self.cfg.get("on_top"))
        self.b_pin.setChecked(on_top)
        if on_top:
            self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self._update_info()

    def _viz_mode_changed(self, _):
        m = self.s_mode.currentData()
        self.viz.set_mode(m)
        self.cfg.set("viz_mode", m)

    def _cycle_viz(self):
        i = (self.s_mode.currentIndex() + 1) % self.s_mode.count()
        self.s_mode.setCurrentIndex(i)
        self.toast.show_text("Визуализация: " + self.s_mode.currentText())

    def _sens_changed(self, v, save=True):
        self.viz.sens = 0.5 + (int(v) - 1) / 9 * 1.5
        if save:
            self.cfg.set("sens", int(v))

    def _accent_toggled(self, v):
        self.cfg.set("auto_accent", bool(v))
        self._refresh_accent()

    def _follow_toggled(self, v):
        self.cfg.set("clip_follow", bool(v))
        self._apply_clip_play_state()

    def _set_on_top(self, on):
        on = bool(on)
        self.cfg.set("on_top", on)
        self.b_pin.setChecked(on)
        self.s_top.blockSignals(True)
        self.s_top.setChecked(on)
        self.s_top.blockSignals(False)
        vis = self.isVisible()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, on)
        if vis:
            self.show()
            self._dark_done = False
            self._dark_titlebar()

    def _set_clip_visible(self, v):
        v = bool(v)
        self.cfg.set("clip_visible", v)
        self.b_clipvis.setChecked(v)
        self.clip_panel.setVisible(v)

    def _toggle_full(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _update_info(self):
        if self.demo:
            src = "ДЕМО-РЕЖИМ: вымышленный плеер и имитация спектра"
        elif self.an.active:
            src = f"Спектр: {self.an.backend} · {self.an.device_name}"
        else:
            src = "Спектр: имитация (захват звука недоступен)"
        vol = "Громкость: системная" if self.sysvol.ok else "Громкость: недоступна"
        self.s_info.setText(f"{src}\n{vol}")
        self.c_viz.set_value("LIVE" if self.an.active else "SIM", T.OK if self.an.active else T.CY)

    def _check_backend(self):
        err = getattr(self.media, "error", None)
        if err:
            self.h_state.setText("SMTC НЕДОСТУПЕН")
            self.dot.state = "bad"
            self.toast.show_text("Нет доступа к медиа-сессии Windows: " + err[:60])
        self._update_info()

    def _update_meta(self):
        app = self.state.app or "—"
        mode = "LIVE" if self.an.active else "SIM"
        self.h_meta.setText(
            f"SRC <span style='color:{T.TEXT}'>{app}</span> &nbsp; "
            f"VIZ <span style='color:{T.TEXT}'>{mode}</span> &nbsp; "
            f"CLIP <span style='color:{T.TEXT}'>{'YT' if clipmod.WEBENGINE_OK else '—'}</span>")

    # ============================================================== медиа-события
    def on_state(self, st: MediaState):
        self.state = st
        if not st.has_session or not st.title:
            self._no_session(st)
            return
        if st.key != self.track_key:
            self._on_track(st)
        if st.playing != self.last_playing:
            self.last_playing = st.playing
            self._on_play_changed(st.playing)
        self.c_src.set_value(st.app or "—")
        if st.dur > 0:
            self.c_dur.set_value(fmt(st.dur))
        self.dot.state = "ok"
        self.h_state.setText("СЕССИЯ АКТИВНА")
        self._update_meta()

    def _no_session(self, st):
        if self.track_key is not None:
            self.track_key = None
            self.l_title.setText("—")
            self.l_sub.setText("")
            self.cover.set_pixmap(None)
            self.cover_pm = None
            self.setWindowTitle("Media Panel")
        self.last_playing = False
        self.viz.playing = False
        self.c_state.set_value("PAUSE", T.CY)
        self.b_play.set_kind("play")
        self.dot.state = "bad" if getattr(self.media, "error", None) else "dim"
        self.h_state.setText("НЕТ МЕДИА-СЕССИИ — включи музыку в любом плеере")
        self.c_src.set_value("—")
        self.c_dur.set_value("--:--")
        self._update_meta()

    def _on_play_changed(self, playing: bool):
        self.viz.playing = playing
        self.c_state.set_value("PLAY" if playing else "PAUSE", T.OK if playing else T.CY)
        self.b_play.set_kind("pause" if playing else "play")
        self._apply_clip_play_state()

    def _on_track(self, st: MediaState):
        self.track_key = st.key
        self.catalog = None
        self.l_title.setText(st.title or "—")
        self.l_sub.setText(" · ".join(x for x in (st.artist, st.album) if x))
        self.cover.set_pixmap(None)
        self.cover_pm = None
        self.c_dur.set_value(fmt(st.dur) if st.dur > 0 else "--:--")
        self.setWindowTitle(f"{st.artist} — {st.title} · Media Panel" if st.artist else f"{st.title} · Media Panel")
        key = st.key
        a, t, al = st.artist, st.title, st.album

        def work():
            res = catalog.deezer_find(a, t)
            if not res and al:
                res = catalog.deezer_album_search(a, al)
            return res

        def done(res):
            if key != self.track_key:
                return
            self.catalog = res
            if res:
                if self.state.dur <= 0 and res.get("dur"):
                    self.c_dur.set_value(fmt(res["dur"]))
                if self.cover_pm is None and res.get("cover"):
                    self._fetch_cover(key, res["cover"])
                if res.get("album_id"):
                    self._attach_album_id(key, res["album_id"])
                    self.show_album(res["album_id"], res.get("album") or al, res.get("artist") or a)
                    return
            if al:
                self.show_album(None, al, a)

        bg(work, done, lambda e: core.log("catalog:", e))
        if self.cfg.get("auto_clip"):
            self.search_clip(f"{a} {t} official video".strip(), a, t, int(st.dur), True)

    def _fetch_cover(self, key, url):
        def done(data):
            if key == self.track_key and self.cover_pm is None:
                self._set_cover(data)
        bg(lambda: http_get(url, 12), done, lambda e: None)

    def on_thumb(self, key, data: bytes):
        if key != self.track_key:
            return
        self._set_cover(data)

    def _set_cover(self, data: bytes):
        img = QImage.fromData(data)
        if img.isNull():
            return
        pm = QPixmap.fromImage(img)
        self.cover_pm = pm
        self.cover.set_pixmap(pm)
        self._refresh_accent()
        self._add_history()

    def _refresh_accent(self):
        col = None
        if self.cfg.get("auto_accent") and self.cover_pm is not None:
            col = dominant_color(self.cover_pm)
        T.set_accent(col)
        QApplication.instance().setStyleSheet(T.qss())
        self._bg_cache = None
        for w in self.findChildren(QWidget):
            w.update()
        self.update()

    # ============================================================== прогресс и громкость
    def _tick_progress(self):
        st = self.state
        if not st.has_session or not st.title:
            self.prog.set_value(0)
            self.t_cur.setText("0:00")
            self.t_end.setText("--:--")
            self._update_level()
            return
        dur = st.dur if st.dur > 0 else float((self.catalog or {}).get("dur") or 0)
        pos = st.now_pos()
        self.t_cur.setText(fmt(pos))
        self.t_end.setText(fmt(dur) if dur > 0 else "--:--")
        self.prog.set_value(int(pos / dur * (PROG_SEGS - 1)) if dur > 0 else 0)
        self._update_level()

    def _update_level(self):
        db = self.viz.level_db
        self.c_lvl.set_value("-∞ dB" if db <= -90 else f"{db:.0f} dB")
        if self.viz.live != getattr(self, "_live_prev", None):
            self._live_prev = self.viz.live
            self._update_info()
            self._update_meta()

    def _seek_frac(self, v):
        st = self.state
        dur = st.dur if st.dur > 0 else float((self.catalog or {}).get("dur") or 0)
        if not st.has_session or dur <= 0:
            return
        if not st.can_seek and not self.demo:
            self.toast.show_text("Этот плеер не поддерживает перемотку")
            return
        t = v / (PROG_SEGS - 1) * dur
        st.pos, st.stamp = t, time.monotonic()
        self.media.cmd("seek", t)
        if self.clip.vid and self.cfg.get("clip_follow"):
            self.clip.seek(t + self.offset)

    def _poll_volume(self):
        if not self.sysvol.ok:
            return
        v = self.sysvol.get()
        muted = self.sysvol.muted()
        self.h_vol.setText(f"{round(v * 100)}")
        self.h_cells.set_value(int(v * 10 + 0.999))
        if not (self.vol.underMouse() and QApplication.mouseButtons() & Qt.LeftButton):
            self.vol.set_value(round(v * 30))
        self.v_val.setText("MUTE" if muted else str(round(v * 30)))
        self.b_mute.set_kind("mute" if muted else "vol")
        self.viz.volume = 0.0 if muted else v

    def _user_volume(self, v):
        self.sysvol.set(v / 30.0)
        self.v_val.setText(str(v))

    def _step_volume(self, d):
        if not self.sysvol.ok:
            return
        v = max(0, min(30, round(self.sysvol.get() * 30) + d))
        self.sysvol.set(v / 30.0)
        self.vol.set_value(v)
        self._poll_volume()

    def _toggle_mute(self):
        if self.sysvol.ok:
            self.sysvol.set_mute(not self.sysvol.muted())
            self._poll_volume()

    # ============================================================== клип
    def _manual_search(self):
        q = self.search.text().strip()
        if q:
            self.search.clearFocus()
            self.search_clip(q, "", "", 0, True, rank=False)

    def search_clip(self, query, artist, title, dur, auto_play, rank=True):
        self.clip_req += 1
        req = self.clip_req
        self.clip_status.setText("Ищу клип…")

        def work():
            items = catalog.yt_search(query)
            return catalog.rank_clips(items, artist, title, dur) if rank and (artist or title) else items

        def done(items):
            if req != self.clip_req:
                return
            self._show_results(items)
            if not items:
                self.clip_status.setText("Клипов не найдено")
                return
            if auto_play:
                self.clip_fail = 0
                self._play_clip(0)

        def fail(e):
            if req == self.clip_req:
                self.clip_status.setText("Поиск не удался: " + str(e)[:70])

        bg(work, done, fail)

    def _show_results(self, items):
        self.clip_items = items
        self.clip_idx = -1
        self.results.clear()
        for it in items:
            li = QListWidgetItem(f"{it['title']}\n{it['channel']} · {it['dur_txt']}")
            li.setSizeHint(QSize(0, 54))
            self.results.addItem(li)

            def done(data, li=li):
                pm = QPixmap()
                try:
                    if pm.loadFromData(data):
                        li.setIcon(QIcon(pm))
                except RuntimeError:  # строку уже удалили новым поиском
                    pass
            bg(lambda u=it["thumb"]: http_get(u, 8), done, lambda e: None)

    def _play_clip(self, i):
        if not (0 <= i < len(self.clip_items)):
            return
        it = self.clip_items[i]
        self.clip_idx = i
        self.results.setCurrentRow(i)
        start = 0.0
        if self.state.has_session and self.state.now_pos() > 3:
            start = self.state.now_pos() + self.offset
        self.clip_status.setText(f"{it['title']}")
        self.clip_status.set_color(T.TEXT)
        self.clip_time = 0.0
        if self.clip.available():
            self.clip.load(it["id"], start)
        else:
            self.clip_status.setText("Встроенный плеер недоступен — открой клип в браузере (↗)")

    def _clip_ready(self):
        self.clip_fail = 0
        self._apply_clip_play_state()
        st = self.state
        if st.has_session and st.now_pos() > 3 and st.playing:
            self.clip.seek(st.now_pos() + self.offset)

    def _clip_failed(self, code):
        self.clip_fail += 1
        if code == "net":
            self.clip_status.setText("Нет доступа к YouTube")
            return
        if self.clip_fail <= 3 and self.clip_idx + 1 < len(self.clip_items):
            self.clip_status.setText(f"Этот ролик нельзя встроить (код {code}), пробую следующий…")
            self._play_clip(self.clip_idx + 1)
        else:
            self.clip_status.setText(f"Не удалось воспроизвести клип (код {code}). Выбери другой в списке")

    def _clip_tick(self, t, ytstate):
        self.clip_time = t
        st = self.state
        if st.has_session and st.playing and ytstate == 1:
            d = t - (st.now_pos() + self.offset)
            self.l_drift.setText(f"Δ{d:+.1f}с")
            col = T.OK if abs(d) < 1.0 else (T.acc().name() if abs(d) < 3 else T.BAD)
            self.l_drift.setStyleSheet(f"color:{col}")
        else:
            self.l_drift.setText("")

    def _apply_clip_play_state(self):
        if not self.clip.vid:
            return
        if self.cfg.get("clip_follow") and not self.last_playing:
            self.clip.pause()
        else:
            self.clip.play()

    def _clip_step(self, d):
        if self.clip_items:
            self.clip_fail = 0
            self._play_clip((self.clip_idx + d) % len(self.clip_items))

    def _shift(self, d):
        self.offset = round(self.offset + d, 1)
        self.cfg.set("clip_offset", self.offset)
        self._update_off()
        self._sync_clip()

    def _update_off(self):
        self.l_off.setText(f"{self.offset:+.1f}с")
        self.l_off.setStyleSheet(f"color:{T.TEXT if self.offset else T.MUTED}")

    def _sync_clip(self):
        if self.clip.vid and self.state.has_session:
            self.clip.seek(self.state.now_pos() + self.offset)
            self.toast.show_text("Клип синхронизирован с музыкой")

    def _open_ext(self):
        if 0 <= self.clip_idx < len(self.clip_items):
            t = int(self.state.now_pos()) if self.state.has_session else 0
            QDesktopServices.openUrl(QUrl(f"https://www.youtube.com/watch?v={self.clip_items[self.clip_idx]['id']}&t={t}s"))

    # ============================================================== альбомы
    def _entry_key(self, artist, album, title):
        return f"{catalog.norm(artist)}|{catalog.norm(album or title)}"

    def _cover_file(self, key):
        d = data_dir() / "covers"
        d.mkdir(exist_ok=True)
        return d / (hashlib.md5(key.encode("utf-8")).hexdigest() + ".jpg")

    def _add_history(self):
        st = self.state
        if self.cover_pm is None or not st.title:
            return
        k = self._entry_key(st.artist, st.album, st.title)
        f = self._cover_file(k)
        self.cover_pm.scaled(256, 256, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation).save(str(f), "JPG", 88)
        old = next((e for e in self.history if e["key"] == k), None)
        ent = {"key": k, "album": st.album or st.title, "artist": st.artist,
               "file": f.name, "album_id": (old or {}).get("album_id")}
        self.history = [ent] + [e for e in self.history if e["key"] != k]
        self.history = self.history[:24]
        self.cfg.set("history", self.history)
        self._rebuild_shelf()

    def _attach_album_id(self, key, album_id):
        st = self.state
        k = self._entry_key(st.artist, st.album, st.title)
        for e in self.history:
            if e["key"] == k and e.get("album_id") != album_id:
                e["album_id"] = album_id
                self.cfg.set("history", self.history)

    def _rebuild_shelf(self):
        self.shelf.clear()
        d = data_dir() / "covers"
        for e in self.history:
            pm = QPixmap(str(d / e["file"]))
            it = QListWidgetItem(QIcon(pm) if not pm.isNull() else QIcon(), e["album"])
            it.setToolTip(f"{e['album']}\n{e['artist']}")
            it.setData(Qt.UserRole, e)
            it.setSizeHint(QSize(100, 120))
            it.setTextAlignment(Qt.AlignHCenter | Qt.AlignTop)
            self.shelf.addItem(it)

    def _shelf_clicked(self, it):
        e = it.data(Qt.UserRole)
        self.show_album(e.get("album_id"), e["album"], e["artist"])

    def show_album(self, album_id, album, artist):
        self.album_req += 1
        req = self.album_req
        self.a_title.setText(album or "Альбом")
        self.a_sub.setText(artist or "")
        self.tracks.clear()

        def work():
            aid = album_id
            if not aid:
                r = catalog.deezer_album_search(artist, album)
                aid = r and r.get("album_id")
            return catalog.deezer_album_tracks(aid) if aid else []

        def done(tracks):
            if req != self.album_req:
                return
            cur = catalog.norm(self.state.title)
            for tr in tracks:
                d = dict(tr)
                tn = catalog.norm(tr["title"])
                d["current"] = bool(cur) and (tn == cur or cur in tn or tn in cur)
                li = QListWidgetItem()
                li.setData(Qt.UserRole, d)
                li.setSizeHint(QSize(0, 28))
                self.tracks.addItem(li)
            if not tracks:
                self.a_sub.setText((artist or "") + " · треклист не найден")

        bg(work, done, lambda e: self.a_sub.setText("Треклист недоступен"))

    def _track_clicked(self, it):
        d = it.data(Qt.UserRole)
        artist = d.get("artist") or self.a_sub.text().split(" · ")[0]
        self.search.setText(f"{artist} {d['title']}")
        self.search_clip(f"{artist} {d['title']} official video", artist, d["title"], d.get("dur", 0), True)

    # ============================================================== окно, фон, клавиши
    def _dark_titlebar(self):
        if sys.platform != "win32" or self._dark_done:
            return
        try:
            import ctypes
            hwnd = int(self.winId())
            v = ctypes.c_int(1)
            for attr in (20, 19):
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), 4)
            self._dark_done = True
        except Exception:
            pass

    def showEvent(self, e):
        super().showEvent(e)
        self._dark_titlebar()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._bg_cache = None

    def paintEvent(self, e):
        if self._bg_cache is None or self._bg_cache.size() != self.size():
            pm = QPixmap(self.size())
            pm.fill(QColor(T.BG))
            p = QPainter(pm)
            W, H = self.width(), self.height()
            a = T.acc()
            a.setAlpha(26)
            g = QRadialGradient(QPointF(W * 0.7, -H * 0.1), 760)
            g.setColorAt(0, a)
            a.setAlpha(0)
            g.setColorAt(1, a)
            p.fillRect(0, 0, W, H, g)
            c = QColor(T.CY)
            c.setAlpha(18)
            g2 = QRadialGradient(QPointF(-W * 0.05, H * 1.1), 640)
            g2.setColorAt(0, c)
            c.setAlpha(0)
            g2.setColorAt(1, c)
            p.fillRect(0, 0, W, H, g2)
            gl = QColor(255, 255, 255, 7)
            for x in range(31, W, 32):
                p.fillRect(x, 0, 1, H, gl)
            for y in range(31, H, 32):
                p.fillRect(0, y, W, 1, gl)
            p.end()
            self._bg_cache = pm
        QPainter(self).drawPixmap(e.rect(), self._bg_cache, e.rect())

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.KeyPress and self.isActiveWindow():
            fw = QApplication.focusWidget()
            k = ev.key()
            if isinstance(fw, QLineEdit):
                if k == Qt.Key_Escape:
                    fw.clearFocus()
                    return True
                return False
            if ev.modifiers() & (Qt.ControlModifier | Qt.AltModifier):
                return False
            if k == Qt.Key_Space:
                self.media.cmd("toggle")
            elif k == Qt.Key_Right:
                self.media.cmd("next")
            elif k == Qt.Key_Left:
                self.media.cmd("prev")
            elif k == Qt.Key_Up:
                self._step_volume(1)
            elif k == Qt.Key_Down:
                self._step_volume(-1)
            elif k == Qt.Key_M:
                self._toggle_mute()
            elif k == Qt.Key_V:
                self._cycle_viz()
            elif k == Qt.Key_C:
                self._set_clip_visible(not self.clip_panel.isVisible())
            elif k == Qt.Key_F or k == Qt.Key_F11:
                self._toggle_full()
            elif k == Qt.Key_P:
                self._set_on_top(not self.cfg.get("on_top"))
            elif k in (Qt.Key_Slash, Qt.Key_Question):
                self._set_clip_visible(True)
                self.search.setFocus()
                self.search.selectAll()
            elif k == Qt.Key_Escape and self.isFullScreen():
                self.showNormal()
            else:
                return False
            return True
        return False

    def closeEvent(self, e):
        try:
            self.an.stop()
            self.clip.stop()
        except Exception:
            pass
        super().closeEvent(e)


def run(demo=False):
    app = QApplication(sys.argv)
    app.setApplicationName("Media Panel")
    core.init()
    T.init_fonts()
    app.setFont(T.ui(13))
    app.setStyleSheet(T.qss())
    if sys.platform != "win32":
        demo = True
    w = MainWindow(demo)
    w.show()
    sys.exit(app.exec())
