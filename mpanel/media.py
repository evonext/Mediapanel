"""Источник медиа: системная сессия Windows (SMTC) — Spotify, Яндекс Музыка, браузер, любой плеер.

Интерфейс у WinMedia и DemoMedia одинаковый:
  start(), cmd(name, arg=None), поля-колбэки on_state(MediaState), on_thumb(key, bytes)
cmd: 'toggle' | 'play' | 'pause' | 'next' | 'prev' | 'seek' (arg — секунды)
"""
import asyncio
import datetime as dt
import math
import threading
import time
from dataclasses import dataclass

from .core import log, ui_post


@dataclass
class MediaState:
    has_session: bool = False
    app: str = ""
    title: str = ""
    artist: str = ""
    album: str = ""
    playing: bool = False
    pos: float = 0.0          # секунд на момент stamp
    dur: float = 0.0
    stamp: float = 0.0        # time.monotonic() в момент измерения pos
    can_seek: bool = False

    @property
    def key(self) -> str:
        return f"{self.artist}|{self.title}|{self.album}"

    def now_pos(self) -> float:
        p = self.pos
        if self.playing:
            p += time.monotonic() - self.stamp
        if self.dur > 0:
            p = min(p, self.dur)
        return max(0.0, p)


def pretty_app(aumid: str) -> str:
    a = (aumid or "").lower()
    table = {
        "spotify": "Spotify", "yandex": "Яндекс Музыка", "chrome": "Chrome", "msedge": "Edge",
        "firefox": "Firefox", "opera": "Opera", "brave": "Brave", "vlc": "VLC",
        "musicbee": "MusicBee", "aimp": "AIMP", "foobar": "foobar2000", "itunes": "iTunes",
        "applemusic": "Apple Music", "zunemusic": "Media Player", "wmplayer": "Media Player",
        "yandexmusic": "Яндекс Музыка", "vk": "VK Музыка",
    }
    for k, v in table.items():
        if k in a:
            return v
    return (aumid or "—").replace(".exe", "").split("!")[-1].split(".")[-1] or "—"


class WinMedia(threading.Thread):
    def __init__(self, on_state, on_thumb):
        super().__init__(daemon=True, name="smtc")
        self.on_state = on_state
        self.on_thumb = on_thumb
        self.loop: asyncio.AbstractEventLoop | None = None
        self.mgr = None
        self._key = None
        self._thumb_tries = 0
        self._thumb_ok = False
        self.error: str | None = None
        self._ready = threading.Event()

    # -- публичное
    def cmd(self, name: str, arg=None):
        if not self.loop:
            return
        asyncio.run_coroutine_threadsafe(self._cmd(name, arg), self.loop)

    # -- поток
    def run(self):
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self._main())
        except Exception as e:  # noqa: BLE001
            self.error = str(e)
            log("SMTC error:", e)

    async def _main(self):
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as Mgr)
        self.mgr = await Mgr.request_async()
        while True:
            try:
                await self._poll()
            except Exception as e:  # noqa: BLE001
                log("poll:", e)
            await asyncio.sleep(0.6)

    async def _poll(self):
        sess = self.mgr.get_current_session()
        if not sess:
            self._emit(MediaState(has_session=False))
            self._key = None
            return
        info = await sess.try_get_media_properties_async()
        pb = sess.get_playback_info()
        tl = sess.get_timeline_properties()
        st = MediaState(has_session=True)
        st.app = pretty_app(sess.source_app_user_model_id)
        st.title = (info.title or "").strip()
        st.artist = (info.artist or "").strip()
        st.album = (info.album_title or "").strip()
        st.playing = int(pb.playback_status) == 4  # PLAYING
        try:
            st.can_seek = bool(pb.controls.is_playback_position_enabled)
        except Exception:
            st.can_seek = False
        try:
            start = tl.start_time.total_seconds()
            end = tl.end_time.total_seconds()
            st.dur = max(0.0, end - start)
            pos = tl.position.total_seconds() - start
            try:
                age = (dt.datetime.now(dt.timezone.utc) - tl.last_updated_time).total_seconds()
                if not (0 <= age < 86400):
                    age = 0
            except Exception:
                age = 0
            st.pos = pos + (age if st.playing else 0)
        except Exception:
            pass
        st.stamp = time.monotonic()
        self._emit(st)

        key = st.key
        if key != self._key:
            self._key = key
            self._thumb_tries = 0
            self._thumb_ok = False
        if not self._thumb_ok and self._thumb_tries < 4 and st.title:
            self._thumb_tries += 1
            data = await self._read_thumb(info)
            if data:
                self._thumb_ok = True
                ui_post(lambda k=key, d=data: self.on_thumb(k, d))

    async def _read_thumb(self, info) -> bytes | None:
        try:
            ref = info.thumbnail
            if not ref:
                return None
            from winrt.windows.storage.streams import Buffer, DataReader, InputStreamOptions
            stream = await ref.open_read_async()
            size = int(stream.size)
            if size <= 0:
                return None
            buf = Buffer(size)
            await stream.read_async(buf, size, InputStreamOptions.READ_AHEAD)
            reader = DataReader.from_buffer(buf)
            data = bytearray(buf.length)
            reader.read_bytes(data)
            return bytes(data)
        except Exception as e:  # noqa: BLE001
            log("thumb:", e)
            return None

    def _emit(self, st: MediaState):
        ui_post(lambda s=st: self.on_state(s))

    async def _cmd(self, name, arg):
        sess = self.mgr.get_current_session() if self.mgr else None
        if not sess:
            return
        try:
            if name == "toggle":
                await sess.try_toggle_play_pause_async()
            elif name == "play":
                await sess.try_play_async()
            elif name == "pause":
                await sess.try_pause_async()
            elif name == "next":
                await sess.try_skip_next_async()
            elif name == "prev":
                await sess.try_skip_previous_async()
            elif name == "seek":
                await sess.try_change_playback_position_async(int(float(arg) * 10_000_000))
        except Exception as e:  # noqa: BLE001
            log("cmd", name, e)


