"""Claim Auditor: answers questions using ONLY the facts on the current FinProof card.

Deterministic and offline (no language model, no API key). Every sentence is built from
fields of the card, so it cannot invent numbers. Questions asking what to buy, sell or
hold, or where a price will go, are refused and redirected to the card's facts.

Every answer has the same shape as a short research brief:
  headline (one plain-English takeaway) -> fact lines, each with evidence tags
  ([SEBI], [NSE 30D], [Volume], [Quote], [Tech]) -> one "Mentor's note" line.
"""

from __future__ import annotations

import re

from . import indicators, media
from .card import ADVICE_RE

REFUSAL = ("FinProof never tells you what to buy or sell, and it does not predict prices. "
           "Here is what the card can tell you about this post instead.")

ADVICE_QUESTION = re.compile(
    r"\b(?:buy|buying|sell|selling|hold|holding|invest|investing|purchase|accumulate|exit|book\s+profits?|"
    r"short\s*sell|target(?:\s+price)?|price\s+target|predict\w*|forecast\w*|"
    r"will\s+(?:it|the\s+price|this|the\s+stock)\s+(?:go|rise|fall|reach|hit|double|crash)|go(?:es)?\s+up|go(?:es)?\s+down|"
    r"good\s+(?:stock|buy|investment|time)|safe\s+(?:stock|bet|pick|investment)|worth\s+(?:it|buying)|"
    r"kharid\w*|le\s+lu|lena\s+chahiye|bech\w*|togol\w*|maarl\w*)\b", re.I)

SEBI, NSE30, VOLUME, QUOTE, TECH = "SEBI", "NSE 30D", "Volume", "Quote", "Tech"
CITES = (SEBI, NSE30, VOLUME, QUOTE, TECH)

# Checked in order; the first match decides the answer. Beginner concepts and indicators come first,
# then the card's own sections.
INTENTS = [
    ("check", re.compile(r"\bvolume\s*(?:&|and)\s*chart\b", re.I)),
    ("media", re.compile(r"\b(?:fake|deep\s*fake|impersonat\w*|leaked|celebrit\w*|famous|endorse\w*|funnel|"
                         r"link\s+in\s+bio|media\s+flags?|ai\s+(?:bot|video))\b", re.I)),
    ("concept_pump", re.compile(r"pump\s*(?:and|&|n|-|'n'|\+)?\s*dump|\bpump\w*\b.*\bdump\w*\b", re.I)),
    ("concept_upi", re.compile(r"\bupi\b", re.I)),
    ("concept_sebi", re.compile(r"\bwhat\s+(?:does|is|do)\b.*\bsebi\b|\bsebi\b.*\bmean\w*|\bwho\s+is\s+sebi\b", re.I)),
    ("concept_nifty", re.compile(r"\bwhy\b.*\b(?:nifty|index|benchmark)\b|\bcompar\w*\b.*\b(?:with|to|against)\s+(?:the\s+)?"
                                 r"(?:nifty|index)\b|\bwhat\s+is\s+(?:the\s+)?nifty|\bbenchmark\b", re.I)),
    ("concept_thin", re.compile(r"\b(?:liquid\w*|illiquid\w*|thin(?:ly)?)\b", re.I)),
    ("tech_rsi", re.compile(r"\brsi\b|relative\s+strength", re.I)),
    ("tech_macd", re.compile(r"\bmacd\b", re.I)),
    ("tech_vwap", re.compile(r"\bvwap\b|volume[- ]weighted", re.I)),
    ("tech_bollinger", re.compile(r"\bbollinger\b|\bbands?\b", re.I)),
    ("tech_ema", re.compile(r"\bema\b|exponential", re.I)),
    ("tech_sma", re.compile(r"\bsma\b|simple\s+moving|moving\s+average", re.I)),
    ("tech_atr", re.compile(r"\batr\b|average\s+true\s+range|daily\s+swing|\bswing\b|volatil\w*", re.I)),
    ("tech_levels", re.compile(r"52[- ]?w(?:ee)?k?|\bkey\s+levels?\b|30[- ]?(?:d|day|session)\w*\s+(?:high|low)|rock\s+bottom|"
                               r"breakout|all[- ]time\s+high|lifetime\s+high|\bsupport\b|\bresistance\b", re.I)),
    ("tech", re.compile(r"\btechnical\w*|\bindicators?\b|\bchart\b|\bmomentum\b", re.I)),
    ("volume", re.compile(r"\b(volume|spike|traded|pump|dump|operator|run[\s-]?up)\b", re.I)),
    ("sebi", re.compile(r"\b(sebi|regist\w*|licen\w*|payment|pay|fees?|valid)\b", re.I)),
    ("track", re.compile(r"\b(track|record|history|past|nifty|hit\s*rate|accura\w*|reliab\w*|trust\w*|right)\b", re.I)),
    ("after", re.compile(r"\b(after|happened|outcome|result|later)\b", re.I)),
    ("warnings", re.compile(r"\b(warn\w*|flag\w*|red|why|sign\w*|suspicious|scam|hype|pressure|loophole|education\w*)\b", re.I)),
    ("claims", re.compile(r"\b(claim\w*|which\s+stock|stocks?|levels?|says?|mention\w*)\b", re.I)),
]

