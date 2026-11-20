"""The Veteran's Desk Note: the card's facts explained the way a calm, seasoned market mentor
would explain them to a first-time investor.

Deterministic and offline: every sentence is built from fields of the card, so it cannot invent
numbers, and it is checked against the same no-advice rules as the card (plus a few stricter
words). It critiques the information and the process, never the stock.
"""

from __future__ import annotations

import re

from . import media
from .card import ADVICE_RE

DISCLAIMER = "Educational decision-process guide based on observed data — never investment advice."
VOICE = "Mentor voice, built from this scan."
# Stricter than the card guard: the mentor never talks about investing or rates a stock at all.
EXTRA_RE = re.compile(r"\b(invest|invests|investing|investments?|bad stocks?|good stocks?|avoid (?:this|the) stock|"
                      r"will (?:rise|fall|go up|go down)|sure to)\b", re.I)


REAL, SYNTHETIC = "REAL", "SYNTHETIC"
CONTEXT_NOTE = "Past prices only, not a forecast."
# The Desk leads with volume and the after-post result; RSI and MACD appear only in Raw Forensic Signals.
CONTEXT_CODES = ("vwap20", "atr14", "levels")
MARKET_CODES = {"volume_spike", "thin_trading", "run_up", "fell_after", "be_segment", "bz_segment"}
# Display names for the raw view (the codes stay in the data for tests and tools).
FLAG_LABELS = {
    "guarantee": "Promise of certain profit", "urgency": "Artificial urgency", "big_promise": "Big-number promise",
    "insider": "Insider-news claim", "paid_group": "Paid VIP group", "personal_upi": "Personal UPI handle",
    "percent_promise": "Large promised return", "education_loophole": "\"Educational only\" loophole",
    "not_on_sebi_list": "Not on SEBI's list", "unverified_sebi_claim": "Unconfirmed SEBI claim",
    "be_segment": "BE series (trade-for-trade)", "bz_segment": "BZ series", "volume_spike": "Pre-post volume spike",
    "thin_trading": "Thin trading", "run_up": "Run-up before the post", "fell_after": "Sharp fall after the post",
    "impersonation": "Impersonation cue", "funnel": "Scam funnel", "missing_context": "Missing context",
}
TECH_LABELS = {"sma20": "Price vs SMA 20", "vwap20": "Price vs VWAP (20D)", "ema50": "Price vs EMA 50",
               "rsi14": "RSI (14)", "macd": "MACD (12, 26, 9)", "bollinger": "Bollinger (20, 2)",
               "atr14": "ATR (14) daily swing", "levels": "Key levels"}


def flag_label(code: str) -> str:
    return FLAG_LABELS.get(code, code.replace("_", " ").capitalize())


def _pct(x: float) -> str:
    v = round(float(x) * 100, 1)  # plain float: numpy rounds halves differently
    return f"{v:+.1f}%" if v else "0.0%"


def _pts(x: float) -> str:
    v = round(float(x) * 100, 1)  # plain float: numpy rounds halves differently
    return f"{v:+.1f} points" if v else "0.0 points"


