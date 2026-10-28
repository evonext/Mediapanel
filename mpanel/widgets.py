"""Самописные виджеты в стиле XM4 Control: панели с уголками, сегментные шкалы, визуализатор."""
import math
import random
import time

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QFontMetrics, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPixmap, QPolygonF, QRadialGradient)
from PySide6.QtWidgets import (QAbstractButton, QFrame, QHBoxLayout, QLabel, QPushButton,
                               QSizePolicy, QVBoxLayout, QWidget)

from . import theme as T
from .audio import N_BANDS


# =============================================================================== панели
class _HeadLabel(QWidget):
    def __init__(self, num: str, title: str):
        super().__init__()
        self.num, self.title = num, title
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def sizeHint(self):
        f = T.mono(11, True, 1.6)
        fm = QFontMetrics(f)
        return QSize(fm.horizontalAdvance(f"{self.num}{self.title.upper()}") + 12, 16)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setFont(T.mono(11, True, 1.6))
        fm = p.fontMetrics()
        y = (self.height() + fm.ascent() - fm.descent()) // 2
        p.setPen(T.acc())
        p.drawText(0, y, self.num)
        w = fm.horizontalAdvance(self.num) + 10
        p.setPen(QColor(T.MUTED))
        p.drawText(w, y, self.title.upper())


class _HeadLine(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(16)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, e):
        p = QPainter(self)
        g = QLinearGradient(0, 0, self.width(), 0)
        g.setColorAt(0, QColor(T.LINE2))
        g.setColorAt(1, QColor(38, 49, 61, 0))
        p.fillRect(0, self.height() // 2, self.width(), 1, g)


class Panel(QFrame):
    """Панель с градиентом, рамкой и оранжевыми уголками (.panel из XM4)."""

    def __init__(self, num: str | None = None, title: str = "", margins=(18, 14, 18, 16)):
        super().__init__()
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(*margins)
        self.lay.setSpacing(12)
        self.head = None
        if num is not None:
            self.head = QHBoxLayout()
            self.head.setSpacing(10)
            self.head.addWidget(_HeadLabel(num, title))
            self.head.addWidget(_HeadLine(), 1)
            self.lay.addLayout(self.head)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        g = QLinearGradient(0, 0, 0, self.height())
        g.setColorAt(0, QColor(T.PANEL2))
        g.setColorAt(1, QColor(T.PANEL))
        p.setBrush(g)
        p.setPen(QPen(QColor(T.LINE), 1))
        p.drawRoundedRect(r, 6, 6)
        c = T.acc()
        c.setAlpha(180)
        p.setPen(QPen(c, 1))
        p.setBrush(Qt.NoBrush)
        l, t, rr, b = r.left(), r.top(), r.right(), r.bottom()
        a = QPainterPath()
        a.moveTo(l, t + 10)
        a.lineTo(l, t + 6)
        a.arcTo(QRectF(l, t, 12, 12), 180, -90)
        a.lineTo(l + 10, t)
        p.drawPath(a)
        d = QPainterPath()
        d.moveTo(rr, b - 10)
        d.lineTo(rr, b - 6)
        d.arcTo(QRectF(rr - 12, b - 12, 12, 12), 0, -90)
        d.lineTo(rr - 10, b)
        p.drawPath(d)


# =============================================================================== мелкие виджеты
class ElideLabel(QLabel):
    def __init__(self, text="", font=None, color=T.TEXT):
        super().__init__(text)
        if font:
            self.setFont(font)
        self._color = color
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(10)

    def set_color(self, c):
        self._color = c
        self.update()

    def sizeHint(self):
        fm = QFontMetrics(self.font())
        return QSize(fm.horizontalAdvance(self.text()) + 2, fm.height() + 2)

    def minimumSizeHint(self):
        return QSize(10, QFontMetrics(self.font()).height() + 2)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setFont(self.font())
        p.setPen(QColor(self._color))
        fm = p.fontMetrics()
        s = fm.elidedText(self.text(), Qt.ElideRight, self.width())
        p.drawText(self.rect(), Qt.AlignLeft | Qt.AlignVCenter, s)


class Chip(QWidget):
    """STATE [PLAY] — чип с подписью и цветным значением."""

    def __init__(self, label: str, value: str = "—", vcolor: str = T.CY):
        super().__init__()
        self.label, self.value, self.vcolor = label, value, vcolor
        self.setFixedHeight(24)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def set_value(self, v: str, color: str | None = None):
        self.value = v
        if color:
            self.vcolor = color
        self.updateGeometry()
        self.update()

    def sizeHint(self):
        fm = QFontMetrics(T.mono(10.5, True, 1.0))
        return QSize(fm.horizontalAdvance(f"{self.label} {self.value}") + 22, 24)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(T.BG))
        p.setPen(QPen(QColor(T.LINE2), 1))
        p.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 3, 3)
        p.setFont(T.mono(10.5, True, 1.0))
        fm = p.fontMetrics()
        y = (self.height() + fm.ascent() - fm.descent()) // 2
        p.setPen(QColor(T.MUTED))
        p.drawText(9, y, self.label)
        p.setPen(QColor(self.vcolor))
        p.drawText(9 + fm.horizontalAdvance(self.label + " "), y, self.value)


