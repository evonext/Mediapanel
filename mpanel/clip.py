"""Плеер клипов: встроенный YouTube-плеер (QtWebEngine), всегда без звука."""
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

HTML = """<!doctype html><html><head><meta charset="utf-8">
<style>html,body{margin:0;height:100%;background:#000;overflow:hidden}
#p{position:absolute;left:0;top:0;width:100%;height:100%;border:0;pointer-events:none}</style></head>
<body><div id="p"></div><script>
var n=0;function rep(s){document.title='mp|'+s+'|'+(n++);}
var player=null,ready=false;
var tag=document.createElement('script');tag.src='https://www.youtube.com/iframe_api';
tag.onerror=function(){rep('err|net');};document.head.appendChild(tag);
function onYouTubeIframeAPIReady(){
 player=new YT.Player('p',{width:'100%',height:'100%',videoId:'__VID__',
  playerVars:{autoplay:1,mute:1,controls:0,disablekb:1,fs:0,rel:0,modestbranding:1,playsinline:1,
              iv_load_policy:3,cc_load_policy:0,start:__START__},
  events:{
   onReady:function(e){ready=true;e.target.mute();e.target.playVideo();rep('ready');},
   onStateChange:function(e){rep('state|'+e.data);},
   onError:function(e){rep('err|'+e.data);}
  }});
}
setInterval(function(){if(ready){try{rep('t|'+player.getCurrentTime().toFixed(2)+'|'+player.getPlayerState());}catch(x){}}},1000);
function ctl(c,a){if(!ready)return;try{
 if(c=='play')player.playVideo();else if(c=='pause')player.pauseVideo();
 else if(c=='seek')player.seekTo(a,true);else if(c=='mute')player.mute();}catch(x){}}
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
    "object-fit:contain!important}"
    ".ytp-chrome-bottom,.ytp-chrome-top,.ytp-gradient-top,.ytp-gradient-bottom,.ytp-ce-element,"
    ".ytp-pause-overlay,.ytp-endscreen-content,.ytp-cards-teaser,.ytp-paid-content-overlay,"
    ".ytp-watermark,.ytp-spinner,.ytp-iv-video-content,.annotation,.ytp-popup,.ytp-contextmenu,"
    ".ytp-ad-overlay-container,.ytp-ad-text-overlay,.ytp-large-play-button{display:none!important}"
)

WATCH_JS = """(function(){
 if(window.__mp){return;} window.__mp=1;
 var st=document.createElement('style');st.textContent=%s;document.documentElement.appendChild(st);
 function pv(){return document.querySelector('#movie_player video')||document.querySelector('video');}
 setInterval(function(){try{
   var v=pv(); if(v){v.muted=true;v.volume=0;}
   var sk=document.querySelector('.ytp-skip-ad-button,.ytp-ad-skip-button,.ytp-ad-skip-button-modern,.ytp-ad-skip-button-container button');
   if(sk){sk.click();}
 }catch(e){}},400);
 window.__mpstate=function(){var v=pv(); if(!v){return '';}
   var ad=document.querySelector('.ad-showing')?1:0; var er=document.querySelector('.ytp-error')?1:0;
   return v.currentTime.toFixed(2)+'|'+(v.ended?0:(v.paused?2:1))+'|'+ad+'|'+er;};
 window.__mpctl=function(c,a){var v=pv(); if(!v){return;} if(document.querySelector('.ad-showing')&&c=='seek'){return;}
   if(c=='play'){var p=v.play(); if(p&&p.catch){p.catch(function(){});}} else if(c=='pause'){v.pause();}
   else if(c=='seek'){v.currentTime=a;}};
})();"""


class ClipPlayer(QWidget):
    ready = Signal()
    failed = Signal(str)          # код ошибки YouTube или 'net'
    tick = Signal(float, int)     # текущее время клипа, состояние плеера YT
    state = Signal(int)

    def __init__(self):
        super().__init__()
        self.vid = None
        self.view = None
        self.mode = "embed"          # embed | watch
        self._start = 0.0
        self._ready_sent = False
        self._poll_busy = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.holder = QLabel()
        self.holder.setAlignment(Qt.AlignCenter)
        self.holder.setStyleSheet(f"background:#000;color:{T.MUTED};border:1px solid {T.LINE2};"
                                  f"border-radius:4px;font-size:12px;")
        lay.addWidget(self.holder)
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
            self.holder.setText("КЛИП\nНайди трек или включи музыку")
        else:
            self.holder.setText("Встроенный видеоплеер недоступен\n" + WEBENGINE_ERR[:90])

    def available(self) -> bool:
        return self.view is not None

    def load(self, vid: str, start: float = 0.0, mode: str = "embed"):
        if not self.view:
            return
        self.vid, self.mode, self._start = vid, mode, start
        self._ready_sent = False
        self._poll.stop()
        self.holder.hide()
        self.view.show()
        self.view.page().setAudioMuted(True)
        if mode == "watch":
            url = f"https://www.youtube.com/watch?v={vid}&t={max(0, int(start))}s"
            self.view.load(QUrl(url))
            self._poll.start()
        else:
            html = HTML.replace("__VID__", vid).replace("__START__", str(max(0, int(start))))
            self.view.setHtml(html, QUrl("https://localhost/"))

    def stop(self):
        self.vid = None
        if self.view:
            self._poll.stop()
            self.view.setHtml("<html><body style='background:#000'></body></html>")
            self.view.hide()
            self.holder.show()

    def _js(self, code: str):
        if self.view and self.vid:
            self.view.page().runJavaScript(code)

    def play(self):
        self._js("window.__mpctl&&window.__mpctl('play')" if self.mode == "watch" else "ctl('play')")

    def pause(self):
        self._js("window.__mpctl&&window.__mpctl('pause')" if self.mode == "watch" else "ctl('pause')")

    def seek(self, sec: float):
        sec = max(0.0, sec)
        self._js(f"window.__mpctl&&window.__mpctl('seek',{sec:.2f})" if self.mode == "watch"
                 else f"ctl('seek',{sec:.2f})")

    # --- режим «страница просмотра»: работает и для роликов, которые нельзя встроить
    def _load_finished(self, ok: bool):
        if self.mode != "watch" or not self.vid:
            return
        if not ok:
            self.failed.emit("net")
            return
        import json
        self.view.page().runJavaScript(WATCH_JS % json.dumps(WATCH_CSS))

    def _poll_watch(self):
        if self.mode != "watch" or not self.vid or self._poll_busy:
            return
        self._poll_busy = True

        def cb(res):
            self._poll_busy = False
            if not res or self.mode != "watch":
                return
            try:
                t, st, ad, er = res.split("|")
                if er == "1":
                    self.failed.emit("watch")
                    return
                if ad == "1":
                    self.tick.emit(0.0, 3)
                    return
                if not self._ready_sent:
                    self._ready_sent = True
                    self.ready.emit()
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
                self.tick.emit(float(parts[2]), int(parts[3]))
        except (ValueError, IndexError):
            pass
