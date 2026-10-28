"""Каталоги: Deezer (обложка, альбом, треклист) и поиск клипов на YouTube."""
import json
import re
from urllib.parse import quote

from .core import get_json, http_get


def norm(s: str | None) -> str:
    s = (s or "").lower().replace("ё", "е")
    return re.sub(r"[^\w]+", " ", s, flags=re.UNICODE).strip()


def _clean_title(t: str) -> str:
    """Убираем хвосты вида (feat. X), - Remastered, [Official]."""
    t = re.sub(r"[\(\[].*?[\)\]]", " ", t or "")
    t = re.sub(r"\s[-–—]\s.*$", " ", t)
    return t.strip()


# ---------------------------------------------------------------- Deezer
def deezer_find(artist: str, title: str) -> dict | None:
    a, t = norm(artist), norm(_clean_title(title) or title)
    if not t:
        return None
    queries = []
    if artist:
        queries.append(f'artist:"{artist}" track:"{_clean_title(title) or title}"')
    queries.append(" ".join(x for x in (a, t) if x))
    for q in queries:
        try:
            d = get_json("https://api.deezer.com/search?limit=15&q=" + quote(q))
        except Exception:
            continue
        items = d.get("data") or []
        best = None
        for x in items:
            xa, xt = norm(x.get("artist", {}).get("name")), norm(x.get("title"))
            if (not a or a in xa or xa in a) and (xt == t or t in xt or xt in t):
                best = x
                break
        if best:
            alb = best.get("album") or {}
            return {
                "title": best.get("title"),
                "artist": best.get("artist", {}).get("name"),
                "album": alb.get("title"),
                "album_id": alb.get("id"),
                "dur": best.get("duration") or 0,
                "cover": alb.get("cover_xl") or alb.get("cover_big") or alb.get("cover_medium"),
            }
    return None


def deezer_artist_pic(artist: str) -> str | None:
    """Фото исполнителя (Deezer)."""
    if not artist:
        return None
    try:
        d = get_json("https://api.deezer.com/search/artist?limit=5&q=" + quote(artist))
    except Exception:
        return None
    items = d.get("data") or []
    a = norm(artist)
    best = next((x for x in items if norm(x.get("name")) == a), items[0] if items else None)
    if not best:
        return None
    return best.get("picture_xl") or best.get("picture_big") or best.get("picture_medium")


def deezer_album_search(artist: str, album: str) -> dict | None:
    a, b = norm(artist), norm(album)
    if not b:
        return None
    for q in (f'artist:"{artist}" album:"{album}"', f"{a} {b}"):
        try:
            d = get_json("https://api.deezer.com/search/album?limit=10&q=" + quote(q))
        except Exception:
            continue
        for x in d.get("data") or []:
            xb = norm(x.get("title"))
            xa = norm(x.get("artist", {}).get("name"))
            if (xb == b or b in xb or xb in b) and (not a or a in xa or xa in a):
                return {"album_id": x.get("id"), "album": x.get("title"),
                        "artist": x.get("artist", {}).get("name"),
                        "cover": x.get("cover_xl") or x.get("cover_big")}
    return None


def deezer_album_tracks(album_id) -> list[dict]:
    d = get_json(f"https://api.deezer.com/album/{album_id}/tracks?limit=100")
    out = []
    for i, x in enumerate(d.get("data") or [], 1):
        out.append({"n": x.get("track_position") or i,
                    "title": x.get("title"),
                    "artist": x.get("artist", {}).get("name"),
                    "dur": x.get("duration") or 0})
    return out


# ---------------------------------------------------------------- YouTube
def _parse_dur(s: str | None) -> int:
    if not s:
        return 0
    try:
        parts = [int(p) for p in s.split(":")]
    except ValueError:
        return 0
    sec = 0
    for p in parts:
        sec = sec * 60 + p
    return sec


def _walk(o, out):
    if isinstance(o, dict):
        vr = o.get("videoRenderer")
        if isinstance(vr, dict):
            out.append(vr)
        for v in o.values():
            _walk(v, out)
    elif isinstance(o, list):
        for v in o:
            _walk(v, out)


def yt_search(query: str, limit: int = 12) -> list[dict]:
    url = ("https://www.youtube.com/results?search_query=" + quote(query)
           + "&sp=EgIQAQ%253D%253D")
    html = http_get(url, timeout=12, headers={
        "Accept-Language": "en-US,en;q=0.9",
        "Cookie": "CONSENT=YES+cb; SOCS=CAI",
    }).decode("utf-8", "replace")
    k = html.find("ytInitialData")
    if k < 0:
        raise RuntimeError("YouTube: не удалось разобрать выдачу")
    start = html.find("{", k)
    data, _ = json.JSONDecoder().raw_decode(html, start)
    rends: list = []
    _walk(data, rends)
    res = []
    seen = set()
    for vr in rends:
        vid = vr.get("videoId")
        if not vid or vid in seen:
            continue
        length = (vr.get("lengthText") or {}).get("simpleText")
        if not length:  # прямые эфиры / премьеры
            continue
        seen.add(vid)
        title = "".join(r.get("text", "") for r in (vr.get("title") or {}).get("runs", []))
        chan = "".join(r.get("text", "") for r in (vr.get("ownerText") or {}).get("runs", []))
        res.append({
            "id": vid, "title": title, "channel": chan,
            "dur_txt": length, "dur": _parse_dur(length),
            "thumb": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
        })
        if len(res) >= limit:
            break
    return res


_BAD = ("lyric", "lyrics", "текст", "karaoke", "караоке", "cover", "кавер", "reaction", "реакция",
        "instrumental", "slowed", "sped up", "nightcore", "8d", "tutorial", "remix", "live",
        "full album", "playlist", "mix", "1 hour", "hours")


def rank_clips(items: list[dict], artist: str, title: str, dur: int = 0) -> list[dict]:
    a, t = norm(artist), norm(_clean_title(title) or title)

    def score(it):
        vt, ch = norm(it["title"]), norm(it["channel"])
        s = 0.0
        if t and t in vt:
            s += 3
        if a and (a in vt or a in ch):
            s += 2
        if "official" in vt or "офици" in vt or "клип" in vt or "video" in vt or "vevo" in ch:
            s += 1.5
        for w in _BAD:
            if w in vt and w not in norm(title):
                s -= 2.5
        if dur and it["dur"]:
            d = abs(it["dur"] - dur)
            s += 2 if d <= 12 else (1 if d <= 40 else (-1 if d > 120 else 0))
        if it["dur"] and it["dur"] > 900:
            s -= 3
        return s

    return sorted(items, key=score, reverse=True)
