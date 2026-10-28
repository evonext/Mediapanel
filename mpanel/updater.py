"""Автообновление portable-exe: проверка последнего релиза на GitHub, фоновая загрузка,
подмена файла при закрытии (запущенный exe в Windows можно переименовать, поэтому установка не нужна)."""
import os
import subprocess
import sys

from . import core

REPO = "evonext/Mediapanel"
API = f"https://api.github.com/repos/{REPO}/releases/tags/latest"
ASSET = "MediaPanel.exe"


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def current_build() -> str:
    try:
        from ._build import BUILD
        return str(BUILD).strip()
    except Exception:
        return ""


def exe_path() -> str:
    return os.path.abspath(sys.executable)


def _new_path() -> str:
    return os.path.splitext(exe_path())[0] + ".update.exe"


def _old_path() -> str:
    return os.path.splitext(exe_path())[0] + ".old.exe"


def check() -> dict | None:
    """Возвращает {'sha','url','size'}, если на GitHub лежит более новая сборка, иначе None."""
    data = core.get_json(API, 12)
    body = (data.get("body") or "").strip()
    sha = body.split()[0] if body else ""
    asset = next((a for a in data.get("assets", []) if a.get("name") == ASSET), None)
    if not asset or not sha:
        return None
    if sha == current_build():
        return None
    return {"sha": sha, "url": asset["browser_download_url"], "size": int(asset.get("size") or 0)}


def download(info: dict, dest: str | None = None) -> str:
    dest = dest or _new_path()
    tmp = dest + ".part"
    data = core.http_get(info["url"], 180)
    if info.get("size") and len(data) != info["size"]:
        raise RuntimeError("размер файла не совпал")
    if data[:2] != b"MZ":
        raise RuntimeError("скачан не exe")
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, dest)
    return dest


def pending() -> bool:
    return os.path.exists(_new_path())


def apply_pending() -> bool:
    """Подменяет exe на скачанный. Вызывается при закрытии приложения."""
    new, cur, old = _new_path(), exe_path(), _old_path()
    if not os.path.exists(new):
        return False
    try:
        if os.path.exists(old):
            os.remove(old)
        os.replace(cur, old)          # запущенный exe переименовать можно
        try:
            os.replace(new, cur)
        except Exception:
            os.replace(old, cur)      # откат
            raise
        return True
    except Exception as e:  # noqa: BLE001
        core.log("update apply:", e)
        return False


def cleanup_old():
    try:
        if os.path.exists(_old_path()):
            os.remove(_old_path())
    except Exception:
        pass


def restart():
    env = dict(os.environ)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    for k in ("_MEIPASS2", "_PYI_APPLICATION_HOME_DIR"):
        env.pop(k, None)
    subprocess.Popen([exe_path()], env=env, close_fds=True)