def _wrong_item(w: dict, card: dict) -> dict | None:
    code, sym = w["code"], w.get("symbol")
    claim = next((c for c in card.get("claims", []) if c.get("symbol") == sym), None) if sym else None
    m = (claim or {}).get("market") or {}
    ev = list(w.get("evidence") or [])
    texts = {
        "guarantee": ("A promise of certain profit",
                      "Markets don't make promises; people with something to push do. When a message takes risk out of the "
                      "conversation, it is usually to stop you asking questions."),
        "urgency": ("Artificial urgency",
                    "Real wealth isn't built against a countdown. A deadline is there to get your decision made before "
                    "your checking starts."),
        "big_promise": ("Big-number promises",
                        "Lines like these offer a feeling, not a fact. A serious analyst shows the reasoning and the risks, "
                        "not just the size of the prize."),
        "insider": ("Talk of secret or insider news",
                    "Real price-sensitive news reaches everyone through stock exchange filings at the same time. A tip "
                    "that claims secret knowledge asks you to trust something you cannot check."),
        "paid_group": ("A paid group or VIP calls",
                       "Paying for calls before seeing a full record of past calls, the misses as well as the wins, puts "
                       "both the cost and the risk on you."),
        "personal_upi": ("Payment to a personal UPI ID",
                         "Since 1 October 2025, SEBI-registered intermediaries collect money through validated '@valid' "
                         "UPI handles. A personal ID leaves you no way to make the receiver accountable."),
        "percent_promise": ("A large promised return",
                            "A big percentage with no risk attached is a sales line. Experienced people talk about what "
                            "could go wrong before what could go right."),
        "education_loophole": ("An 'educational' label on a live stock call",
                               "Real education teaches a method. It does not hand you a stock name with price levels to "
                               "act on today. When the label and the content disagree, believe the content."),
        "not_on_sebi_list": ("No SEBI registration found",
                             "Registration tells you who is accountable if things go wrong. Without it, nobody is."),
        "unverified_sebi_claim": ("A registration claim that could not be confirmed",
                                  "Anyone can type 'SEBI registered'. The registration number and SEBI's own list are "
                                  "what count."),
        "be_segment": ("A stock under closer exchange watch",
                       f"NSE trades {sym} trade-for-trade, a series it uses for stocks it watches more closely."),
        "bz_segment": ("A company that has not met listing rules",
                       f"NSE has placed {sym} in its BZ series, used for companies that have not met listing rules."),
        "impersonation": ("A famous name used as bait",
                          "Scam clips borrow well-known faces, regulators or 'AI bot' stories. Real news appears on the "
                          "company's or regulator's own site first. FinProof flags the cue; it cannot verify the clip."),
        "funnel": ("A push to a private channel",
                   "'Link in bio', DMs and free VIP groups move you away from public view, where nobody else can "
                   "check the claims."),
        "missing_context": ("A stock call with no context",
                            "A clip that names a price, with no registration number and no word about risk, gives "
                            "you nothing to check."),
    }
    if code in texts:
        title, text = texts[code]
    elif code == "volume_spike" and m.get("spike_ratio"):
        title = f"Unusual trading before the message ({m['spike_ratio']:.1f}× the 20-day average)"
        text = (f"Trading in {sym} jumped on {m.get('spike_date')}, before this post reached you. Sometimes that is "
                "ordinary news or one large trade, but it also means others were active before the message went out. "
                "By the time a tip goes viral, the early movers have usually had their turn.")
    elif code == "thin_trading" and m.get("avg_traded_value_20d") is not None:
        title = f"A thinly traded stock (about ₹{m['avg_traded_value_20d'] / 1e7:,.2f} crore a day)"
        text = "In a stock this quiet, a small group of traders can move the price. Hype works best where trading is thin."
    elif code == "run_up" and m.get("run_up_20d") is not None:
        title = f"The move came before the message ({_pct(m['run_up_20d'])} in 20 sessions)"
        text = ("When a stock has already run up before you hear about it, the tip is arriving late. Beginners who chase "
                "a run-up often arrive just as the early traders are cashing in.")
    elif code == "fell_after" and m.get("fall_after") is not None:
        title = f"A sharp fall after the post ({_pct(m['fall_after'])} within 30 sessions)"
        text = "This is the classic shape of hype: a burst of attention, then the price gives the gains back."
    else:
        title, text = w["text"], ""
    return {"code": code, "title": title, "text": text, "evidence": ev}


