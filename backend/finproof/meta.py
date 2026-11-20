"""Work out when a pasted post was made and who posted it, so nobody has to type it in.

Reads WhatsApp chat-export headers, Telegram forward/copy headers, @handles, known source
names and dates written inside the post. Indian day/month order is assumed (14/03/2025 is
14 March). Every result says how it was found, and the user can still override it.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import asdict, dataclass

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
TIME = r"(\d{1,2})[:.](\d{2})(?:[:.]\d{2})?\s*([ap]\.?\s?m\.?)?"
UNATTRIBUTED = "Unattributed Forward"

# [14/03/2025, 9:42 am] Name: message          (WhatsApp, iPhone export)
WA_IOS = re.compile(r"^\s*\[(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4}),?\s+" + TIME + r"\]\s*([^:\n]{1,60}?):\s?", re.I | re.M)
# 14/03/25, 2:15 PM - Name: message            (WhatsApp, Android export)
WA_ANDROID = re.compile(r"^\s*(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4}),?\s+" + TIME + r"\s*[-–]\s*([^:\n]{1,60}?):\s?", re.I | re.M)
# Forwarded from Channel Name / Forwarded from @handle
TG_FORWARD = re.compile(r"^\s*forwarded from[:\s]+([^\n\[\]]{2,60}?)\s*$", re.I | re.M)
# Channel Name, [24.03.2025 09:42]              (Telegram Desktop copy)
TG_COPY = re.compile(r"^\s*([^\n,\[\]]{2,60}),\s*\[(\d{1,2})\.(\d{1,2})\.(\d{2,4})\s+" + TIME + r"\]\s*$", re.I | re.M)
HANDLE = re.compile(r"(?<![\w.@])@([A-Za-z][A-Za-z0-9_]{3,31})\b")

ISO_DATE = re.compile(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})(?:[ T]" + TIME + r")?", re.I)
NUM_DATE = re.compile(r"(?<![\d/.-])(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})(?![\d/.-])(?:,?\s+" + TIME + r")?", re.I)
D_MON_Y = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+" + MON + r",?\s+(\d{4})(?:,?\s+(?:at\s+)?" + TIME + r")?", re.I)
MON_D_Y = re.compile(r"\b" + MON + r"\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})(?:,?\s+(?:at\s+)?" + TIME + r")?", re.I)
RELATIVE = re.compile(r"\b(today|yesterday|aaj)\b", re.I)


@dataclass
class PostMeta:
    posted_on: dt.date | None = None
    posted_time: str | None = None   # "09:42" (as written in the post, Indian time)
    date_how: str | None = None
    source: str | None = None
    source_how: str | None = None
    body: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["posted_on"] = self.posted_on.isoformat() if self.posted_on else None
        return d


def _year(y: str) -> int:
    n = int(y)
    return 2000 + n if n < 100 else n


def _date(y, m, d, today: dt.date) -> dt.date | None:
    try:
        day = dt.date(_year(str(y)), int(m), int(d))
    except ValueError:
        return None
    return day if dt.date(2005, 1, 1) <= day <= today else None


def _time(hh, mm, ampm) -> str | None:
    if hh is None or mm is None:
        return None
    h, m = int(hh), int(mm)
    if ampm:
        pm = ampm.lower().replace(".", "").replace(" ", "") == "pm"
        h = (h % 12) + (12 if pm else 0)
    return f"{h:02d}:{m:02d}" if 0 <= h < 24 and 0 <= m < 60 else None


def _clean_name(name: str) -> str | None:
    name = re.sub(r"\s+", " ", name).strip(" -–:·|")
    return name if 2 <= len(name) <= 60 and not re.fullmatch(r"[\d\s+()-]+", name) else name or None


def extract(text: str, known_sources: list[str] | None = None, today: dt.date | None = None) -> PostMeta:
    today = today or dt.date.today()
    text = text or ""
    meta = PostMeta()
    body = text

    # 1. Chat headers: date, time and sender together.
    for rx, how in ((WA_IOS, "WhatsApp message header"), (WA_ANDROID, "WhatsApp message header")):
        m = rx.search(text)
        if m:
            day = _date(m.group(3), m.group(2), m.group(1), today)
            if day:
                meta.posted_on, meta.date_how = day, how
                meta.posted_time = _time(m.group(4), m.group(5), m.group(6))
            meta.source, meta.source_how = _clean_name(m.group(7)), "WhatsApp sender name"
            body = rx.sub("", body)
            break
    m = TG_COPY.search(text)
    if m:
        day = _date(m.group(4), m.group(3), m.group(2), today)
        if day and not meta.posted_on:
            meta.posted_on, meta.date_how = day, "Telegram message header"
            meta.posted_time = _time(m.group(5), m.group(6), m.group(7))
        if not meta.source:
            meta.source, meta.source_how = _clean_name(m.group(1)), "Telegram channel name"
        body = TG_COPY.sub("", body)
    m = TG_FORWARD.search(text)
    if m:
        meta.source, meta.source_how = _clean_name(m.group(1)), "Telegram \"Forwarded from\" line"
        body = TG_FORWARD.sub("", body)

    # 2. Who: an @handle or a source FinProof already tracks.
    if not meta.source:
        for name in sorted(known_sources or [], key=len, reverse=True):
            if name and name.lower() in text.lower():
                meta.source, meta.source_how = name, "matched a source in the FinProof ledger"
                break
    if not meta.source:
        h = HANDLE.search(text)
        if h:
            meta.source, meta.source_how = "@" + h.group(1), "@handle in the post"

    # 3. When: the first full date written in the post (not in the future).
    if not meta.posted_on:
        found = []
        for rx, order in ((ISO_DATE, "ymd"), (D_MON_Y, "dMy"), (MON_D_Y, "Mdy"), (NUM_DATE, "dmy")):
            for m in rx.finditer(body):
                g = m.groups()
                if order == "ymd":
                    day, tm = _date(g[0], g[1], g[2], today), _time(g[3], g[4], g[5])
                elif order == "dMy":
                    day, tm = _date(g[2], MONTHS[g[1][:3].lower()], g[0], today), _time(g[3], g[4], g[5])
                elif order == "Mdy":
                    day, tm = _date(g[2], MONTHS[g[0][:3].lower()], g[1], today), _time(g[3], g[4], g[5])
                else:
                    day, tm = _date(g[2], g[1], g[0], today), _time(g[3], g[4], g[5])
                if day:
                    found.append((m.start(), day, tm))
        if found:
            _, meta.posted_on, meta.posted_time = min(found)
            meta.date_how = "date written in the post"
    if not meta.posted_on:
        r = RELATIVE.search(body)
        if r:
            word = r.group(1).lower()
            meta.posted_on = today - dt.timedelta(days=1) if word == "yesterday" else today
            meta.date_how = f"the word \"{word}\" in the post"

    meta.body = "\n".join(line for line in body.splitlines() if line.strip()).strip() or text.strip()
    return meta


extract_metadata = extract  # the name used in the project brief