# ----------------------------------------------------------------------------- демо
class DemoMedia:
    """Фейковый плеер для проверки интерфейса без Windows (--demo)."""
    TRACKS = [
        ("Daft Punk", "Harder, Better, Faster, Stronger", "Discovery", 224),
        ("The Weeknd", "Blinding Lights", "After Hours", 200),
        ("Kavinsky", "Nightcall", "OutRun", 258),
        ("Måneskin", "Beggin'", "Teatro d'ira - Vol. I", 211),
    ]

    def __init__(self, on_state, on_thumb):
        from PySide6.QtCore import QTimer
        self.on_state, self.on_thumb = on_state, on_thumb
        self.i = 0
        self.playing = True
        self.pos = 37.0
        self.stamp = time.monotonic()
        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)
        self.error = None

    def start(self):
        self.timer.start(600)
        self._send_thumb()

    def _state(self) -> MediaState:
        a, t, al, d = self.TRACKS[self.i]
        return MediaState(True, "Demo Player", t, a, al, self.playing,
                          self.pos, d, self.stamp, True)

    def _tick(self):
        now = time.monotonic()
        if self.playing:
            self.pos += now - self.stamp
        self.stamp = now
        if self.pos >= self.TRACKS[self.i][3]:
            self.cmd("next")
            return
        self.on_state(self._state())

    def _send_thumb(self):
        from PySide6.QtCore import QBuffer, QIODevice
        from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter
        img = QImage(300, 300, QImage.Format_RGB32)
        p = QPainter(img)
        hue = (self.i * 83 + 10) % 360
        g = QLinearGradient(0, 0, 300, 300)
        g.setColorAt(0, QColor.fromHsv(hue, 200, 255))
        g.setColorAt(1, QColor.fromHsv((hue + 60) % 360, 230, 90))
        p.fillRect(0, 0, 300, 300, g)
        p.setPen(QColor(255, 255, 255, 90))
        for r in range(30, 160, 22):
            p.drawEllipse(150 - r, 150 - r, 2 * r, 2 * r)
        p.end()
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        img.save(buf, "PNG")
        self.on_thumb(self._state().key, bytes(buf.data()))

    def cmd(self, name, arg=None):
        if name in ("toggle", "play", "pause"):
            self.playing = (not self.playing) if name == "toggle" else (name == "play")
        elif name in ("next", "prev"):
            self.i = (self.i + (1 if name == "next" else -1)) % len(self.TRACKS)
            self.pos = 0.0
            self.stamp = time.monotonic()
            self.on_state(self._state())
            self._send_thumb()
        elif name == "seek":
            self.pos = float(arg)
        self.stamp = time.monotonic()
        self.on_state(self._state())