class Dot(QWidget):
    def __init__(self):
        super().__init__()
        self.state = "dim"
        self.setFixedSize(14, 14)
        self._t = QTimer(self)
        self._t.timeout.connect(self.update)
        self._t.start(90)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QColor({"ok": T.OK, "bad": T.BAD}.get(self.state, T.DIM))
        if self.state == "ok":
            k = 0.5 + 0.5 * math.sin(time.monotonic() * 3.0)
            g = QColor(c)
            g.setAlpha(int(40 + 40 * k))
            p.setBrush(g)
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(7, 7), 5.5 + k, 5.5 + k)
        p.setBrush(c)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(7, 7), 3.5, 3.5)


class Switch(QAbstractButton):
    """Переключатель .sw из XM4 (42×20)."""

    def __init__(self, checked=False):
        super().__init__()
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(42, 20)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on = self.isChecked()
        a = T.acc()
        r = QRectF(0.5, 0.5, 41, 19)
        if on:
            g = QColor(a)
            g.setAlpha(50)
            p.setBrush(g)
            p.setPen(QPen(a, 1))
        else:
            p.setBrush(QColor(T.BG))
            p.setPen(QPen(QColor(T.LINE2), 1))
        p.drawRoundedRect(r, 3, 3)
        x = 23 if on else 3
        p.setPen(Qt.NoPen)
        p.setBrush(a if on else QColor(T.DIM))
        p.drawRoundedRect(QRectF(x, 4, 16, 12), 2, 2)


class TagButton(QAbstractButton):
    """Маленькая монометка-кнопка (.tag из XM4)."""

    def __init__(self, text: str, checkable=True):
        super().__init__()
        self.setText(text)
        self.setCheckable(checkable)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedHeight(24)

    def sizeHint(self):
        fm = QFontMetrics(T.mono(10.5, True, 1.2))
        return QSize(fm.horizontalAdvance(self.text().upper()) + 20, 24)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on = self.isChecked()
        hov = self.underMouse()
        col = QColor(T.CY) if on else QColor(T.MUTED)
        border = QColor(T.CY) if on else (T.acc() if hov else QColor(T.LINE2))
        if on:
            g = QColor(T.CY)
            g.setAlpha(28)
            p.setBrush(g)
        else:
            p.setBrush(Qt.NoBrush)
        p.setPen(QPen(border, 1))
        p.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 3, 3)
        p.setFont(T.mono(10.5, True, 1.2))
        p.setPen(col)
        p.drawText(self.rect(), Qt.AlignCenter, self.text().upper())


