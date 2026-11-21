"""Who is this? A YouTube channel's public profile, and facts from a video's description.

Read from the channel's public page (no API key, no login), live first and cached for offline use. Values YouTube does
not return are left out, never guessed. Everything here is REAL data from YouTube; the description text is the
channel's own words and is shown as quoted source text.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re

import httpx

from . import config, net

log = logging.getLogger(__name__)

CH_CACHE = config.CACHE / "youtube" / "channels"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept-Language": "en-IN,en;q=0.9"}
TIMEOUT = 8
STR = r'((?:[^"\\]|\\.)*)'


def _unjson(raw: str) -> str:
    try:
        return json.loads(f'"{raw}"').replace("\xa0", " ").strip()
    except ValueError:
        return raw.replace("\xa0", " ").strip()


def parse_channel_page(page: str, channel_id: str | None = None) -> dict:
    """The profile fields found in a YouTube channel page (any that are missing are left out)."""
    def grab(*patterns: str) -> str | None:
        for p in patterns:
            m = re.search(p, page)
            if m:
                return _unjson(m.group(1))
        return None

    cid = channel_id or grab(r'"channelId":"(UC[A-Za-z0-9_-]{22})"', r'"externalId":"(UC[A-Za-z0-9_-]{22})"')
    handle = grab(r'"canonicalBaseUrl":"/(@[^"/]+)"', r'"vanityChannelUrl":"https?://www\.youtube\.com/(@[^"/]+)"')
    out = {
        "channel_id": cid,
        "channel": grab(r'"channelMetadataRenderer":\{"title":"' + STR + '"'),
        "handle": handle,
        "subscribers": grab(r'"subscriberCountText":"([^"]+)"', r'"content":"([^"]*subscribers?)"',
                            r'"subscriberCountText":\{"simpleText":"([^"]+)"'),
        "videos": grab(r'"videoCountText":"([^"]+)"', r'"content":"([^"]*videos?)"'),
        "about": grab(r'"channelMetadataRenderer":\{"title":"(?:[^"\\]|\\.)*","description":"' + STR + '"'),
        "url": f"https://www.youtube.com/{handle}" if handle else (f"https://www.youtube.com/channel/{cid}" if cid else None),
    }
    return {k: v for k, v in out.items() if v}


def about_lines(about: str | None, n: int = 2) -> list[str]:
    return [line.strip() for line in (about or "").splitlines() if line.strip()][:n]


def _fetch_live(channel_id: str) -> dict:
    r = httpx.get(f"https://www.youtube.com/channel/{channel_id}/about", headers=UA, timeout=TIMEOUT, follow_redirects=True)
    r.raise_for_status()
    return parse_channel_page(r.text, channel_id)


def channel_profile(channel_id: str | None, offline: bool | None = None) -> dict | None:
    """Hybrid: live when online (refreshing the cache), else the cached copy. None if neither is available."""
    if not channel_id:
        return None
    offline = config.OFFLINE if offline is None else offline
    path = CH_CACHE / f"{channel_id}.json"
    cached = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    if not offline and net.online():
        try:
            data = _fetch_live(channel_id)
        except Exception as exc:  # blocked, timed out, no network: fall back to the cache
            log.warning("live channel fetch failed for %s: %s", channel_id, exc)
            if isinstance(exc, httpx.TransportError):
                net.mark_offline()
        else:
            if data.get("channel"):
                data["fetched_on"] = dt.date.today().isoformat()
                CH_CACHE.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
                return {**data, "from_cache": False, "provenance": config.REAL_LABEL}
    if cached:
        return {**cached, "from_cache": True, "provenance": config.REAL_LABEL}
    return None


# ------------------------------------------------------------------ facts from a description (facts only)
GROUP_RE = re.compile(r"(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me|telegram\.dog|chat\.whatsapp\.com|wa\.me|whatsapp\.com/channel)"
                      r"/[\w+/-]+", re.I)
URL_IN_RE = re.compile(r"https?://\S+", re.I)
PAID_WORDS_RE = re.compile(r"\b(course|courses|premium|membership|mentorship|paid|webinar|masterclass|subscription|"
                           r"advisory|batch|enrol|enroll|join now|fees?)\b", re.I)
PAID_HOSTS_RE = re.compile(r"(graphy\.com|cosmofeed|tagmango|exlyapp|exly\.co|instamojo|rzp\.io|razorpay\.me|pages\.razorpay|"
                           r"kajabi|teachable|learnyst|classplus|myinstamojo|superprofile|topmate|youtube\.com/channel/[\w-]+/join)", re.I)
DISCLAIMER_RE = re.compile(r"disclaimer|not\s+(?:a\s+)?sebi[\s-]*regist\w*|for\s+educational\s+purposes?|educational\s+purposes?\s+only|"
                           r"not\s+(?:a\s+)?(?:financial|investment)\s+advice|do\s+your\s+own\s+research|consult\s+(?:your|a)\s+\w*\s*advis",
                           re.I)


def description_facts(description: str | None) -> dict:
    text = description or ""
    groups = sorted({m.group(0).rstrip(".,)") for m in GROUP_RE.finditer(text)})
    paid = []
    for line in text.splitlines():
        for url in URL_IN_RE.findall(line):
            url = url.rstrip(".,)")
            if url not in groups and (PAID_HOSTS_RE.search(url) or PAID_WORDS_RE.search(line)) and url not in paid:
                paid.append(url)
    disc = next((line.strip()[:140] for line in text.splitlines() if DISCLAIMER_RE.search(line)), None)
    return {"group_links": groups[:5], "paid_links": paid[:5], "disclaimer": disc, "checked": bool(text.strip()),
            "provenance": config.REAL_LABEL}
