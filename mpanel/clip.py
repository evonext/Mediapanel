"""Плеер клипов на QtWebEngine: встроенный YouTube-плеер, а если владелец запретил встраивание —
обычная страница просмотра, из которой показывается только видео.

По умолчанию звук выключен (клип идёт параллельно с музыкой). set_muted(False) включает свой звук."""
import json

from PySide6.QtCore import QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

# QtWebEngine нужно импортировать ДО создания QApplication
try:
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
    from PySide6.QtWebEngineWidgets import QWebEngineView
    WEBENGINE_OK = True
    WEBENGINE_ERR = ""
except Exception as _e:  # noqa: BLE001
    WEBENGINE_OK = False
    WEBENGINE_ERR = str(_e)

from . import theme as T

BOX_CONTAIN = "left:0;top:0;width:100%;height:100%"
BOX_COVER = ("left:50%;top:50%;width:max(100vw,calc(100vh*16/9));height:max(100vh,calc(100vw*9/16));"
             "transform:translate(-50%,-50%)")

HTML = """<!doctype html><html><head><meta charset="utf-8">
<style>html,body{margin:0;height:100%;background:#000;overflow:hidden}
#p{position:absolute;border:0;pointer-events:none;__BOX__}</style></head>
<body><div id="p"></div><script>
var n=0;function rep(s){document.title='mp|'+s+'|'+(n++);}
var player=null,ready=false,MUTED=__MUTE__,VOL=__VOL__;
var tag=document.createElement('script');tag.src='https://www.youtube.com/iframe_api';
tag.onerror=function(){rep('err|net');};document.head.appendChild(tag);
function onYouTubeIframeAPIReady(){
 player=new YT.Player('p',{width:'100%',height:'100%',videoId:'__VID__',
  playerVars:{autoplay:1,mute:1,controls:0,disablekb:1,fs:0,rel:0,modestbranding:1,playsinline:1,
              iv_load_policy:3,cc_load_policy:0,start:__START__},
  events:{
   onReady:function(e){ready=true;
     if(MUTED){e.target.mute();}else{e.target.unMute();e.target.setVolume(VOL);}
     e.target.playVideo();rep('ready');},
   onStateChange:function(e){rep('state|'+e.data);},
   onError:function(e){rep('err|'+e.data);}
  }});
}
setInterval(function(){if(ready){try{rep('t|'+player.getCurrentTime().toFixed(2)+'|'+player.getPlayerState()+'|'+(player.getDuration()||0));}catch(x){}}},1000);
function ctl(c,a){if(!ready)return;try{
 if(c=='play')player.playVideo();else if(c=='pause')player.pauseVideo();
 else if(c=='seek')player.seekTo(a,true);else if(c=='mute')player.mute();
 else if(c=='unmute')player.unMute();else if(c=='vol')player.setVolume(a);}catch(x){}}
</script></body></html>"""

WATCH_CSS = (
    "html,body{background:#000!important;overflow:hidden!important}"
    "ytd-masthead,#masthead-container,#secondary,#below,#comments,ytd-miniplayer,"
    "tp-yt-iron-overlay-backdrop,ytd-consent-bump-v2-lightbox,ytd-popup-container,"
    "tp-yt-paper-dialog,ytd-mealbar-promo-renderer{display:none!important}"
    "#movie_player{position:fixed!important;left:0!important;top:0!important;width:100vw!important;"
    "height:100vh!important;z-index:2147483647!important;background:#000!important}"
    "#movie_player .html5-video-container{width:100%!important;height:100%!important}"
    "#movie_player video{width:100%!important;height:100%!important;left:0!important;top:0!important;"
    "object-fit:__FIT__!important}"
    ".ytp-chrome-bottom,.ytp-chrome-top,.ytp-gradient-top,.ytp-gradient-bottom,.ytp-ce-element,"
    ".ytp-pause-overlay,.ytp-endscreen-content,.ytp-cards-teaser,.ytp-paid-content-overlay,"
    ".ytp-watermark,.ytp-spinner,.ytp-iv-video-content,.annotation,.ytp-popup,.ytp-contextmenu,"
    ".ytp-ad-overlay-container,.ytp-ad-text-overlay,.ytp-large-play-button{display:none!important}"
)