class IconButton(QPushButton):
    """Кнопка с векторной иконкой."""

    def __init__(self, kind: str, size=40, primary=False, tip=""):
        super().__init__()
        self.kind = kind
        self.primary = primary
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setToolTip(tip)

    def set_kind(self, k: str):
        self.kind = k
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        a = T.acc()
        on = self.isCheckable() and self.isChecked()
        r = QRectF(0.5, 0.5, w - 1, h - 1)
        if self.primary:
            glow = QColor(a)
            glow.setAlpha(60 if not self.underMouse() else 95)
            for i, al in ((7, 18), (4, 30), (2, 46)):
                gc = QColor(glow)
                gc.setAlpha(al)
                p.setBrush(gc)
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(r.adjusted(-i, -i, i, i), 4 + i, 4 + i)
            p.setBrush(T.acc2() if self.underMouse() else a)
            p.setPen(QPen(a, 1))
            fg = QColor("#120700")
        else:
            p.setBrush(QColor(T.PANEL2))
            p.setPen(QPen(a if (self.underMouse() or on) else QColor(T.LINE2), 1))
            fg = a if on else QColor(T.TEXT)
        if on and not self.primary:
            g = QColor(a)
            g.setAlpha(28)
            p.setBrush(g)
        p.drawRoundedRect(r, 4, 4)
        self._icon(p, fg, w, h)

    def _icon(self, p: QPainter, fg: QColor, w, h):
        k = self.kind
        s = min(w, h)
        u = s / 40.0
        cx, cy = w / 2, h / 2
        p.setBrush(fg)
        p.setPen(Qt.NoPen)
        if k == "play":
            p.drawPolygon(QPolygonF([QPointF(cx - 6 * u + 1, cy - 9 * u), QPointF(cx + 10 * u + 1, cy),
                                     QPointF(cx - 6 * u + 1, cy + 9 * u)]))
        elif k == "pause":
            p.drawRoundedRect(QRectF(cx - 8 * u, cy - 9 * u, 5.5 * u, 18 * u), 1.2, 1.2)
            p.drawRoundedRect(QRectF(cx + 2.5 * u, cy - 9 * u, 5.5 * u, 18 * u), 1.2, 1.2)
        elif k in ("next", "prev"):
            d = 1 if k == "next" else -1
            x0 = cx - d * 6 * u
            p.drawPolygon(QPolygonF([QPointF(x0, cy - 7 * u), QPointF(x0 + d * 11 * u, cy),
                                     QPointF(x0, cy + 7 * u)]))
            p.drawRoundedRect(QRectF(cx + d * 6 * u - 1.2 * u, cy - 7 * u, 2.4 * u, 14 * u), 1, 1)
        else:
            pen = QPen(fg, max(1.6, 1.7 * u), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            if k in ("vol", "mute"):
                p.setBrush(fg)
                p.drawPolygon(QPolygonF([QPointF(cx - 9 * u, cy - 3.5 * u), QPointF(cx - 4 * u, cy - 3.5 * u),
                                         QPointF(cx + 1 * u, cy - 8 * u), QPointF(cx + 1 * u, cy + 8 * u),
                                         QPointF(cx - 4 * u, cy + 3.5 * u), QPointF(cx - 9 * u, cy + 3.5 * u)]))
                p.setBrush(Qt.NoBrush)
                if k == "vol":
                    p.drawArc(QRectF(cx - 4 * u, cy - 5 * u, 12 * u, 10 * u), -50 * 16, 100 * 16)
                    p.drawArc(QRectF(cx - 4 * u, cy - 9 * u, 20 * u, 18 * u), -50 * 16, 100 * 16)
                else:
                    p.drawLine(QPointF(cx + 4 * u, cy - 4 * u), QPointF(cx + 11 * u, cy + 4 * u))
                    p.drawLine(QPointF(cx + 11 * u, cy - 4 * u), QPointF(cx + 4 * u, cy + 4 * u))
            elif k == "pin":
                p.drawLine(QPointF(cx - 5 * u, cy + 8 * u), QPointF(cx + 1 * u, cy + 2 * u))
                p.drawPolygon(QPolygonF([QPointF(cx - 2 * u, cy - 8 * u), QPointF(cx + 8 * u, cy + 2 * u),
                                         QPointF(cx + 1 * u, cy + 3 * u), QPointF(cx - 6 * u, cy - 4 * u)]))
            elif k == "full":
                a = 8 * u
                for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                    x, y = cx + sx * a, cy + sy * a
                    p.drawLine(QPointF(x, y), QPointF(x - sx * 5 * u, y))
                    p.drawLine(QPointF(x, y), QPointF(x, y - sy * 5 * u))
            elif k == "clip":
                p.drawRoundedRect(QRectF(cx - 10 * u, cy - 7 * u, 20 * u, 14 * u), 2.5, 2.5)
                p.setBrush(fg)
                p.drawPolygon(QPolygonF([QPointF(cx - 2.5 * u, cy - 3.5 * u), QPointF(cx + 3.5 * u, cy),
                                         QPointF(cx - 2.5 * u, cy + 3.5 * u)]))
            elif k == "sync":
                p.drawArc(QRectF(cx - 8 * u, cy - 8 * u, 16 * u, 16 * u), 40 * 16, 250 * 16)
                p.setBrush(fg)
                p.drawPolygon(QPolygonF([QPointF(cx + 9 * u, cy - 7 * u), QPointF(cx + 9 * u, cy + 0.5 * u),
                                         QPointF(cx + 2 * u, cy - 3 * u)]))
            elif k == "minus":
                p.drawLine(QPointF(cx - 5 * u, cy), QPointF(cx + 5 * u, cy))
            elif k == "plus":
                p.drawLine(QPointF(cx - 5 * u, cy), QPointF(cx + 5 * u, cy))
                p.drawLine(QPointF(cx, cy - 5 * u), QPointF(cx, cy + 5 * u))
            elif k == "ext":
                p.drawRect(QRectF(cx - 8 * u, cy - 5 * u, 12 * u, 12 * u))
                p.drawLine(QPointF(cx - 1 * u, cy + 1 * u), QPointF(cx + 8 * u, cy - 8 * u))
                p.drawLine(QPointF(cx + 2 * u, cy - 8 * u), QPointF(cx + 8 * u, cy - 8 * u))
                p.drawLine(QPointF(cx + 8 * u, cy - 8 * u), QPointF(cx + 8 * u, cy - 2 * u))
            elif k == "search":
                p.drawEllipse(QRectF(cx - 7 * u, cy - 7 * u, 12 * u, 12 * u))
                p.drawLine(QPointF(cx + 3 * u, cy + 3 * u), QPointF(cx + 8 * u, cy + 8 * u))


class SegMeter(QWidget):
    """Сегментная шкала (.meter из XM4): громкость, прогресс, чувствительность."""
    changed = Signal(int)

    def __init__(self, vmin, vmax, value=0, color="acc", floor=None, seg_h=14, interactive=True):
        super().__init__()
        self.vmin, self.vmax, self.value_ = vmin, vmax, value
        self.color = color
        self.floor = vmin - 1 if floor is None else floor
        self.seg_h = seg_h
        self.interactive = interactive
        self.setMinimumHeight(seg_h + 6)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFocusPolicy(Qt.NoFocus)
        if interactive:
            self.setCursor(Qt.PointingHandCursor)

    def value(self):
        return self.value_

    def set_value(self, v):
        v = max(self.vmin, min(self.vmax, int(round(v))))
        if v != self.value_:
            self.value_ = v
            self.update()

    def _start(self):
        return max(0, self.floor - self.vmin + 1)

    def _from_x(self, x):
        start = self._start()
        count = (self.vmax - self.vmin + 1) - start
        f = max(0.0, min(1.0, x / max(1, self.width())))
        if start and f < 0.5 / count:
            return self.vmin
        if f >= 1:
            return self.vmax
        return self.vmin + start + int(f * count)

    def _user(self, x):
        v = self._from_x(x)
        if v != self.value_:
            self.value_ = v
            self.update()
            self.changed.emit(v)

    def mousePressEvent(self, e):
        if self.interactive and e.button() == Qt.LeftButton:
            self._user(e.position().x())

    def mouseMoveEvent(self, e):
        if self.interactive and e.buttons() & Qt.LeftButton:
            self._user(e.position().x())

    def wheelEvent(self, e):
        if self.interactive:
            d = 1 if e.angleDelta().y() > 0 else -1
            nv = max(self.vmin, min(self.vmax, self.value_ + d))
            if nv != self.value_:
                self.value_ = nv
                self.update()
                self.changed.emit(nv)

    def paintEvent(self, e):
        p = QPainter(self)
        start = self._start()
        n = (self.vmax - self.vmin + 1) - start
        gap = 3
        w = (self.width() - gap * (n - 1)) / n
        h = min(self.height(), self.seg_h)
        y = (self.height() - h) / 2
        if self.color == "cy":
            on_c, cur_c = QColor(T.CY), QColor("#a6f2ff")
        elif self.color == "ok":
            on_c = cur_c = QColor(T.OK)
        else:
            on_c, cur_c = T.acc(), T.acc2()
        glow = QColor(on_c)
        glow.setAlpha(48)
        off = QColor(T.LINE)
        v = self.value_
        for i in range(n):
            x = i * (w + gap)
            xv = self.vmin + start + i
            rect = QRectF(x, y, w, h)
            if xv <= v:
                p.fillRect(rect.adjusted(-1.5, -1.5, 1.5, 1.5), glow)
                p.fillRect(rect, cur_c if xv == v else on_c)
            else:
                p.fillRect(rect, off)


class Cover(QWidget):
    """Обложка со скан-линиями (как .cover в XM4)."""

    def __init__(self, size=150):
        super().__init__()
        self.pm: QPixmap | None = None
        self.setFixedSize(size, size)

    def set_size(self, s):
        self.setFixedSize(s, s)

    def set_pixmap(self, pm):
        self.pm = pm
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, 4, 4)
        p.setClipPath(path)
        p.fillRect(self.rect(), QColor(T.BG))
        if self.pm and not self.pm.isNull():
            pm = self.pm
            s = min(pm.width(), pm.height())
            src = QRectF((pm.width() - s) / 2, (pm.height() - s) / 2, s, s)
            p.drawPixmap(r, pm, src)
        else:
            c, rad = r.center(), r.width() * 0.26
            p.setPen(QPen(QColor(T.DIM), 1.4))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(c, rad, rad)
            p.drawEllipse(c, rad * 0.28, rad * 0.28)
        p.setClipping(False)
        p.setClipPath(path)
        sc = QColor(0, 0, 0, 46)
        for y in range(0, self.height(), 3):
            p.fillRect(0, y, self.width(), 1, sc)
        p.setClipping(False)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(T.LINE2), 1))
        p.drawRoundedRect(r, 4, 4)