QUICK_PROMPTS = [
    "Should I buy this?",
    "Why flagged?",
    "Source record",
    "Volume & chart check",
]

# One calm line from the mentor after each answer: a habit, never a call on the stock.
MENTOR = {
    "warnings": "Pressure tactics are built to rush you. The facts will still be there tomorrow.",
    "track": "One good call proves little. Count the calls, and compare each with the Nifty 50.",
    "volume": "Volume tells you someone was active, not why. Check the exchange filings for those dates.",
    "sebi": "Registration tells you who is accountable, not who is right. Check both.",
    "after": "Judge every tip against the index, not against a screenshot of a winner.",
    "claims": "A price level without a reason and a risk is a sales line, not analysis.",
    "advice": "That decision is yours, made slowly, with the company's own filings in front of you.",
    "overview": "Read the facts first, then give yourself a day before deciding anything.",
    "no_card": "Start with the source and the date. Every check follows from those two.",
    "tech": "An indicator describes the past. Use it to test a post's story, never as the reason to act.",
    "tech_atr": "Know the normal daily swing before you call any move big.",
    "tech_levels": "Before you believe 'rock bottom' or 'breakout', look at where the price actually sat in its range.",
    "concept_pump": "When a stock is being shouted about, ask who gains from your attention.",
    "concept_nifty": "A tip that cannot beat a simple index over the same days added nothing.",
    "concept_sebi": "Look up the registration number yourself on SEBI's website; never trust a screenshot of one.",
    "concept_thin": "The quieter the stock, the easier it is for a few people to move it. Check the traded value first.",
    "concept_upi": "Pay only to an '@valid' handle you have checked on SEBI's own service.",
    "check": "Volume and price show activity, not intent. Check the exchange filings for those dates.",
    "media": "A famous face in a clip proves nothing. Look for the same news on the company's or regulator's own site.",
}


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:+.1f}%"


def _apct(x: float) -> str:
    return f"{abs(round(float(x) * 100, 1)):.1f}%"


def _line(text: str, evidence: list[str] | None = None, cite: list[str] | str | None = None) -> dict:
    cites = [cite] if isinstance(cite, str) else list(cite or [])
    return {"text": text, "evidence": evidence or [], "cite": cites}


def _stocks(card: dict) -> list[dict]:
    return [c for c in card.get("claims", []) if not c.get("ambiguous") and c.get("symbol")]


def _tech(card: dict) -> tuple[dict | None, dict | None]:
    for c in _stocks(card):
        if c.get("technicals"):
            return c, c["technicals"]
    return None, None


# ------------------------------------------------------------------ the card's own sections
def _warning_cite(code: str) -> list[str]:
    if code in ("volume_spike", "thin_trading", "be_segment", "bz_segment"):
        return [VOLUME]
    if code in ("run_up", "fell_after"):
        return [TECH]
    if code in ("personal_upi", "not_on_sebi_list", "unverified_sebi_claim"):
        return [SEBI, QUOTE] if code == "personal_upi" else [SEBI]
    return [QUOTE]


