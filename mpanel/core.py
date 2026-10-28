"""Общие утилиты: настройки, фоновые задачи, потокобезопасный вызов в GUI."""
import json
import os
import sys
import traceback
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal, Slot


def data_dir() -> Path:
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    p = Path(base) / "MediaPanel"
    p.mkdir(parents=True, exist_ok=True)
    return p


class Settings:
    DEFAULTS = {
        "viz_mode": "bars",
        "sens": 4,
        "peaks": True,
        "auto_accent": False,
        "auto_clip": True,
        "clip_follow": True,
        "on_top": False,
        "clip_visible": True,
        "clip_offset": 0.0,
        "history": [],
        "geometry": None,
    }

    def __init__(self):
        self.path = data_dir() / "settings.json"
        self.data = dict(self.DEFAULTS)
        try:
            self.data.update(json.loads(self.path.read_text("utf-8")))
        except Exception:
            pass

    def get(self, k):
        return self.data.get(k, self.DEFAULTS.get(k))

    def set(self, k, v):
        self.data[k] = v
        self.save()

    def save(self):
        try:
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), "utf-8")
        except Exception:
            pass


class Dispatcher(QObject):
    """Позволяет вызвать функцию в GUI-потоке из любого потока."""
    _sig = Signal(object)

    def __init__(self):
        super().__init__()
        self._sig.connect(self._run, Qt.QueuedConnection)

    @Slot(object)
    def _run(self, fn):
        try:
            fn()
        except Exception:
            traceback.print_exc()

    def post(self, fn):
        self._sig.emit(fn)


_ui: Dispatcher | None = None
_pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="mp")


def init():
    global _ui
    _ui = Dispatcher()


def ui_post(fn):
    if _ui is not None:
        _ui.post(fn)


def bg(work, done=None, fail=None):
    """Выполнить work() в потоке, затем done(result) / fail(exc) в GUI-потоке."""
    def job():
        try:
            res = work()
        except Exception as e:  # noqa: BLE001
            ex = e
            if fail:
                ui_post(lambda: fail(ex))
            return
        if done:
            ui_post(lambda: done(res))
    _pool.submit(job)


UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def http_get(url: str, timeout: float = 10, headers: dict | None = None) -> bytes:
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def get_json(url: str, timeout: float = 10):
    return json.loads(http_get(url, timeout).decode("utf-8", "replace"))


def log(*a):
    try:
        print(*a, file=sys.stderr)
    except Exception:
        pass