class KeyHint(QWidget):
    def __init__(self, keys, text):
        super().__init__()
        self.keys, self.text = keys, text
        self.setFixedHeight(22)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._kf = T.mono(10.5, True, 0.4)

    def _kw(self):
        fm = QFontMetrics(self._kf)
        return [fm.horizontalAdvance(k) + 12 for k in self.keys]

    def sizeHint(self):
        fm = QFontMetrics(self._kf)
        return QSize(sum(self._kw()) + 4 * len(self.keys) + fm.horizontalAdvance(self.text) + 6, 22)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setFont(self._kf)
        x = 0
        for k, w in zip(self.keys, self._kw()):
            r = QRectF(x + 0.5, 2.5, w - 1, 16)
            p.setBrush(QColor(T.PANEL2))
            p.setPen(QPen(QColor(T.LINE2), 1))
            p.drawRoundedRect(r, 3, 3)
            p.setPen(QColor(T.LINE2).lighter(130))
            p.drawLine(QPointF(x + 2, 19), QPointF(x + w - 2, 19))
            p.setPen(QColor(T.TEXT))
            p.drawText(r, Qt.AlignCenter, k)
            x += w + 4
        p.setPen(QColor(T.MUTED))
        fm = p.fontMetrics()
        p.drawText(int(x + 2), (self.height() + fm.ascent() - fm.descent()) // 2, self.text)


class SettingRow(QWidget):
    """Строка настройки (.trow): заголовок + пояснение слева, контрол справа."""

    def __init__(self, title: str, hint: str, control: QWidget, first=False):
        super().__init__()
        self.first = first
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0 if first else 10, 0, 10 if False else 2)
        lay.setSpacing(12)
        col = QVBoxLayout()
        col.setSpacing(0)
        t = QLabel(title)
        t.setFont(T.ui(13, True))
        h = QLabel(hint)
        h.setFont(T.ui(11.5))
        h.setStyleSheet(f"color:{T.MUTED}")
        h.setWordWrap(True)
        col.addWidget(t)
        col.addWidget(h)
        lay.addLayout(col, 1)
        lay.addWidget(control, 0, Qt.AlignRight | Qt.AlignVCenter)

    def paintEvent(self, e):
        if self.first:
            return
        p = QPainter(self)
        pen = QPen(QColor(T.LINE2), 1, Qt.DashLine)
        p.setPen(pen)
        p.drawLine(0, 0, self.width(), 0)


