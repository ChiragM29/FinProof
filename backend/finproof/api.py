"""FinProof API. Run from backend/:  uvicorn finproof.api:app --port 8000"""

from __future__ import annotations

import datetime as dt
import logging
import os

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import (ai, auditor, cases, config, history, journal, label, meta, net, reply, signalmap, social, study, veteran,
               youtube, profile)
from .card import DISCLAIMER, build_card, wording_problems
from .chart import WATCHLIST, chart_payload, quote
from .ledger import Ledger
from .market import YahooPrices

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="FinProof", description=DISCLAIMER)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_origin_regex=r"chrome-extension://.*",
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

PRICES = YahooPrices()
LEDGER = Ledger(PRICES)


@app.middleware("http")
async def revalidate_static(request: Request, call_next):
    """Dashboard files: browsers must check for a newer version (cheap, uses the ETag)."""
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


class AnalyzeRequest(BaseModel):
    url: str | None = None
    text: str | None = None
    source: str | None = None
    posted_on: dt.date | None = None
    sample: bool = False  # a made-up demo post: post-derived findings are labelled SYNTHETIC


LATEST_SESSION_NOTE = "auto-defaulted to the latest NSE session (no date found in the post)"


def _latest_session() -> dt.date:
    nifty = PRICES.history(config.BENCHMARK)
    return nifty.index[-1].date() if not nifty.empty else dt.date.today()


def _platform(kind: str, *hows: str | None) -> str:
    if kind in social.PLATFORM_NAMES:
        return social.PLATFORM_NAMES[kind]
    said = " ".join(h or "" for h in hows)
    return "WhatsApp" if "WhatsApp" in said else "Telegram" if "Telegram" in said else "Text"


def _detected(card: dict, *, day: dt.date, time: str | None, date_how: str, date_auto: bool,
              source: str | None, source_how: str | None, source_auto: bool) -> dict:
    """What FinProof worked out about the post, shown as pills the user can override."""
    claims = [c for c in card["claims"] if c.get("symbol")]
    fallback_date = date_how == LATEST_SESSION_NOTE
    return {
        "platform": _platform(card["post"]["kind"], date_how, source_how),
        "posted_on": day.isoformat(), "posted_time": time, "date_how": date_how, "date_auto": date_auto,
        "date_origin": "user" if not date_auto else ("fallback" if fallback_date else "extracted"),
        "source": source or meta.UNATTRIBUTED, "source_how": source_how or "no channel or sender found in the post",
        "source_auto": source_auto,
        "source_origin": "user" if not source_auto else ("extracted" if source else "fallback"),
        "tickers": [c["symbol"] for c in claims],
        "renamed": [{"from": c["renamed_from"], "to": c["symbol"]} for c in claims if c.get("renamed_from")],
    }


def _video_card(vid: str, posted_on: dt.date | None = None, extra_text: str | None = None) -> dict:
    try:
        video = youtube.fetch_video(vid)
    except youtube.VideoUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    parts = [video.get("title") or "", video.get("description") or "", extra_text or video.get("transcript") or ""]
    prof = profile.channel_profile(video.get("channel_id"))  # Who is this? (live first, cached copy offline)
    when = youtube.published_ist(video)
    time = None
    if posted_on:
        day, note = posted_on, "date given by the user"
    elif when:
        day, time, note = when[0], when[1], "YouTube publish date"
    elif video.get("published_on"):
        day, note = dt.date.fromisoformat(video["published_on"]), "YouTube publish date"
    else:
        day, note = _latest_session(), LATEST_SESSION_NOTE
    card = build_card(
        text="\n".join(parts), ledger=LEDGER, prices=PRICES, posted_on=day, posted_on_note=note,
        kind="youtube", title=video.get("title"), channel=video.get("channel"),
        source_key=video.get("channel_id") or video.get("channel"),
        link=f"https://www.youtube.com/watch?v={vid}",
        text_parts={"title": video.get("title") or "", "description": video.get("description") or "",
                    "transcript": extra_text or video.get("transcript") or "", "channel page": (prof or {}).get("about") or ""},
    )
    card["profile"] = {
        **({k: prof.get(k) for k in ("channel", "handle", "subscribers", "videos", "url", "fetched_on", "from_cache") if prof.get(k) is not None}
           if prof else {"channel": video.get("channel")}),
        "about_lines": profile.about_lines((prof or {}).get("about")),
        "video_date": day.isoformat(), "video_date_how": note,
        "status": "ok" if prof else "not available", "provenance": config.REAL_LABEL,
    }
    card["description_facts"] = profile.description_facts(video.get("description"))
    card["post"]["transcript"] = "found" if video.get("transcript") else f"not available ({video.get('transcript_error')})"
    card["post"]["from_cache"] = video.get("from_cache", False)
    card["detected"] = _detected(card, day=day, time=time, date_how=note, date_auto=not posted_on,
                                 source=video.get("channel"), source_how="YouTube channel name", source_auto=True)
    card["veteran"] = veteran.build_veteran_brief(card)
    card["label"] = label.build_label(card, "\n".join(parts))
    card["reply"] = reply.build(card)
    return card