def _warnings(card: dict):
    ws = card.get("warnings") or []
    if not ws:
        return "None of the warning signs FinProof checks for were found in this post.", [
            _line("FinProof checked for promises, urgency, paid groups, personal UPI IDs, SEBI claims and unusual "
                  "trading before the post.", cite=[QUOTE, VOLUME])]
    return (f"{len(ws)} warning sign{'s' if len(ws) != 1 else ''} in this post.",
            [_line(w["text"], w.get("evidence"), _warning_cite(w["code"])) for w in ws])


def _track(card: dict):
    tr = card.get("track_record") or {}
    head = (f"{tr['worked']} of {tr['scored']} past tips from this source beat the Nifty 50 over 30 days."
            if tr.get("status") == "ok" else tr.get("text", "No track record information on this card."))
    out = []
    if tr.get("status") == "ok":
        out.append(_line(tr["text"], cite=NSE30))
    shown = 0
    for tip in reversed(tr.get("recent") or []):
        h = (tip.get("horizons") or {}).get("30") or {}
        if h.get("status") != "scored" or shown >= 4:
            continue
        claimed = "a rise" if tip.get("direction") == "up" else "a fall"
        verdict = "matched the claim" if h.get("worked") else "did not match the claim"
        out.append(_line(f"Tip of {tip['posted_on']} on {tip['symbol']} claimed {claimed}: after 30 days the stock moved "
                         f"{_pct(h.get('stock_return'))} and the Nifty 50 {_pct(h.get('nifty_return'))}, so it {verdict}.",
                         cite=NSE30))
        shown += 1
    if tr.get("provenance"):
        out.append(_line(f"These past tips are {tr['provenance']} data.", cite=NSE30))
    if not out:
        out.append(_line("FinProof keeps a ledger of past tips per source and scores each against the Nifty 50 after "
                         "30 days.", cite=NSE30))
    return head, out


def _volume(card: dict):
    stocks = [c for c in _stocks(card) if c.get("market")]
    if not stocks:
        return "No NSE-listed stock was found, so there is no volume to check.", [
            _line("FinProof measures volume only for NSE-listed companies named in the post.", cite=VOLUME)]
    out, head = [], None
    for c in stocks:
        m = c["market"]
        if m.get("status") != "ok":
            out.append(_line(f"{c['symbol']}: not enough trading history before the post to measure volume.", cite=VOLUME))
            continue
        spike = m.get("spike_ratio")
        if spike is not None:
            flagged = "volume_spike" in m.get("flags", [])
            head = head or (f"Yes: {c['symbol']} traded {spike:.1f}× its 20-day average volume on {m.get('spike_date')}, "
                            "before the post." if flagged else
                            f"No unusual volume: the busiest session before the post was {spike:.1f}× the 20-day average "
                            "(FinProof flags 2.5× or more).")
            out.append(_line(f"{c['symbol']}: the biggest volume in the 3 sessions before the post was {spike:.1f}x "
                             f"its 20-day average (on {m.get('spike_date')}), "
                             f"{'flagged as a spike' if flagged else 'below the 2.5x spike level'}.", cite=VOLUME))
        value = m.get("avg_traded_value_20d")
        if value is not None:
            thin = "flagged as thinly traded" if "thin_trading" in m.get("flags", []) else "above the ₹1 crore thin-trading level"
            out.append(_line(f"{c['symbol']}: about ₹{value / 1e7:,.2f} crore traded a day over the 20 sessions before "
                             f"the post, {thin}.", cite=VOLUME))
        if m.get("run_up_20d") is not None:
            out.append(_line(f"{c['symbol']}: price change over the 20 sessions before the post: {_pct(m['run_up_20d'])}.",
                             cite=TECH))
        if m.get("last_session_used"):
            out.append(_line(f"These numbers use sessions up to {m['last_session_used']}, before the post.", cite=VOLUME))
    return head or "Volume could not be measured before this post.", out


