"""Проверка собранного exe: все ли зависимости на месте. Результат пишется в selftest.txt рядом с exe."""
import os
import sys
import traceback


def run() -> int:
    lines, bad = [], 0

    def check(name, fn):
        nonlocal bad
        try:
            fn()
            lines.append(f"OK    {name}")
        except Exception:  # noqa: BLE001
            bad += 1
            lines.append(f"FAIL  {name}\n{traceback.format_exc()}")

    check("PySide6.QtWidgets", lambda: __import__("PySide6.QtWidgets"))
    check("PySide6.QtWebEngineWidgets", lambda: __import__("PySide6.QtWebEngineWidgets"))
    check("numpy", lambda: __import__("numpy"))
    check("winrt.windows.media.control",
          lambda: __import__("winrt.windows.media.control", fromlist=["x"]))
    check("winrt.windows.storage.streams",
          lambda: __import__("winrt.windows.storage.streams", fromlist=["x"]))
    check("pyaudiowpatch", lambda: __import__("pyaudiowpatch"))
    check("pycaw", lambda: __import__("pycaw.pycaw", fromlist=["x"]))
    check("comtypes", lambda: __import__("comtypes"))
    check("mpanel.app", lambda: __import__("mpanel.app", fromlist=["x"]))

    out = "\n".join(lines) + f"\n\nпровалов: {bad}\n"
    base = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else __file__)
    try:
        with open(os.path.join(base, "selftest.txt"), "w", encoding="utf-8") as f:
            f.write(out)
    except Exception:
        pass
    try:
        print(out)
    except Exception:
        pass
    return 1 if bad else 0