@app.get("/terminal", include_in_schema=False)
@app.get("/terminal.html", include_in_schema=False)
def terminal_redirect() -> RedirectResponse:
    """The old terminal now lives inside the Command Center at /."""
    return RedirectResponse(url="/", status_code=307)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "offline": config.OFFLINE, "network": net.status(), "tips_loaded": len(LEDGER.tips),
            "ai": ai.status()}


def _restricted(platform: str, url: str, reason: str | None, message: str = social.RESTRICTED_MESSAGE) -> dict:
    """Not an error: the page shows an inline box to paste the caption, with the platform and link kept."""
    return {"status": "restricted", "platform": platform, "platform_label": social.PLATFORM_NAMES.get(platform, platform),
            "url": url, "reason": reason, "message": message}


def _text_card(text: str, req: AnalyzeRequest, *, kind: str = "text", link: str = "", handle: str | None = None,
               provenance: str | None = None, posted: tuple[dt.date, str | None, str] | None = None,
               author: str | None = None) -> dict:
    """Card for post text: a pasted forward, or a caption from an Instagram/X/YouTube link."""
    known = [tips[0].source_label for tips in LEDGER.sources().values()]
    found = meta.extract(text, known_sources=known)
    if req.posted_on:
        day, time, note = req.posted_on, None, "date given by the user"
    elif found.posted_on:
        day, time, note = found.posted_on, found.posted_time, f"auto-detected from the {found.date_how}"
    elif posted:
        day, time, note = posted
    else:
        day, time, note = _latest_session(), None, LATEST_SESSION_NOTE
    if req.source:
        source, source_how = req.source, "given by the user"
    elif author or handle:
        source = f"{author} (@{handle})" if author and handle else author or f"@{handle}"
        source_how = f"{social.PLATFORM_NAMES.get(kind, kind)} account in the link"
    else:
        source, source_how = found.source, found.source_how
    prov = provenance or (config.SYNTHETIC_LABEL if req.sample else config.REAL_LABEL)
    card = build_card(text=found.body, ledger=LEDGER, prices=PRICES, posted_on=day, posted_on_note=note,
                      kind=kind, channel=source, source_key=handle or source, link=link, post_provenance=prov)
    card["detected"] = _detected(card, day=day, time=time, date_how=note, date_auto=not req.posted_on,
                                 source=source, source_how=source_how, source_auto=not req.source)
    cases.attach(card, PRICES)  # a real SEBI case stock gets its order and computed price facts
    card["veteran"] = veteran.build_veteran_brief(card)
    card["label"] = label.build_label(card, found.body)
    card["reply"] = reply.build(card)
    return card


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest) -> dict:
    """A pasted post, or a YouTube / Instagram / X link (fetched online first, cache as fallback)."""
    link = social.detect(req.url) if req.url else social.detect(req.text)
    caption = req.text if req.text and req.text.strip() and not social.detect(req.text) else None
    if link:
        plat, url = link["platform"], link["url"]
        if plat == "youtube":
            vid = youtube.video_id(url)
            if vid:
                try:
                    return _video_card(vid, req.posted_on, caption)
                except HTTPException as exc:
                    if caption:
                        return _text_card(caption, req, kind="youtube", link=url)
                    return _restricted("youtube", url, str(exc.detail),
                                       "YouTube could not be reached — paste the title or what was said to audit it")
        elif plat == "instagram" and link.get("kind") == "profile" and not caption:
            return _restricted("instagram", url, "profile link",
                               f"This is the Instagram profile @{link['handle']}. Paste the caption of the post you want to check")
        elif plat in ("x", "instagram"):
            if caption:
                return _text_card(caption, req, kind=plat, link=url, handle=link.get("handle"))
            post = social.fetch_post(link)
            if post["status"] != "ok":
                if plat == "instagram":
                    who = f" (@{link['handle']})" if link.get("handle") else ""
                    box = _restricted(plat, url, post.get("reason"), f"Instagram needs a login to read this post{who}; paste the caption")
                    if not config.OFFLINE and social.embed_url(url):  # offline: nothing extra, the text box stays
                        box["embed_url"] = social.embed_url(url)
                    return box
                return _restricted(plat, url, post.get("reason"))
            posted = None
            if post.get("posted_on"):
                posted = (dt.date.fromisoformat(post["posted_on"]), post.get("posted_time"),
                          f"{social.PLATFORM_NAMES[plat]} post date")
            card = _text_card(post["text"], req, kind=plat, link=url, handle=post.get("author_handle"),
                              author=post.get("author"), provenance=post.get("provenance"), posted=posted)
            card["post"]["from_cache"] = post.get("from_cache", False)
            return card
        elif caption:
            return _text_card(caption, req, link=url)
        else:
            return _restricted("web", url, "not a YouTube, Instagram or X link",
                               "FinProof reads YouTube, Instagram and X links — paste the post text to audit it")
    if not caption:
        raise HTTPException(status_code=400, detail="Paste a YouTube, Instagram or X link, or the text of a tip.")
    return _text_card(caption, req)