def _sebi(card: dict):
    s = card.get("sebi") or {}
    out = []
    if s.get("coverage_text"):
        out.append(_line(s["coverage_text"], cite=SEBI))
    if card.get("payments"):
        out.append(_line(card["payments"]["text"], [u["id"] for u in card["payments"].get("upi_ids", [])], [SEBI, QUOTE]))
    out += [_line(w["text"], w.get("evidence"), [SEBI, QUOTE]) for w in card.get("warnings", [])
            if w["code"] in ("personal_upi", "not_on_sebi_list", "unverified_sebi_claim", "education_loophole")]
    return s.get("text", "No SEBI information on this card."), out or [
        _line("FinProof looks for a registration number or a name in the post and checks it against its saved copy "
              "of SEBI's lists.", cite=SEBI)]


def _after(card: dict):
    if (card.get("post") or {}).get("point_in_time"):
        return "This card only uses information from before the post.", [
            _line("It does not show what happened after, so it cannot give away how the tip turned out.", cite=NSE30)]
    out, head = [], None
    for c in card.get("claims", []):
        h = ((c.get("after_post") or {}).get("horizons") or {}).get("30")
        if h and h.get("status") == "scored":
            verdict = "matched" if h.get("worked") else "did not match"
            head = head or (f"30 days after the post, {c['symbol']} moved {_pct(h['stock_return'])} while the Nifty 50 "
                            f"moved {_pct(h['nifty_return'])}.")
            out.append(_line(f"{c['symbol']}: 30 days after the post the stock moved {_pct(h['stock_return'])} and the "
                             f"Nifty 50 {_pct(h['nifty_return'])} (difference {_pct(h['excess_return'])}), so the post's "
                             f"claim {verdict}.", cite=NSE30))
    if not out:
        return "Not enough time has passed, or no stock was found, to show what happened after this post.", [
            _line("FinProof scores a claim once 30 sessions have passed after the post.", cite=NSE30)]
    return head, out


def _claims(card: dict):
    if not card.get("claims"):
        return card.get("no_stock_text") or "No NSE-listed company was found in this post.", [
            _line("FinProof matches the post's words against NSE's list of listed companies.", cite=QUOTE)]
    out = []
    for c in card["claims"]:
        if c.get("ambiguous"):
            out.append(_line(c.get("note", "An unclear company name."), [c.get("matched_text", "")], QUOTE))
            continue
        bits = [f"{c['symbol']}: {c['direction_text']}"]
        if c.get("expected_prices"):
            bits.append("Prices named in the post: " + ", ".join(f"₹{p:,.0f}" for p in c["expected_prices"]) + ".")
        if c.get("stop_loss"):
            bits.append(f"Stop-loss named: ₹{c['stop_loss']:,.0f}.")
        out.append(_line(" ".join(bits), cite=QUOTE))
    names = [c["symbol"] for c in _stocks(card)]
    head = (f"The post names {len(names)} NSE stock{'s' if len(names) != 1 else ''}: {', '.join(names)}."
            if names else "The post names no stock FinProof could check.")
    return head, out


def _overview(card: dict):
    out = []
    ws = card.get("warnings") or []
    out += [_line(w["text"], w.get("evidence"), _warning_cite(w["code"])) for w in ws[:3]]
    tr = card.get("track_record") or {}
    if tr.get("text"):
        out.append(_line(tr["text"], cite=NSE30))
    if (card.get("sebi") or {}).get("text"):
        out.append(_line(card["sebi"]["text"], cite=SEBI))
    _, t = _tech(card)
    atr = next((f for f in (t or {}).get("facts", []) if f["code"] == "atr14"), None)
    if atr:
        out.append(_line(atr["text"], cite=TECH))
    return (card.get("summary") or {}).get("text", "Here is what the card shows."), [x for x in out if x["text"]]


# ------------------------------------------------------------------ indicators, from the card's point-in-time snapshot
def _no_tech(card: dict, key: str):
    return "There is no price history before this post to compute indicators.", [
        _line(indicators.EXPLAIN[key], cite=TECH),
        _line("FinProof needs at least 20 sessions of NSE prices before the post.", cite=TECH)]