WATCH_JS = """(function(){
 window.__mpmute=__MUTE__; window.__mpvol=__VOL__;
 if(window.__mp){return;} window.__mp=1;
 var st=document.createElement('style');st.textContent=__CSS__;document.documentElement.appendChild(st);
 function pv(){return document.querySelector('#movie_player video')||document.querySelector('video');}
 setInterval(function(){try{
   var v=pv(); if(v){ if(window.__mpmute){v.muted=true;v.volume=0;}else{v.muted=false;v.volume=window.__mpvol;} }
   var sk=document.querySelector('.ytp-skip-ad-button,.ytp-ad-skip-button,.ytp-ad-skip-button-modern,.ytp-ad-skip-button-container button');
   if(sk){sk.click();}
 }catch(e){}},400);
 window.__mpstate=function(){var v=pv(); if(!v){return '';}
   var ad=document.querySelector('.ad-showing')?1:0; var er=document.querySelector('.ytp-error')?1:0;
   return v.currentTime.toFixed(2)+'|'+(v.ended?0:(v.paused?2:1))+'|'+ad+'|'+er+'|'+(isFinite(v.duration)?v.duration:0);};
 window.__mpctl=function(c,a){var v=pv(); if(!v){return;} if(document.querySelector('.ad-showing')&&c=='seek'){return;}
   if(c=='play'){var p=v.play(); if(p&&p.catch){p.catch(function(){});}} else if(c=='pause'){v.pause();}
   else if(c=='seek'){v.currentTime=a;}
   else if(c=='mute'){window.__mpmute=true;} else if(c=='unmute'){window.__mpmute=false;}
   else if(c=='vol'){window.__mpvol=a;}};
})();"""