@app.get("/api/youtube/{vid}")
def youtube_card(vid: str) -> dict:
    vid = youtube.video_id(vid)
    if not vid:
        raise HTTPException(status_code=400, detail="Not a YouTube video id.")
    return _video_card(vid)


@app.get("/api/sources")
def sources() -> list[dict]:
    out = []
    for sid in LEDGER.sources():
        rec, _ = LEDGER.record(sid)
        out.append(rec.__dict__)
    return sorted(out, key=lambda r: r["source_label"])


@app.get("/api/sources/{source_id}")
def source(source_id: str) -> dict:
    if source_id not in LEDGER.sources():
        raise HTTPException(status_code=404, detail="Unknown source.")
    rec, scored = LEDGER.record(source_id)
    return {"record": rec.__dict__, "tips": [s.to_dict() for s in scored], "disclaimer": DISCLAIMER}


# ------------------------------------------------------------------ terminal: chart, auditor, journal

def _valid_symbol(symbol: str) -> bool:
    return len(symbol) <= 24 and symbol.lstrip("^").replace("&", "").replace("-", "").replace(":", "", 1).isalnum()


@app.get("/api/chart/{symbol}")
def chart(symbol: str, levels_before: dt.date | None = None) -> dict:
    """Chart data. `levels_before` (the post date) makes the key levels use only sessions before it."""
    if not _valid_symbol(symbol):
        raise HTTPException(status_code=400, detail="Not an NSE symbol.")
    data = chart_payload(symbol, PRICES, levels_before=levels_before.isoformat() if levels_before else None)
    if data is None:
        raise HTTPException(status_code=404, detail=f"No NSE price data for {symbol.upper()}.")
    return data


@app.get("/api/nifty50")
def nifty50() -> dict:
    """The 50 Nifty 50 companies (NSE's own constituents file, dated) for the search box."""
    rows = history.nifty50()
    return {"companies": rows, "count": len(rows), "as_of": rows[0]["as_of"] if rows else None,
            "provenance": config.REAL_LABEL, "source": "NSE index constituents file (ind_nifty50list.csv)"}


@app.get("/api/price-history")
def price_history(q: str) -> dict:
    """Price History mode for a bare ticker or company name: chart facts only, past prices, no flags."""
    symbol = history.resolve(q)
    card = history.build(symbol, PRICES) if symbol else None
    if card is None:
        raise HTTPException(status_code=404, detail="Not a Nifty 50 ticker or company name with price data.")
    return card