def _fact(t: dict, code: str) -> str | None:
    return next((f["text"] for f in t.get("facts", []) if f["code"] == code), None)


def _tech_answer(card: dict, key: str, code: str):
    c, t = _tech(card)
    if not t:
        return _no_tech(card, key)
    sym, day = c["symbol"], t["as_of"]
    fact = _fact(t, code)
    if code == "rsi14":
        head = f"Before the post, {sym}'s RSI(14) was {t['rsi14']:.1f}: {indicators.rsi_words(t['rsi14'])}."
        extra = [_line(f"Reading on {day}, the last session before the post. 70 and above marks a rapid recent climb, "
                       "30 and below a rapid recent drop.", cite=TECH)]
    elif code == "macd":
        head = f"Before the post, {sym}'s {fact}" if fact else "MACD could not be computed."
        extra = [_line(f"On {day}: MACD line {t['macd']:+.3f}, signal line {t['macd_signal']:+.3f}.", cite=TECH)] \
            if t.get("macd") is not None and t.get("macd_signal") is not None else []
    elif code == "atr14":
        head = (f"{sym} typically moved about ±{_apct(t['atr14_pct'])} a day before the post (ATR 14)."
                if t.get("atr14_pct") is not None else "ATR could not be computed.")
        extra = [_line(f"In rupees: about ₹{t['atr14']:,.2f} a day on a closing price of ₹{t['close']:,.2f} ({day}).",
                       cite=TECH)] if t.get("atr14") is not None else []
    elif code == "levels":
        lv = t.get("levels") or {}
        if lv.get("high_52w") is not None:
            head = (f"Before the post, {sym} closed at ₹{t['close']:,.2f}: {_apct(t['close'] / lv['high_52w'] - 1)} below its "
                    f"52-week high and {_apct(t['close'] / lv['low_52w'] - 1)} above its 52-week low.")
        elif lv.get("high_30d") is not None:
            head = f"Before the post, {sym} closed at ₹{t['close']:,.2f}, within its 30-session range."
        else:
            head = "Not enough history for key levels."
        extra = [_line("Words like 'rock bottom' or 'breakout of the year' can be checked against these levels.", cite=TECH)]
    else:
        names = {"sma20": ("SMA 20", "sma20", "dist_sma20"), "ema50": ("EMA 50", "ema50", "dist_ema50"),
                 "vwap20": ("20-day VWAP", "vwap20", "dist_vwap20")}
        if code in names:
            label, val, dist = names[code]
            head = (f"Before the post, {sym} closed {_apct(t[dist])} {'above' if t[dist] >= 0 else 'below'} its {label} "
                    f"(₹{t[val]:,.2f})." if t.get(dist) is not None else f"{label} could not be computed.")
            extra = []
            if code == "vwap20" and c.get("price_at_post") and t.get("vwap20"):
                extra.append(_line(f"The post quotes ₹{c['price_at_post']:,.2f}; most traders over the 20 sessions before "
                                   f"it paid about ₹{t['vwap20']:,.2f}.", cite=[QUOTE, TECH]))
        else:  # bollinger
            if t.get("bb_upper") is not None:
                where = ("above the upper band" if t["close"] > t["bb_upper"] else "below the lower band"
                         if t["close"] < t["bb_lower"] else "inside the bands")
                head = (f"Before the post, {sym} closed {where}: ₹{t['close']:,.2f} against bands of ₹{t['bb_lower']:,.2f} "
                        f"to ₹{t['bb_upper']:,.2f}.")
            else:
                head = "Bollinger bands could not be computed."
            extra = []
    lines = [_line(indicators.EXPLAIN[key], cite=TECH)]
    if fact and code not in ("rsi14", "atr14"):
        lines.append(_line(f"{fact} ({day})", cite=TECH))
    return head, lines + extra


def _tech_overview(card: dict):
    c, t = _tech(card)
    if not t:
        return _no_tech(card, "sma20")
    return (f"Here is what {c['symbol']}'s chart showed on {t['as_of']}, the last session before the post.",
            [_line(f["text"], cite=TECH) for f in t.get("facts", [])])


