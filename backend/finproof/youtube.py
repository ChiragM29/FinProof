"""Fetch a YouTube video's title, channel, publish date, description and transcript.

Everything fetched is cached in data/cache/youtube, so a rehearsed demo replays
without the network.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

import httpx

from . import config, net

log = logging.getLogger(__name__)

YT_CACHE = config.CACHE / "youtube"
ID_RE = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([A-Za-z0-9_-]{11})")
BARE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
LANGS = ["en", "en-IN", "en-US", "hi", "kn", "ta", "te", "mr", "gu", "bn"]
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept-Language": "en-IN,en;q=0.9"}


class VideoUnavailable(Exception):
    pass


def video_id(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    m = ID_RE.search(value)
    if m:
        return m.group(1)
    return value if BARE_ID_RE.match(value) else None


def _json_string(raw: str) -> str:
    try:
        return json.loads(f'"{raw}"')
    except json.JSONDecodeError:
        return raw


def _page_meta(vid: str) -> dict:
    r = httpx.get(f"https://www.youtube.com/watch?v={vid}", headers=UA, timeout=LIVE_TIMEOUT, follow_redirects=True)
    r.raise_for_status()
    page = r.text

    def grab(pattern: str) -> str | None:
        m = re.search(pattern, page)
        return _json_string(m.group(1)) if m else None

    published = grab(r'"publishDate":"([^"]+)"') or grab(r'itemprop="datePublished" content="([^"]+)"') \
        or grab(r'"uploadDate":"([^"]+)"')
    return {
        "title": grab(r'"title":"((?:[^"\\]|\\.)*)","lengthSeconds"') or grab(r'<meta name="title" content="([^"]*)"'),
        "channel": grab(r'"ownerChannelName":"((?:[^"\\]|\\.)*)"') or grab(r'"author":"((?:[^"\\]|\\.)*)"'),
        "channel_id": grab(r'"channelId":"(UC[A-Za-z0-9_-]{22})"'),
        "published_on": published[:10] if published else None,
        "published_at": published,
        "description": grab(r'"shortDescription":"((?:[^"\\]|\\.)*)"') or "",
    }


def _transcript(vid: str) -> tuple[str | None, str | None, str | None]:
    """(text, language, error)."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        api = YouTubeTranscriptApi()
        try:
            fetched = api.fetch(vid, languages=LANGS)
        except Exception:
            listing = api.list(vid)
            fetched = next(iter(listing)).fetch()
        text = " ".join(s.text.replace("\n", " ") for s in fetched.snippets)
        return text, fetched.language_code, None
    except Exception as exc:  # no captions, blocked, private video ...
        return None, None, f"{type(exc).__name__}"


IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def published_ist(video: dict) -> tuple[dt.date, str] | None:
    """Publish date and time in Indian time, when YouTube gave a full timestamp."""
    raw = video.get("published_at") or ""
    if "T" not in raw:
        return None
    try:
        when = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is None:
        return None
    local = when.astimezone(IST)
    return local.date(), local.strftime("%H:%M")


LIVE_TIMEOUT = 8  # seconds for each live call (video page, transcript)


def _fetch_live(vid: str) -> dict:
    """Title, channel, publish time, description and transcript, straight from YouTube."""
    meta = _page_meta(vid)
    pool = ThreadPoolExecutor(max_workers=1)
    try:  # the transcript library has no timeout of its own
        text, lang, err = pool.submit(_transcript, vid).result(timeout=LIVE_TIMEOUT)
    except FutureTimeout:
        text, lang, err = None, None, "Timeout"
    finally:
        pool.shutdown(wait=False)
    return {"video_id": vid, **meta, "transcript": text, "transcript_language": lang, "transcript_error": err}


def fetch_video(vid: str, offline: bool | None = None) -> dict:
    """Hybrid: fetch live when the network is there (and refresh the cache), else use the cached copy.
    FINPROOF_OFFLINE=1 (or offline=True) means cache only."""
    offline = config.OFFLINE if offline is None else offline
    path = YT_CACHE / f"{vid}.json"
    cached = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    if not offline and net.online():
        try:
            data = _fetch_live(vid)
        except Exception as exc:  # blocked, timed out, no network: fall back to the cache
            log.warning("live YouTube fetch failed for %s: %s", vid, exc)
            if isinstance(exc, httpx.TransportError):
                net.mark_offline()
            if cached is None:
                raise VideoUnavailable(f"could not reach YouTube ({type(exc).__name__}) and the video is not cached") from exc
        else:
            if cached and not data.get("transcript") and cached.get("transcript"):
                data.update({k: cached.get(k) for k in ("transcript", "transcript_language", "transcript_error")})
            YT_CACHE.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            return {**data, "from_cache": False}
    if cached is None:
        raise VideoUnavailable("no network and this video is not cached")
    return {**cached, "from_cache": True}