class AspectBox(QWidget):
    """Контейнер, держащий пропорцию 16:9 по ширине (высота подгоняется при изменении размера)."""

    def __init__(self, child: QWidget, max_h: int = 400):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(child)
        self.max_h = max_h
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(180)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        h = max(100, min(self.max_h, int(self.width() * 9 / 16)))
        if h != self.height():
            self.setFixedHeight(h)

    def sizeHint(self):
        return QSize(320, 180)


# =============================================================================== визуализатор
class VizWidget(QWidget):
    MODES = ["bars", "mirror", "radial", "scope"]
    MODE_NAMES = {"bars": "Столбцы", "mirror": "Зеркало", "radial": "Круг", "scope": "Осциллограф"}

    def __init__(self, analyzer):
        super().__init__()
        self.an = analyzer
        self.mode = "bars"
        self.sens = 1.0
        self.peaks = True
        self.playing = False
        self.volume = 1.0
        self.n = N_BANDS
        self.h = np.zeros(self.n)
        self.pk = np.zeros(self.n)
        self.pkv = np.zeros(self.n)
        self.phase = [(random.random() * 6.28, 0.6 + random.random() * 1.6, random.random() * 6.28)
                      for _ in range(self.n)]
        self.beat = 0.0
        self.next_beat = 0.0
        self.rot = 0.0
        self.lvl = [0.0, 0.0]
        self.lvl_pk = [0.0, 0.0]
        self.lvl_pk_t = [0.0, 0.0]
        self.wave = np.zeros(512)
        self.live = False
        self.setMinimumHeight(130)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._t = QTimer(self)
        self._t.setInterval(16)
        self._t.timeout.connect(self._tick)
        self._t.start()

    # --- данные
    def set_mode(self, m):
        self.mode = m
        self.update()

    @property
    def level_db(self):
        v = max(self.lvl_pk[0], self.lvl_pk[1])
        return -99.0 if v < 1e-4 else 20 * math.log10(v)

    def _sim(self, now):
        n = self.n
        if self.playing and now > self.next_beat:
            self.beat = 0.55
            self.next_beat = now + 0.38 + random.random() * 0.26
        self.beat *= 0.9
        out = np.zeros(n)
        vol = 0.35 + 0.65 * self.volume
        for i in range(n):
            f = i / (n - 1)
            p1, sp, p2 = self.phase[i]
            tilt = 1.05 - f * 0.55
            wob = 0.45 + 0.3 * math.sin(now * 2.1 * sp + p1) + 0.2 * math.sin(now * 5.7 * sp + p2)
            kick = self.beat * (1 - f * 3) if f < 0.25 else self.beat * 0.25
            out[i] = (wob * tilt + kick) * vol * (0.85 + random.random() * 0.15)
        return np.clip(out, 0, 1) if self.playing else np.full(n, 0.02) + 0.015 * np.sin(now * 2 + np.arange(n) * 0.4)

    def _tick(self):
        if not self.isVisible():
            return
        now = time.monotonic()
        tgt = None
        lvl = None
        self.live = bool(self.an and self.an.active)
        if self.live:
            bands, wave, (l, r), fresh = self.an.snapshot()
            if fresh:
                tgt = np.clip(bands * self.sens, 0, 1)
                self.wave = wave
                lvl = (l, r)
            else:
                tgt = np.zeros(self.n)
                self.wave = self.wave * 0.8
                lvl = (0.0, 0.0)
        else:
            tgt = self._sim(now)
            amp = 0.5 * (0.35 + 0.65 * self.volume) if self.playing else 0.0
            xs = np.linspace(0, 1, 512)
            m = float(np.mean(tgt))
            w = np.zeros(512)
            for k in range(1, 6):
                w += math.sin(now * (1.3 + k * 0.7) + k) * np.sin(2 * math.pi * (k * 2.0 + 1) * xs + now * k) / k
            self.wave = np.clip(w * m * 1.4 * (1 if self.playing else 0.1), -1, 1)
            lvl = (min(1, m * 1.2 * amp * 2 * (0.8 + 0.2 * random.random())),
                   min(1, m * 1.2 * amp * 2 * (0.8 + 0.2 * random.random())))
        up = tgt > self.h
        self.h = np.where(up, self.h + (tgt - self.h) * 0.5, self.h + (tgt - self.h) * 0.13)
        # пики
        hold = self.h >= self.pk
        self.pk = np.where(hold, self.h, self.pk)
        self.pkv = np.where(hold, 0.0, self.pkv + 0.0009)
        self.pk = np.maximum(self.h, self.pk - self.pkv)
        # уровни
        for i in (0, 1):
            self.lvl[i] += (lvl[i] - self.lvl[i]) * (0.6 if lvl[i] > self.lvl[i] else 0.15)
            if self.lvl[i] >= self.lvl_pk[i]:
                self.lvl_pk[i] = self.lvl[i]
                self.lvl_pk_t[i] = now
            elif now - self.lvl_pk_t[i] > 0.9:
                self.lvl_pk[i] = max(self.lvl[i], self.lvl_pk[i] - 0.02)
        if self.playing:
            self.rot += 0.004
        self.update()

    # --- рисование
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        r = QRectF(0.5, 0.5, W - 1, H - 1)
        p.setBrush(QColor(T.BG))
        p.setPen(QPen(QColor(T.LINE), 1))
        p.drawRoundedRect(r, 4, 4)
        path = QPainterPath()
        path.addRoundedRect(r, 4, 4)
        p.setClipPath(path)
        gl = QColor(255, 255, 255, 10)
        for y in range(0, H, 11):
            p.fillRect(0, y, W, 1, gl)
        {"bars": self._bars, "mirror": self._mirror, "radial": self._radial,
         "scope": self._scope}[self.mode](p, W, H)
        self._vu(p, W, H)
        # метка источника
        p.setFont(T.mono(10, True, 1.2))
        txt = "LIVE ●" if self.live else "SIM"
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(txt) + 14
        tr = QRectF(W - tw - 30, 8, tw, 18)
        p.setBrush(QColor(6, 8, 11, 180))
        p.setPen(QPen(QColor(T.CY) if self.live else QColor(T.LINE2), 1))
        p.drawRoundedRect(tr, 3, 3)
        p.setPen(QColor(T.CY) if self.live else QColor(T.MUTED))
        p.drawText(tr, Qt.AlignCenter, txt)

    def _bars(self, p, W, H):
        n, gap = self.n, 3
        bw = (W - 34 - gap * (n - 1)) / n
        mid = H * 0.66
        a, a2 = T.acc(), T.acc2()
        grad = QLinearGradient(0, 0, 0, mid)
        grad.setColorAt(0, a2)
        grad.setColorAt(1, a)
        glow = QColor(a)
        glow.setAlpha(36)
        refl = QColor(T.CY)
        refl.setAlpha(56)
        capc = QColor(a2)
        for i in range(n):
            x = 6 + i * (bw + gap)
            up = max(1.5, self.h[i] * (mid - 10))
            p.fillRect(QRectF(x - 1.2, mid - up - 1.2, bw + 2.4, up + 2.4), glow)
            p.fillRect(QRectF(x, mid - up, bw, up), grad)
            p.fillRect(QRectF(x, mid + 2, bw, up * 0.32), refl)
            if self.peaks and self.pk[i] > 0.03:
                py = mid - self.pk[i] * (mid - 10) - 4
                p.fillRect(QRectF(x, py, bw, 2), capc)
        p.fillRect(QRectF(0, mid, W, 1), QColor(255, 255, 255, 22))

    def _mirror(self, p, W, H):
        n, gap = self.n, 3
        cols = n * 2
        bw = (W - 34 - gap * (cols - 1)) / cols
        mid = H / 2
        a, a2 = T.acc(), T.acc2()
        grad = QLinearGradient(0, 0, 0, H)
        grad.setColorAt(0, a2)
        grad.setColorAt(0.5, a)
        grad.setColorAt(1, a2)
        glow = QColor(a)
        glow.setAlpha(34)
        for j in range(cols):
            idx = min(n - 1, int(abs(j - (cols - 1) / 2)))   # низкие частоты — в центре
            x = 6 + j * (bw + gap)
            ext = max(1.0, self.h[idx] * (mid - 8))
            p.fillRect(QRectF(x - 1, mid - ext - 1, bw + 2, 2 * ext + 2), glow)
            p.fillRect(QRectF(x, mid - ext, bw, 2 * ext), grad)
            if self.peaks and self.pk[idx] > 0.03:
                pe = self.pk[idx] * (mid - 8) + 3
                p.fillRect(QRectF(x, mid - pe - 2, bw, 2), a2)
                p.fillRect(QRectF(x, mid + pe, bw, 2), a2)
        p.fillRect(QRectF(0, mid, W, 1), QColor(255, 255, 255, 18))

    def _radial(self, p, W, H):
        cx, cy = (W - 30) / 2, H / 2
        base = min(W - 30, H)
        pulse = float(np.mean(self.h[:8]))
        r0 = base * 0.2 * (1 + pulse * 0.12)
        rmax = base * 0.5 - 8
        n2 = self.n * 2
        a, c = T.acc(), QColor(T.CY)
        ring = QColor(a)
        ring.setAlpha(90)
        p.setPen(QPen(ring, 1))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy), r0 - 5, r0 - 5)
        for j in range(n2):
            idx = j if j < self.n else n2 - 1 - j
            ang = j / n2 * 2 * math.pi + self.rot
            ln = max(2.0, self.h[idx] * (rmax - r0))
            t = idx / (self.n - 1)
            col = QColor(int(a.red() + (c.red() - a.red()) * t), int(a.green() + (c.green() - a.green()) * t),
                         int(a.blue() + (c.blue() - a.blue()) * t))
            cs, sn = math.cos(ang), math.sin(ang)
            gc = QColor(col)
            gc.setAlpha(46)
            p.setPen(QPen(gc, 7, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(cx + cs * r0, cy + sn * r0), QPointF(cx + cs * (r0 + ln), cy + sn * (r0 + ln)))
            p.setPen(QPen(col, 3, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(cx + cs * r0, cy + sn * r0), QPointF(cx + cs * (r0 + ln), cy + sn * (r0 + ln)))

    def _scope(self, p, W, H):
        w = self.wave
        n = len(w)
        mid = H / 2
        xs = np.linspace(8, W - 30, n)
        amp = (H / 2 - 12) * min(1.8, 0.8 + self.sens)
        pts = [QPointF(float(xs[i]), float(mid - w[i] * amp)) for i in range(0, n, 2)]
        path = QPainterPath()
        path.moveTo(pts[0])
        for q in pts[1:]:
            path.lineTo(q)
        p.setBrush(Qt.NoBrush)
        c = QColor(T.CY)
        gc = QColor(c)
        gc.setAlpha(40)
        p.setPen(QPen(gc, 7, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(path)
        p.setPen(QPen(c, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(path)
        p.fillRect(QRectF(0, mid, W, 1), QColor(255, 255, 255, 22))

    def _vu(self, p, W, H):
        """Два вертикальных сегментных индикатора уровня L/R справа."""
        segs = 20
        top, bot = 10, H - 10
        sh = (bot - top - (segs - 1) * 2) / segs
        for ch in (0, 1):
            x = W - 24 + ch * 9
            v = self.lvl[ch] ** 0.6
            pkseg = int(min(1, self.lvl_pk[ch] ** 0.6) * segs)
            for s in range(segs):
                y = bot - (s + 1) * sh - s * 2
                on = (s + 1) <= int(v * segs + 0.5)
                col = QColor(T.OK) if s < 13 else (QColor("#ffd23f") if s < 17 else QColor(T.BAD))
                if on or s == pkseg - 1 and pkseg > 0:
                    p.fillRect(QRectF(x, y, 6, sh), col)
                else:
                    p.fillRect(QRectF(x, y, 6, sh), QColor(T.LINE))