# ------------------------------------------------------------------ beginner concepts, tied to this card's numbers
def _concept_pump(card: dict):
    lines = [_line("FinProof looks for the usual signs: unusual volume before the post, a sharp run-up, thin trading, "
                   "and hype words such as guarantees and deadlines.", cite=[VOLUME, QUOTE])]
    for c in _stocks(card):
        m = c.get("market") or {}
        if m.get("spike_ratio") is not None:
            lines.append(_line(f"{c['symbol']}: busiest session before the post {m['spike_ratio']:.1f}× its 20-day "
                               "average volume.", cite=VOLUME))
        if m.get("run_up_20d") is not None:
            lines.append(_line(f"{c['symbol']}: {_pct(m['run_up_20d'])} over the 20 sessions before the post.", cite=TECH))
        break
    hype = [w for w in card.get("warnings", []) if w["code"] in ("guarantee", "urgency", "big_promise", "insider",
                                                                  "paid_group", "percent_promise")]
    lines.append(_line(f"Hype signals in this post: {len(hype)}.", [e for w in hype for e in w.get("evidence", [])][:4], QUOTE))
    return ("A pump and dump is when a group pushes up a thinly watched stock with hype, then unloads its own "
            "shares on the newcomers the hype attracted."), lines


def _concept_nifty(card: dict):
    lines = [_line("Any stock can rise when the whole market rises. Comparing with the Nifty 50 over the same days "
                   "separates the tip's effect from the market's.", cite=NSE30)]
    _, after = _after(card)
    lines += [x for x in after if "difference" in x["text"]]
    tr = card.get("track_record") or {}
    if tr.get("status") == "ok":
        lines.append(_line(tr["text"], cite=NSE30))
    return ("The Nifty 50 is the fair yardstick: a tip that did not beat it over the same days added nothing beyond "
            "what the whole market did."), lines


def _concept_sebi(card: dict):
    s = card.get("sebi") or {}
    lines = [_line("Registered research analysts and advisers have a SEBI registration number (INH... for research "
                   "analysts, INA... for advisers) that anyone can look up on SEBI's website.", cite=SEBI),
             _line("Since 1 October 2025, SEBI-registered intermediaries collect money through validated '@valid' UPI "
                   "handles.", cite=SEBI)]
    if s.get("text"):
        lines.append(_line(f"This post: {s['text']}", cite=SEBI))
    return ("SEBI registration means a person is licensed by India's market regulator and can be held accountable "
            "for what they publish."), lines


def _concept_thin(card: dict):
    lines = [_line("FinProof flags a stock as thinly traded when it averaged under ₹1 crore of trades a day over the "
                   "20 sessions before the post.", cite=VOLUME)]
    for c in _stocks(card):
        v = (c.get("market") or {}).get("avg_traded_value_20d")
        if v is not None:
            thin = "thin_trading" in (c.get("market") or {}).get("flags", [])
            lines.append(_line(f"{c['symbol']}: about ₹{v / 1e7:,.2f} crore a day, "
                               f"{'below' if thin else 'above'} that level.", cite=VOLUME))
    return "Thin liquidity means few shares change hands each day, so a small group can move the price.", lines


def _concept_upi(card: dict):
    lines = [_line("Since 1 October 2025, SEBI-registered intermediaries collect payments through validated '@valid' "
                   "UPI handles, which can be checked on SEBI's own service.", cite=SEBI)]
    ids = (card.get("payments") or {}).get("upi_ids") or []
    personal = [u["id"] for u in ids if not u.get("validated_format")]
    valid = [u["id"] for u in ids if u.get("validated_format")]
    if personal:
        lines.append(_line("This post asks for payment to a personal UPI ID, not an '@valid' handle.", personal, [SEBI, QUOTE]))
    if valid:
        lines.append(_line("This post gives an '@valid' handle; check it on SEBI's service before paying anyone.", valid,
                           [SEBI, QUOTE]))
    if not ids:
        lines.append(_line("This post gives no UPI ID.", cite=QUOTE))
    return ("A personal UPI ID cannot be traced to a registered firm, so if something goes wrong there is no one "
            "accountable to complain to."), lines