class ClipPlayer(QWidget):
    ready = Signal()
    failed = Signal(str)          # код ошибки YouTube, 'watch' или 'net'
    tick = Signal(float, int)     # время клипа, состояние (1 играет, 2 пауза, 3 буфер/реклама, 0 конец)
    state = Signal(int)
    info = Signal(float)          # длительность клипа, секунд

    def __init__(self, fill: bool = False, transparent: bool = False):
        super().__init__()
        self.vid = None
        self.view = None
        self.mode = "embed"          # embed | watch
        self.fill = fill             # True — заполнять всю область (cover), иначе вписывать (contain)
        self.muted = True
        self.volume = 70
        self._start = 0.0
        self._ready_sent = False
        self._poll_busy = False
        self.setStyleSheet("background:transparent")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.holder = QLabel()
        self.holder.setAlignment(Qt.AlignCenter)
        if transparent:
            self.holder.setStyleSheet("background:transparent;border:0")
        else:
            self.holder.setStyleSheet(f"background:#000;color:{T.MUTED};border:1px solid {T.LINE2};"
                                      f"border-radius:4px;font-size:12px;")
        lay.addWidget(self.holder)
        self._transparent = transparent
        if WEBENGINE_OK:
            self.view = QWebEngineView()
            self.view.setContextMenuPolicy(Qt.NoContextMenu)
            page = self.view.page()
            page.setAudioMuted(True)
            page.setBackgroundColor(QColor("#000000"))
            s = page.settings()
            s.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
            self.view.titleChanged.connect(self._title)
            self.view.loadFinished.connect(self._load_finished)
            self._poll = QTimer(self)
            self._poll.setInterval(1000)
            self._poll.timeout.connect(self._poll_watch)
            lay.addWidget(self.view)
            self.view.hide()
            if not transparent:
                self.holder.setText("КЛИП\nНайди трек или включи музыку")
        elif not transparent:
            self.holder.setText("Встроенный видеоплеер недоступен\n" + WEBENGINE_ERR[:90])

    def available(self) -> bool:
        return self.view is not None

    # ------------------------------------------------------------------ загрузка
    def load(self, vid: str, start: float = 0.0, mode: str = "embed"):
        if not self.view:
            return
        self.vid, self.mode, self._start = vid, mode, start
        self._ready_sent = False
        self._poll.stop()
        self.holder.hide()
        self.view.show()
        self.view.page().setAudioMuted(self.muted)
        if mode == "watch":
            self.view.load(QUrl(f"https://www.youtube.com/watch?v={vid}&t={max(0, int(start))}s"))
            self._poll.start()
        else:
            html = (HTML.replace("__VID__", vid).replace("__START__", str(max(0, int(start))))
                    .replace("__MUTE__", "true" if self.muted else "false")
                    .replace("__VOL__", str(int(self.volume)))
                    .replace("__BOX__", BOX_COVER if self.fill else BOX_CONTAIN))
            self.view.setHtml(html, QUrl("https://localhost/"))

    def stop(self):
        self.vid = None
        if self.view:
            self._poll.stop()
            self.view.setHtml("<html><body style='background:#000'></body></html>")
            self.view.hide()
            self.holder.show()

    # ------------------------------------------------------------------ управление
    def _js(self, code: str):
        if self.view and self.vid:
            self.view.page().runJavaScript(code)

    def _ctl(self, cmd: str, arg=None):
        a = "" if arg is None else f",{arg}"
        if self.mode == "watch":
            self._js(f"window.__mpctl&&window.__mpctl('{cmd}'{a})")
        else:
            self._js(f"ctl('{cmd}'{a})")

    def play(self):
        self._ctl("play")

    def pause(self):
        self._ctl("pause")

    def seek(self, sec: float):
        self._ctl("seek", f"{max(0.0, sec):.2f}")

    def set_muted(self, m: bool):
        self.muted = m
        if self.view:
            self.view.page().setAudioMuted(m)
        self._ctl("mute" if m else "unmute")
        if not m:
            self._ctl("vol", self.volume if self.mode == "embed" else self.volume / 100.0)

    def set_volume(self, v: int):
        """0..100"""
        self.volume = max(0, min(100, int(v)))
        self._ctl("vol", self.volume if self.mode == "embed" else self.volume / 100.0)

    # ------------------------------------------------------------------ режим «страница просмотра»
    def _load_finished(self, ok: bool):
        if self.mode != "watch" or not self.vid:
            return
        if not ok:
            self.failed.emit("net")
            return
        css = WATCH_CSS.replace("__FIT__", "cover" if self.fill else "contain")
        js = (WATCH_JS.replace("__CSS__", json.dumps(css)).replace("__MUTE__", "true" if self.muted else "false")
              .replace("__VOL__", f"{self.volume / 100.0:.2f}"))
        self.view.page().runJavaScript(js)

    def _poll_watch(self):
        if self.mode != "watch" or not self.vid or self._poll_busy:
            return
        self._poll_busy = True

        def cb(res):
            self._poll_busy = False
            if not res or self.mode != "watch":
                return
            try:
                t, st, ad, er, dur = res.split("|")
                if er == "1":
                    self.failed.emit("watch")
                    return
                if ad == "1":
                    self.tick.emit(0.0, 3)
                    return
                if not self._ready_sent:
                    self._ready_sent = True
                    self.ready.emit()
                self.info.emit(float(dur))
                self.tick.emit(float(t), int(st))
            except ValueError:
                pass

        self.view.page().runJavaScript("window.__mpstate&&window.__mpstate()", cb)

    def _title(self, t: str):
        if not t.startswith("mp|"):
            return
        parts = t.split("|")
        kind = parts[1] if len(parts) > 1 else ""
        try:
            if kind == "ready":
                self.ready.emit()
            elif kind == "state":
                self.state.emit(int(parts[2]))
            elif kind == "err":
                code = parts[2]
                if self.mode == "embed" and code in ("101", "150", "153", "5") and self.vid:
                    self.load(self.vid, self._start, "watch")   # владелец запретил встраивание
                else:
                    self.failed.emit(code)
            elif kind == "t":
                self.info.emit(float(parts[4]))
                self.tick.emit(float(parts[2]), int(parts[3]))
        except (ValueError, IndexError):
            pass