@app.get("/api/signal-map")
def signal_map() -> dict:
    return signalmap.build(LEDGER, PRICES)


@app.get("/api/quotes")
def quotes(symbols: str | None = None) -> list[dict]:
    """Last price and day change for the watchlist (default list when none given)."""
    wanted = [s for s in (symbols.split(",") if symbols else WATCHLIST) if _valid_symbol(s.strip())][:30]
    return [q for q in (quote(s.strip(), PRICES) for s in wanted) if q]


class AuditorRequest(BaseModel):
    question: str
    card: dict | None = None


@app.get("/api/auditor/prompts")
def auditor_prompts() -> list[str]:
    return auditor.QUICK_PROMPTS


class ChatRequest(BaseModel):
    message: str
    card: dict | None = None
    history: list[dict] | None = None


@app.post("/api/chat")
def chat_answer(req: ChatRequest) -> dict:
    """AI answer grounded in the card, or the offline Claim Auditor when AI isn't available."""
    return ai.chat(req.message, req.card, req.history)


@app.post("/api/auditor")
def auditor_answer(req: AuditorRequest) -> dict:
    return auditor.answer(req.question, req.card)


class JournalRequest(BaseModel):
    entries: list[dict]


@app.get("/api/journal/demo-seed")
def journal_seed() -> list[dict]:
    return journal.demo_seed()


@app.post("/api/journal/summary")
def journal_summary(req: JournalRequest) -> dict:
    result = journal.summarize(req.entries, PRICES)
    problems = wording_problems({k: v for k, v in result.items() if k != "rows"})
    if problems:
        raise HTTPException(status_code=500, detail="advice wording in journal summary")
    return result


# ------------------------------------------------------------------ decision test

class StudyStart(BaseModel):
    background: dict[str, str] | None = None


class StudyAnswer(BaseModel):
    participant_id: str
    tip_id: str
    answer: str
    confidence: int
    ms: int = 0


class StudyFinish(BaseModel):
    participant_id: str


def _facilitator(key: str | None) -> None:
    expected = os.environ.get("FINPROOF_STUDY_KEY")
    if expected and key != expected:
        raise HTTPException(status_code=401, detail="Facilitator key needed.")


def _study_call(fn, *args):
    try:
        return fn(*args)
    except study.StudyError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message)


@app.get("/api/study/info")
def study_info(request: Request) -> dict:
    ts = study.current_set(PRICES)
    return {"set": ts.name, "practice": ts.practice, "tips": len(ts.tips), "ready": not ts.problems,
            "problems": ts.problems, "participant_urls": study.lan_urls(request.url.port or 8000),
            "key_required": bool(os.environ.get("FINPROOF_STUDY_KEY"))}


@app.post("/api/study/start")
def study_start(req: StudyStart) -> dict:
    ts = study.current_set(PRICES)
    event = _study_call(study.start_session, ts, req.background)
    return study.plan_payload(event, ts, LEDGER, PRICES)


@app.post("/api/study/answer")
def study_answer(req: StudyAnswer) -> dict:
    ts = study.current_set(PRICES)
    _study_call(study.record_answer, ts, req.participant_id, req.tip_id, req.answer, req.confidence, req.ms)
    return {"ok": True}


@app.post("/api/study/finish")
def study_finish(req: StudyFinish) -> dict:
    _study_call(study.finish_session, study.current_set(PRICES), req.participant_id)
    return {"ok": True}


@app.get("/api/study/results")
def study_results(x_study_key: str | None = Header(default=None)) -> dict:
    _facilitator(x_study_key)
    return study.results(study.current_set(PRICES))


@app.get("/api/study/export.csv")
def study_export(x_study_key: str | None = Header(default=None)) -> Response:
    _facilitator(x_study_key)
    ts = study.current_set(PRICES)
    return Response(content=study.export_csv(ts), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="decision_test_{ts.name}.csv"'})


if config.DASHBOARD.exists():
    app.mount("/", StaticFiles(directory=config.DASHBOARD, html=True), name="dashboard")
