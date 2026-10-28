"""Живой спектр системного звука (WASAPI loopback). Если не вышло — интерфейс рисует имитацию."""
import threading
import time

import numpy as np

from .core import log

N_BANDS = 56
FFT = 2048
WAVE_N = 512


class Analyzer:
    """Захватывает то, что играет в колонках/наушниках по умолчанию, и считает спектр."""

    def __init__(self):
        self.active = False           # устройство открыто
        self.error: str | None = None
        self.backend = "—"
        self._lock = threading.Lock()
        self._bands = np.zeros(N_BANDS, dtype=np.float32)
        self._wave = np.zeros(WAVE_N, dtype=np.float32)
        self._lvl = (0.0, 0.0)
        self._ts = 0.0
        self._ring = np.zeros(FFT, dtype=np.float32)
        self._win = np.hanning(FFT).astype(np.float32)
        self._edges = None
        self._rate = 48000
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.device_name = ""

    # ------------------------------------------------------------ публичное
    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name="audio")
        self._thread.start()

    def stop(self):
        self._stop.set()

    def snapshot(self):
        """(bands 0..1, wave -1..1, (L, R) 0..1, fresh)"""
        with self._lock:
            fresh = (time.monotonic() - self._ts) < 0.25
            return self._bands.copy(), self._wave.copy(), self._lvl, fresh

    # ------------------------------------------------------------ потоки
    def _run(self):
        while not self._stop.is_set():
            try:
                self._run_pyaudio()
                self.active = False
                self._stop.wait(0.5)  # устройство сменилось / поток закрылся — открываем заново
                continue
            except Exception as e:  # noqa: BLE001
                self.error = str(e)
                log("audio(pyaudiowpatch):", e)
            self.active = False
            if self._stop.is_set():
                break
            try:
                self._run_soundcard()
            except Exception as e:  # noqa: BLE001
                self.error = str(e)
                log("audio(soundcard):", e)
            self.active = False
            self._stop.wait(4.0)

    def _run_pyaudio(self):
        import pyaudiowpatch as pa
        p = pa.PyAudio()
        try:
            wasapi = p.get_host_api_info_by_type(pa.paWASAPI)
            out = p.get_device_info_by_index(wasapi["defaultOutputDevice"])
            if not out.get("isLoopbackDevice"):
                for lb in p.get_loopback_device_info_generator():
                    if out["name"] in lb["name"]:
                        out = lb
                        break
                else:
                    raise RuntimeError("не найдено loopback-устройство")
            ch = max(1, int(out["maxInputChannels"]))
            rate = int(out["defaultSampleRate"])
            name = out["name"]

            def cb(in_data, frame_count, time_info, status):
                try:
                    a = np.frombuffer(in_data, dtype=np.float32)
                    self._feed(a.reshape(-1, ch), rate)
                except Exception:
                    pass
                return (None, pa.paContinue)

            stream = p.open(format=pa.paFloat32, channels=ch, rate=rate, input=True,
                            input_device_index=out["index"], frames_per_buffer=1024,
                            stream_callback=cb)
            self.backend, self.device_name = "WASAPI", name
            self.active, self.error = True, None
            while not self._stop.is_set():
                time.sleep(1.5)
                # устройство по умолчанию сменилось — переоткрываем
                try:
                    w2 = p.get_host_api_info_by_type(pa.paWASAPI)
                    cur = p.get_device_info_by_index(w2["defaultOutputDevice"])["name"]
                    if cur not in name and name not in cur:
                        break
                except Exception:
                    pass
                if not stream.is_active():
                    break
            stream.stop_stream()
            stream.close()
        finally:
            p.terminate()

    def _run_soundcard(self):
        import soundcard as sc
        spk = sc.default_speaker()
        mic = sc.get_microphone(id=str(spk.name), include_loopback=True)
        rate = 48000
        self.backend, self.device_name = "soundcard", spk.name
        self.active, self.error = True, None
        with mic.recorder(samplerate=rate, channels=2, blocksize=1024) as rec:
            while not self._stop.is_set():
                data = rec.record(numframes=1024)
                self._feed(np.asarray(data, dtype=np.float32), rate)
                if sc.default_speaker().name != spk.name:
                    break

    # ------------------------------------------------------------ DSP
    def _make_edges(self, rate):
        self._rate = rate
        f = np.geomspace(35.0, min(16000.0, rate / 2 - 100), N_BANDS + 1)
        self._edges = f
        self._centers = np.sqrt(f[:-1] * f[1:])
        self._tilt = (2.2 * np.log2(self._centers / 700.0)).astype(np.float32)

    def _feed(self, a: np.ndarray, rate: int):
        if a.ndim == 1:
            a = a.reshape(-1, 1)
        if self._edges is None or rate != self._rate:
            self._make_edges(rate)
        mono = a.mean(axis=1)
        n = len(mono)
        if n >= FFT:
            self._ring[:] = mono[-FFT:]
        else:
            self._ring = np.roll(self._ring, -n)
            self._ring[-n:] = mono
        peak_l = float(np.max(np.abs(a[:, 0]))) if n else 0.0
        peak_r = float(np.max(np.abs(a[:, 1 if a.shape[1] > 1 else 0]))) if n else 0.0

        spec = np.abs(np.fft.rfft(self._ring * self._win)) / (FFT / 4.0)
        freqs = np.fft.rfftfreq(FFT, 1.0 / rate)
        bands = np.zeros(N_BANDS, dtype=np.float32)
        lo_idx = np.searchsorted(freqs, self._edges[:-1])
        hi_idx = np.searchsorted(freqs, self._edges[1:])
        for i in range(N_BANDS):
            lo, hi = lo_idx[i], max(hi_idx[i], lo_idx[i] + 1)
            if hi - lo <= 1:  # узкая низкая полоса — интерполяция между бинами
                v = float(np.interp(self._centers[i], freqs, spec))
            else:
                v = float(spec[lo:hi].max())
            bands[i] = v
        db = 20.0 * np.log10(bands + 1e-9) + self._tilt
        norm = np.clip((db + 72.0) / 58.0, 0.0, 1.0)

        w = self._ring[-WAVE_N * 2:: 2] if len(self._ring) >= WAVE_N * 2 else self._ring[-WAVE_N:]
        with self._lock:
            self._bands = norm.astype(np.float32)
            self._wave = np.clip(w[-WAVE_N:], -1, 1).astype(np.float32)
            self._lvl = (min(1.0, peak_l), min(1.0, peak_r))
            self._ts = time.monotonic()
