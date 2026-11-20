"""Twitter/X and Instagram links: detect the platform, fetch the public post text, fall back gracefully.

Hybrid, like YouTube: online first (public oEmbed / OpenGraph, 4-second timeout), cached in
data/cache/social, cache when the network is down. Both platforms often login-wall or rate-limit
automated fetches; that is reported as `restricted` (never an error) so the page can ask the user
to paste the caption instead, with the platform and link kept.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import logging
import re
from urllib.parse import quote

import httpx

from . import config, net

log = logging.getLogger(__name__)

SOCIAL_CACHE = config.CACHE / "social"
TIMEOUT = 4.0
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
      "Accept-Language": "en-IN,en;q=0.9"}
RESTRICTED_MESSAGE = "Platform restricted auto-fetch — paste the post caption below to audit immediately"

X_RE = re.compile(r"^https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/([A-Za-z0-9_]{1,15})/status(?:es)?/(\d{1,25})", re.I)
IG_RE = re.compile(r"^https?://(?:www\.)?instagram\.com/(?:([A-Za-z0-9_.]{1,30})/)?(p|reels?|tv)/([A-Za-z0-9_-]{5,40})", re.I)
YT_RE = re.compile(r"^https?://(?:www\.|m\.)?(?:youtube\.com|youtu\.be)/", re.I)
URL_RE = re.compile(r"^https?://\S+$", re.I)
PLATFORM_NAMES = {"x": "X (Twitter)", "instagram": "Instagram", "youtube": "YouTube", "web": "Web link"}

# Two made-up demo posts (SYNTHETIC) so judges can try X and Instagram links with no network.
DEMO_POSTS = {
    "x_1931000000000000001": {
        "platform": "x", "id": "1931000000000000001",
        "url": "https://x.com/SureShotStockIN/status/1931000000000000001",
        "author": "Sure Shot Stocks (demo)", "author_handle": "SureShotStockIN",
        "posted_on": "2025-06-02", "posted_time": "09:15",
        "text": "LEAKED interview: Mukesh Ambani says RELIANCE will be the next multibagger 🚀 Buy before results! "
                "100% accuracy, daily fixed profit. DM for guaranteed calls, free Telegram VIP group, link in bio.",
        "provenance": config.SYNTHETIC_LABEL, "demo": True,
    },
    "instagram_FPdemoReel01": {
        "platform": "instagram", "id": "FPdemoReel01",
        "url": "https://www.instagram.com/reel/FPdemoReel01/",
        "author": "trading.guru.ai (demo)", "author_handle": "trading.guru.ai",
        "posted_on": "2025-06-02", "posted_time": None,
        "text": "RBI approved AI auto-trading bot 🤖 made ₹5 lakh this week. SBIN CMP 790 target 900. "
                "Pay ₹1,999 to trading.guru@ybl to join. Link in bio.",
        "provenance": config.SYNTHETIC_LABEL, "demo": True,
    },
}


def detect(value: str | None) -> dict | None:
    """Which platform a pasted link belongs to. None when the value is not a single link."""
    v = (value or "").strip()
    if not URL_RE.match(v):
        return None
    if m := X_RE.match(v):
        return {"platform": "x", "id": m.group(2), "handle": m.group(1), "url": v}
    if m := IG_RE.match(v):
        return {"platform": "instagram", "id": m.group(3), "handle": m.group(1), "url": v}
    if YT_RE.match(v):
        return {"platform": "youtube", "id": None, "handle": None, "url": v}
    return {"platform": "web", "id": None, "handle": None, "url": v}


def _cache_path(platform: str, pid: str):
    return SOCIAL_CACHE / f"{platform}_{re.sub(r'[^A-Za-z0-9_-]', '_', pid)}.json"


def _strip_tags(raw: str) -> str:
    raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
    return html.unescape(re.sub(r"<[^>]+>", "", raw)).strip()


def _parse_date(text: str) -> str | None:
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return dt.datetime.strptime(text.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


class Restricted(Exception):
    """The platform answered but would not show the post (login wall, private, removed, rate limit)."""


def _get(url: str, **kw) -> httpx.Response:
    return httpx.get(url, headers=UA, timeout=TIMEOUT, follow_redirects=True, **kw)


def _fetch_x(link: dict) -> dict:
    r = _get(f"https://publish.twitter.com/oembed?url={quote(link['url'], safe='')}&omit_script=1&dnt=true")
    if r.status_code != 200:
        raise Restricted(f"oEmbed answered {r.status_code}")
    data = r.json()
    block = data.get("html") or ""
    para = re.search(r"<p[^>]*>(.*?)</p>", block, re.S)
    if not para:
        raise Restricted("no post text in the oEmbed reply")
    dates = re.findall(r"<a [^>]*>([A-Z][a-z]+ \d{1,2}, \d{4})</a>", block)
    handle = re.search(r"twitter\.com/([A-Za-z0-9_]{1,15})", data.get("author_url") or "")
    return {"platform": "x", "id": link["id"], "url": link["url"], "author": data.get("author_name"),
            "author_handle": handle.group(1) if handle else link.get("handle"),
            "posted_on": _parse_date(dates[-1]) if dates else None, "posted_time": None,
            "text": _strip_tags(para.group(1)), "provenance": config.REAL_LABEL}


def _meta(page: str, prop: str) -> str | None:
    m = re.search(rf'<meta[^>]+(?:property|name)="{prop}"[^>]+content="([^"]*)"', page) or \
        re.search(rf'<meta[^>]+content="([^"]*)"[^>]+(?:property|name)="{prop}"', page)
    return html.unescape(m.group(1)) if m else None


def _fetch_instagram(link: dict) -> dict:
    r = _get(link["url"])
    if r.status_code != 200 or "/accounts/login" in str(r.url):
        raise Restricted(f"login wall ({r.status_code})")
    desc = _meta(r.text, "og:description") or _meta(r.text, "description")
    if not desc:
        raise Restricted("no public caption in the page")
    # e.g. '1,234 likes, 56 comments - trading.guru on June 2, 2025: "caption..."'
    m = re.search(r"-\s*([A-Za-z0-9_.]+)\s+on\s+([A-Z][a-z]+ \d{1,2}, \d{4}):\s*\"?(.*?)\"?\s*\.?$", desc, re.S)
    caption = m.group(3) if m else desc
    handle = m.group(1) if m else link.get("handle")
    return {"platform": "instagram", "id": link["id"], "url": link["url"], "author": _meta(r.text, "og:title") or handle,
            "author_handle": handle, "posted_on": _parse_date(m.group(2)) if m else None, "posted_time": None,
            "text": caption.strip(), "provenance": config.REAL_LABEL}


FETCHERS = {"x": _fetch_x, "instagram": _fetch_instagram}


def fetch_post(link: dict, offline: bool | None = None) -> dict:
    """{"status": "ok", ...post} or {"status": "restricted", "reason": ...}. Never raises for network trouble."""
    offline = config.OFFLINE if offline is None else offline
    key = f"{link['platform']}_{link['id']}"
    path = _cache_path(link["platform"], link["id"])
    cached = json.loads(path.read_text(encoding="utf-8")) if path.exists() else DEMO_POSTS.get(key)
    if cached and cached.get("demo"):  # made-up demo posts never need the network
        return {**cached, "status": "ok", "from_cache": True}
    reason = "offline: the post is not cached" if offline else None
    if not offline and net.online():
        try:
            post = FETCHERS[link["platform"]](link)
        except Restricted as exc:
            reason = str(exc)
        except (httpx.HTTPError, ValueError) as exc:  # timeout, DNS, bad JSON ...
            reason = f"could not reach {PLATFORM_NAMES[link['platform']]} ({type(exc).__name__})"
            if isinstance(exc, httpx.TransportError):
                net.mark_offline()
        else:
            SOCIAL_CACHE.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(post, ensure_ascii=False, indent=1), encoding="utf-8")
            return {**post, "status": "ok", "from_cache": False}
    elif not offline:
        reason = "no network"
    if cached:
        return {**cached, "status": "ok", "from_cache": True}
    return {"status": "restricted", "platform": link["platform"], "url": link["url"], "reason": reason,
            "message": RESTRICTED_MESSAGE}


def write_demo_cache() -> list[str]:
    """Used by scripts/warm_cache.py: put the two SYNTHETIC demo posts in the social cache."""
    SOCIAL_CACHE.mkdir(parents=True, exist_ok=True)
    out = []
    for key, post in DEMO_POSTS.items():
        path = _cache_path(post["platform"], post["id"])
        path.write_text(json.dumps(post, ensure_ascii=False, indent=1), encoding="utf-8")
        out.append(post["url"])
    return out
