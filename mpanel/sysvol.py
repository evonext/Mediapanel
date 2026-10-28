"""Системная громкость Windows (pycaw / Core Audio)."""
from ctypes import POINTER, cast

from .core import log


class SysVolume:
    def __init__(self):
        self.ok = False
        self._vol = None
        try:
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            dev = AudioUtilities.GetSpeakers()
            ep = getattr(dev, "EndpointVolume", None)  # новые версии pycaw
            if ep is not None:
                self._vol = ep
            else:
                iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                self._vol = cast(iface, POINTER(IAudioEndpointVolume))
            self._vol.GetMasterVolumeLevelScalar()
            self.ok = True
        except Exception as e:  # noqa: BLE001
            log("sysvol:", e)

    def get(self) -> float:
        try:
            return float(self._vol.GetMasterVolumeLevelScalar()) if self.ok else 0.0
        except Exception:
            return 0.0

    def set(self, v: float):
        try:
            if self.ok:
                self._vol.SetMasterVolumeLevelScalar(max(0.0, min(1.0, v)), None)
        except Exception as e:  # noqa: BLE001
            log("sysvol set:", e)

    def muted(self) -> bool:
        try:
            return bool(self._vol.GetMute()) if self.ok else False
        except Exception:
            return False

    def set_mute(self, m: bool):
        try:
            if self.ok:
                self._vol.SetMute(1 if m else 0, None)
        except Exception as e:  # noqa: BLE001
            log("sysvol mute:", e)