def build_veteran_brief(card: dict) -> dict:
    """What is wrong in this post, what an experienced person does instead, and the raw numbers behind both."""
    claim = next((c for c in card.get("claims", []) if not c.get("ambiguous") and c.get("symbol")), None)
    sym = claim["symbol"] if claim else None
    warnings = card.get("warnings", [])
    detected = card.get("detected") or {}
    tr = card.get("track_record") or {}

    wrong = [w for w in (_wrong_item(w, card) for w in warnings) if w]
    tech = (claim or {}).get("technicals") or {}
    context = []
    mk0 = (claim or {}).get("market") or {}
    if mk0.get("spike_ratio") is not None:
        context.append({"code": "volume", "text": f"Volume: the busiest of the 3 sessions before the post was "
                                                  f"{mk0['spike_ratio']:.1f}× its 20-day average ({mk0.get('spike_date')})."})
    after0 = ((claim or {}).get("after_post") or {}).get("horizons", {}).get("30") or {}
    if after0.get("status") == "scored":
        context.append({"code": "after", "text": f"After the post: {sym} {_pct(after0['stock_return'])} vs the Nifty 50 "
                                                 f"{_pct(after0['nifty_return'])} over 30 days."})
    context += [f for f in tech.get("facts", []) if f["code"] in CONTEXT_CODES]
    after = ((claim or {}).get("after_post") or {}).get("horizons", {}).get("30") or {}
    if after.get("status") == "scored" and not after.get("worked"):
        wrong.append({"code": "claim_failed", "evidence": [],
                      "title": f"The claim did not stand up against the market ({_pts(after['excess_return'])} vs the Nifty 50)",
                      "text": f"Thirty days later {sym} had moved {_pct(after['stock_return'])} while the Nifty 50 moved "
                              f"{_pct(after['nifty_return'])}. Anyone who simply followed the index did better than "
                              "anyone who followed this message."})
    if tr.get("status") == "ok" and tr.get("hit_rate") is not None and tr["hit_rate"] < 0.5:
        wrong.append({"code": "weak_record", "evidence": [],
                      "title": f"A weak record: {tr['worked']} of {tr['scored']} past tips beat the Nifty 50",
                      "text": "Over many calls, this source has been right less often than a coin toss against the index. "
                              "Confident tone is not the same as a good record."})
    if detected.get("source_origin") == "fallback":
        wrong.append({"code": "no_source", "evidence": [], "title": "Nobody stands behind this message",
                      "text": "An unattributed forward has no name and no history. You cannot check the record of "
                              "someone who isn't there."})

    right = []
    if after.get("status") == "scored":
        right.append({"code": "benchmark", "title": "Judge it against the market, not a screenshot",
                      "text": f"Over the 30 days after the post, {sym} moved {_pct(after['stock_return'])} and the Nifty 50 "
                              f"moved {_pct(after['nifty_return'])}: a gap of {_pts(after['excess_return'])}. Always ask "
                              "whether a tip beat a simple index, or was just noise."})
    elif after.get("status") == "pending":  # a clear claim, but 30 days have not passed yet
        right.append({"code": "benchmark", "title": "Judge it against the market, not a screenshot",
                      "text": f"It is too early to see how {sym} did after this post. When you look back, compare it with "
                              "the Nifty 50 over the same days, not with a winner someone chose to screenshot."})
    elif sym:  # no clear up-or-down claim, or a point-in-time card that hides the outcome
        right.append({"code": "benchmark", "title": "Judge it against the market, not a screenshot",
                      "text": f"This card does not score how {sym} did after the post. Whenever you look back at a tip, "
                              "compare it with the Nifty 50 over the same days, not with a winner someone chose to "
                              "screenshot."})
    if tr.get("status") == "ok":
        right.append({"code": "record", "title": "Look at the whole record, not the best call",
                      "text": f"{tr['worked']} of {tr['scored']} past tips from this source beat the Nifty 50. Ask how many "
                              "calls there were and how each compared with the index; one good call proves little."})
    elif tr.get("status") == "not_enough":
        right.append({"code": "record", "title": "Notice how small the sample is",
                      "text": f"FinProof has only {tr.get('scored', 0)} scored tips from this source. A handful of calls "
                              "tells you very little either way."})
    else:
        right.append({"code": "record", "title": "Ask for a record you can check",
                      "text": "FinProof has no past tips from this source. A record you cannot see is not a record. Ask "
                              "for every past call with dates, not a highlights reel."})
    pressure = {w["code"] for w in warnings} & {"guarantee", "urgency", "big_promise", "percent_promise", "insider"}
    if pressure:
        right.append({"code": "downside", "title": "Ask what could go wrong first",
                      "text": "This post talks only about the upside. A genuine analyst tells you the risks and the business "
                              "facts (earnings, debt, filings) before any price. That silence is information."})
    else:
        right.append({"code": "primary", "title": "Go to the primary source and give it a day",
                      "text": "Read the company's own announcements and quarterly results on the NSE website, then give "
                              "yourself 24 hours before deciding anything. Good opportunities survive a day; pressure "
                              "tactics don't."})

    n = len(warnings)
    if n >= 3:
        intro = (f"This message uses {n} classic pressure signals. The platforms have changed, from paper certificates "
                 "to Telegram groups, but the traps look the same. Here is how to read it calmly.")
    elif n:
        intro = (f"There {'is' if n == 1 else 'are'} {n} warning sign{'s' if n != 1 else ''} here worth understanding "
                 "before anything else.")
    else:
        intro = ("This post is calm: no countdown, no promised returns, no payment request. That is a good start, but a "
                 "calm tone is not the same as a correct claim. The habits below still apply.")

    # Raw Forensic Signals: every number and quote behind the note. Findings read from the post carry the
    # post's own label (SYNTHETIC for a made-up demo post); market data and the ledger keep theirs.
    post_prov = (card.get("post") or {}).get("provenance") or REAL
    raw = []
    s = card.get("sebi") or {}
    raw.append({"code": "sebi", "label": "SEBI check", "value": s.get("text", ""), "provenance": post_prov})
    if claim and claim.get("market"):
        mk = claim["market"]
        if mk.get("spike_ratio") is not None:
            raw.append({"code": "spike_ratio", "label": "Pre-post volume ratio", "provenance": REAL,
                        "value": f"{mk['spike_ratio']:.2f}× (max of 3 sessions before the post ÷ 20-day average), {mk.get('spike_date')}"})
        if mk.get("avg_traded_value_20d") is not None:
            raw.append({"code": "traded_value", "label": "20-day average traded value", "provenance": REAL,
                        "value": f"₹{mk['avg_traded_value_20d'] / 1e7:,.2f} crore a day"})
        if mk.get("run_up_20d") is not None:
            raw.append({"code": "run_up_value", "label": "Run-up, 20 sessions before", "value": _pct(mk["run_up_20d"]),
                        "provenance": REAL})
    if after.get("status") == "scored":
        raw.append({"code": "after_30", "label": "30 days after the post", "provenance": REAL,
                    "value": f"{sym} {_pct(after['stock_return'])}, Nifty 50 {_pct(after['nifty_return'])}, gap {_pts(after['excess_return'])}"})
    if tr.get("status") in ("ok", "not_enough"):
        raw.append({"code": "track_record", "label": "Source track record",
                    "value": f"{tr.get('worked')} of {tr.get('scored')} scored tips beat the Nifty 50",
                    "provenance": tr.get("provenance") or REAL})
    for f in tech.get("facts", []):  # every indicator reading, RSI and MACD included
        raw.append({"code": f"tech_{f['code']}", "label": TECH_LABELS.get(f["code"], f["code"]), "value": f["text"],
                    "provenance": REAL})
    for w in warnings:
        raw.append({"code": w["code"], "label": flag_label(w["code"]), "value": w["text"], "evidence": w.get("evidence", []),
                    "provenance": REAL if w["code"] in MARKET_CODES else post_prov, "flag": True})
    if detected:
        raw.append({"code": "detected_date", "label": "Detected date", "provenance": post_prov,
                    "value": f"{detected.get('posted_on')} ({detected.get('date_origin')}: {detected.get('date_how')})"})
        raw.append({"code": "detected_source", "label": "Detected source", "provenance": post_prov,
                    "value": f"{detected.get('source')} ({detected.get('source_origin')})"})

    brief = {"intro": intro, "wrong": wrong, "right": right[:3], "balanced": n == 0, "raw": raw,
             "context": {"title": "Chart: before and after the post", "as_of": tech.get("as_of"),
                         "note": CONTEXT_NOTE, "facts": context} if context else None,
             "media": media.audit(card), "voice": VOICE, "disclaimer": DISCLAIMER}
    bad = veteran_problems(brief)
    if bad:  # never ship advice wording, even if a template slips
        raise ValueError(f"advice wording in veteran brief: {bad}")
    return brief


def veteran_problems(brief: dict) -> list[str]:
    """Advice wording in the mentor's own sentences (quoted post text in `evidence` is exempt)."""
    out = []
    texts = [brief["intro"], brief["voice"]] + [x[k] for part in ("wrong", "right") for x in brief[part] for k in ("title", "text")]
    if brief.get("context"):
        texts += [brief["context"]["title"], brief["context"]["note"]] + [f["text"] for f in brief["context"]["facts"]]
    texts += [r["label"] for r in brief.get("raw", [])]
    for t in texts:
        for rx in (ADVICE_RE, EXTRA_RE):
            m = rx.search(t)
            if m:
                out.append(f"{m.group(0)!r} in: {t}")
    return out