def _check(card: dict):
    """Volume and chart together: the pre-post volume facts, then the indicator readings."""
    head, lines = _volume(card)
    _, t = _tech(card)
    lines = list(lines) + [_line(f["text"], cite=TECH) for f in (t or {}).get("facts", [])
                           if f["code"] in ("rsi14", "atr14", "vwap20", "levels")]
    return head, lines


def _media(card: dict):
    ws = [w for w in card.get("warnings", []) if w["code"] in media.MEDIA_CODES]
    lines = [_line(w["text"], w.get("evidence"), _warning_cite(w["code"])) for w in ws]
    lines.append(_line(media.NOTE + " FinProof reads the post's words and market data, not the video file.", cite=QUOTE))
    if not ws:
        return "No impersonation or scam-funnel cues in this post.", lines
    return f"{len(ws)} media & impersonation cue{'s' if len(ws) != 1 else ''} in this post.", lines


SECTIONS = {
    "check": _check, "media": _media,
    "warnings": _warnings, "track": _track, "volume": _volume, "sebi": _sebi, "after": _after, "claims": _claims,
    "tech": _tech_overview,
    "tech_rsi": lambda c: _tech_answer(c, "rsi14", "rsi14"), "tech_macd": lambda c: _tech_answer(c, "macd", "macd"),
    "tech_vwap": lambda c: _tech_answer(c, "vwap20", "vwap20"),
    "tech_bollinger": lambda c: _tech_answer(c, "bollinger", "bollinger"),
    "tech_ema": lambda c: _tech_answer(c, "ema50", "ema50"), "tech_sma": lambda c: _tech_answer(c, "sma20", "sma20"),
    "tech_atr": lambda c: _tech_answer(c, "atr14", "atr14"), "tech_levels": lambda c: _tech_answer(c, "levels", "levels"),
    "concept_pump": _concept_pump, "concept_nifty": _concept_nifty, "concept_sebi": _concept_sebi,
    "concept_thin": _concept_thin, "concept_upi": _concept_upi,
}


def mentor_for(intent: str) -> str:
    if intent in MENTOR:
        return MENTOR[intent]
    return MENTOR["tech"] if intent.startswith("tech") else MENTOR["overview"]


def intent_of(question: str) -> str:
    return next((name for name, rx in INTENTS if rx.search(question)), "overview")


def answer(question: str, card: dict | None) -> dict:
    question = (question or "").strip()[:500]
    if not card:
        if ADVICE_QUESTION.search(question):
            return {"question": question, "refused": True, "refusal": REFUSAL, "intent": "advice", "headline": REFUSAL,
                    "mentor": MENTOR["advice"], "lines": [
                        _line("Paste the tip you saw (the message or a YouTube link). FinProof will show the source's past "
                              "record, any warning signs and what the market data says.", cite=QUOTE)]}
        return {"question": question, "refused": False, "refusal": None, "intent": "no_card", "mentor": MENTOR["no_card"],
                "headline": "Paste a tip first.",
                "lines": [_line("Paste the message or a YouTube link. FinProof answers only from what it finds in that "
                                "post and in NSE data.", cite=QUOTE)]}
    if ADVICE_QUESTION.search(question):
        _, lines = _overview(card)
        result = {"question": question, "refused": True, "refusal": REFUSAL, "intent": "advice", "headline": REFUSAL,
                  "lines": lines}
    else:
        intent = intent_of(question)
        headline, lines = SECTIONS.get(intent, _overview)(card)
        result = {"question": question, "refused": False, "refusal": None, "intent": intent, "headline": headline,
                  "lines": lines}
    result["mentor"] = mentor_for(result["intent"])
    texts = [result["mentor"]] + [ln["text"] for ln in result["lines"]]
    if result["headline"] != REFUSAL:  # the refusal states the policy itself
        texts.append(result["headline"])
    bad = [t for t in texts if ADVICE_RE.search(t)]
    if bad:  # a line of FinProof's own wording slipped into advice language
        raise ValueError(f"advice wording in auditor answer: {bad}")
    return result
