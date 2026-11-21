"""Build the credibility card.

The card rates the source and the claim, never the stock. Every sentence FinProof
writes goes through `wording_problems`, and a test fails if any card contains
buy/sell/hold-style advice. Text quoted from the post lives in fields listed in
QUOTED_KEYS and is shown in quotation marks, clearly as the post's words.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import asdict

import pandas as pd

from . import config, extract, indicators, media, pumpdump, sebi
from .ledger import Ledger, Tip, score_tip
from .market import exchange_of, nse_companies

DISCLAIMER = ("FinProof checks the source and the information quality of a post. "
              "It is not investment advice and does not rate any stock.")

ADVICE_RE = re.compile(
    r"\b(buy|buying|sell|selling|hold|holding|accumulate|exit|go long|go short|short[- ]?sell\w*|invest in|"
    r"we recommend|recommended|target price|price target|safe (?:stock|bet|investment)|good (?:stock|investment)|"
    r"strong (?:buy|sell)|undervalued|overvalued|must[- ]buy)\b", re.I)

# Fields that hold the post's own words or third-party names, not FinProof's wording.
QUOTED_KEYS = {"title", "channel", "evidence", "matched_text", "registered_name", "company", "candidates",
               "link", "source_label", "description_excerpt", "upi_ids", "question"}

DIRECTION_TEXT = {
    "up": "The post expects the price to rise.",
    "down": "The post expects the price to fall.",
    "mixed": "The post points both ways for this stock.",
    "unclear": "We could not tell which way the post expects the price to move.",
}

PRESSURE_TEXT = {
    "guarantee": "Promises a certain or risk-free profit.",
    "urgency": "Pushes you to act quickly.",
    "big_promise": "Promises unusually large gains.",
    "insider": "Hints at secret or insider information.",
    "paid_group": "Points you to a paid or private group.",
}

DATA_PROVENANCE = [
    {"what": "Stock prices and volumes", "provenance": config.REAL_LABEL, "source": "NSE prices via Yahoo Finance"},
    {"what": "List of NSE companies", "provenance": config.REAL_LABEL, "source": "NSE equity list (archives.nseindia.com)"},
    {"what": "SEBI registration", "provenance": config.REAL_LABEL, "source": "Saved copy of SEBI's registered lists"},
]


def wording_problems(card: dict) -> list[str]:
    """Return every FinProof-written string that contains advice language."""
    problems: list[str] = []

    def walk(node, key=None):
        if key in QUOTED_KEYS:
            return
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, k)
        elif isinstance(node, list):
            for v in node:
                walk(v, key)
        elif isinstance(node, str) and ADVICE_RE.search(node):
            problems.append(node)

    walk(card)
    return problems


def _pct(x: float) -> str:
    return f"{x * 100:+.1f}%"


def _series(symbol: str) -> str | None:
    df = nse_companies()
    hit = df.loc[df["SYMBOL"] == symbol, "SERIES"]
    return None if hit.empty else str(hit.iloc[0])


def _close_on(prices, symbol: str, day: dt.date) -> tuple[float | None, str | None]:
    """Raw closing price and its date, on the last trading day on or before `day`."""
    df = prices.history(symbol)
    if df.empty:
        return None, None
    past = df.loc[df.index <= pd.Timestamp(day)]
    if past.empty:
        return None, None
    return float(past["Close"].iloc[-1]), past.index[-1].date().isoformat()


SPLIT_FACTORS = (2, 3, 4, 5, 10, 20)


def _price_scale(price_at_post: float | None, expected: list[float], close: float | None) -> tuple[float | None, str | None]:
    """Compare the post's price levels with the (split-adjusted) market price of that day.

    Returns (factor, note). factor 1 means the levels are on today's scale; a split factor
    means divide the post's prices by it; None means the levels can't be compared at all.
    """
    if not close:
        return 1.0, None
    if price_at_post:
        ratio = price_at_post / close
        if abs(ratio - 1) <= 0.12:
            return 1.0, None
    elif expected:
        ratio = expected[0] / close
        if 0.6 <= ratio <= 1.6:  # a plausible target range
            return 1.0, None
    else:
        return 1.0, None
    for f in SPLIT_FACTORS:
        if abs(ratio / f - 1) <= 0.15:
            return float(f), (f"The prices in the post are about {f} times the split-adjusted market price of that day "
                              f"(likely a stock split since), so FinProof divided them by {f} before comparing.")
    return None, "The prices in the post are far from the market price that day, so FinProof did not compare them."


def _market_warnings(sym: str, sig: pumpdump.MarketSignals) -> list[dict]:
    out = []
    if "volume_spike" in sig.flags:
        out.append({"code": "volume_spike", "text": f"Volume spike: {sym} traded {sig.spike_ratio:.1f} times its "
                    f"20-day average volume on {sig.spike_date}, in the 3 sessions before this post."})
    if "run_up" in sig.flags:
        out.append({"code": "run_up", "text": f"{sym} had already moved {_pct(sig.run_up_20d)} in the 20 sessions before the post."})
    if "thin_trading" in sig.flags:
        crore = sig.avg_traded_value_20d / 1e7
        out.append({"code": "thin_trading", "text": f"Thinly traded: {sym} averaged only about ₹{crore:.2f} crore "
                    "of trades a day over the 20 sessions before the post, so a small group can move its price."})
    if "fell_after" in sig.flags:
        out.append({"code": "fell_after", "text": f"After the post, {sym} fell {_pct(sig.fall_after)} from its peak within 30 sessions."})
    return out


def _segment_warning(sym: str) -> dict | None:
    series = _series(sym)
    if series == "BE":
        return {"code": "be_segment", "text": f"{sym} settles trade-for-trade on NSE (BE series), a segment used for stocks under closer watch."}
    if series == "BZ":
        return {"code": "bz_segment", "text": f"{sym} is in NSE's BZ series, used for companies that have not met listing rules."}
    return None


def _track_record(ledger: Ledger, source_key: str | None, as_of: dt.date | None = None) -> dict:
    sid = ledger.find_source(source_key) if source_key else None
    if not sid:
        return {"status": "no_history",
                "text": "We have no recorded tips from this source yet, so there is no track record to show."}
    rec, scored = ledger.record(sid, as_of=as_of)
    if rec is None:
        return {"status": "no_history",
                "text": "This source has no tips with a known 30-day result from before this post."}
    data = asdict(rec)
    if rec.enough_history:
        data["status"] = "ok"
        data["text"] = (f"{rec.worked} of {rec.scored} past tips from this source beat the Nifty 50 in the direction "
                        f"they claimed, {rec.horizon_days} days after posting. Average difference from the Nifty 50: "
                        f"{_pct(rec.avg_excess_return)}.")
    else:
        data["status"] = "not_enough"
        data["text"] = (f"Only {rec.scored} scored tips from this source so far. We need at least "
                        f"{config.MIN_TIPS_FOR_RECORD} before showing a percentage.")
    done = [s.tip.posted_on for s in scored if s.horizons.get(config.MAIN_HORIZON)
            and s.horizons[config.MAIN_HORIZON].status == "scored"]
    if done:
        data["period"] = {"first": min(done).isoformat(), "last": max(done).isoformat()}
    recent = [s.to_dict() for s in scored[-12:]]
    if as_of is not None:  # hide any result that was not yet known on the post date
        for tip in recent:
            posted = dt.date.fromisoformat(tip["posted_on"])
            for days, h in tip["horizons"].items():
                if posted + dt.timedelta(days=int(days)) >= as_of:
                    tip["horizons"][days] = {"days": int(days), "status": "pending"}
            tip["expected_price_reached"] = tip["days_to_expected_price"] = None
    data["recent"] = recent
    return data


def _found_in(claim, parts: dict[str, str]) -> str | None:
    """The first part of a video (title, description, transcript...) that names this stock."""
    needles = [n.lower() for n in (claim.matched_text, (claim.symbol or "").split(":")[-1]) if n]
    for part, body in parts.items():
        low = (body or "").lower()
        if any(re.search(rf"(?<![a-z0-9]){re.escape(n)}(?![a-z0-9])", low) for n in needles):
            return part
    return None


def build_card(*, text: str, ledger: Ledger, prices, posted_on: dt.date, posted_on_note: str,
               kind: str = "text", title: str | None = None, channel: str | None = None,
               source_key: str | None = None, link: str = "", max_stocks: int = 5,
               point_in_time: bool = False, post_provenance: str = config.REAL_LABEL,
               text_parts: dict[str, str] | None = None) -> dict:
    """Build the card. With point_in_time=True the card uses only what was known before
    `posted_on` (no outcome, no fall-after signal, track record as of that day). The
    decision test uses this mode so the card cannot give away how a tip turned out.
    `post_provenance` is SYNTHETIC for made-up demo posts: findings read from the post carry that label."""
    ex = extract.extract(text)
    # Where each SEBI number appears (title, description, transcript, channel page...), for the label.
    parts = text_parts or {"post": text}
    found_in = {}
    for part, body in parts.items():
        for m in extract.REGNO_RE.finditer(body or ""):
            found_in.setdefault(m.group(0).upper(), part)
    where = {"youtube": "the video title, description or transcript"}.get(kind, "the post")
    if "channel page" in parts:
        where = "the video, its description or the channel page"
    sebi_check = sebi.check(sorted(set(ex.sebi_numbers) | set(found_in)), channel, where=where, found_in=found_in)
    warnings: list[dict] = []

    # A quoted number that is not on SEBI's list is a warning, but only when our copy of the list is complete.
    # A name that matches nobody is not: channel names rarely match people's legal names.
    if sebi_check.copy_complete:
        if sebi_check.status == "number_not_found":
            warnings.append({"code": "not_on_sebi_list", "text": sebi_check.text})
        if ex.claims_sebi_registration and sebi_check.status not in ("registered", "name_match"):
            warnings.append({"code": "unverified_sebi_claim",
                             "text": "The post says it is SEBI registered, but that could not be confirmed on SEBI's list."})
    for cat, phrases in ex.pressure.items():
        warnings.append({"code": cat, "text": PRESSURE_TEXT[cat], "evidence": phrases[:4]})
    big = [p for p in ex.percent_promises if p >= 20]
    if big:
        warnings.append({"code": "percent_promise", "text": f"Claims gains of {max(big)}% or more.",
                         "evidence": [f"{p}%" for p in big]})

    personal_upi = [u["id"] for u in ex.upi_ids if not u["validated_format"]]
    if personal_upi:
        warnings.append({"code": "personal_upi", "evidence": personal_upi,
                         "text": "Asks for payment to a personal UPI ID. Since 1 October 2025, SEBI-registered "
                                 "intermediaries collect payments through '@valid' UPI handles, and this ID is not one."})
    payments = None
    if ex.upi_ids:
        valid = [u["id"] for u in ex.upi_ids if u["validated_format"]]
        payments = {"upi_ids": ex.upi_ids,
                    "text": ("Uses an '@valid' UPI handle, the format reserved for SEBI-registered intermediaries. "
                             "Check it on SEBI's 'SEBI Check' service before paying.") if valid and not personal_upi
                    else "The post gives a UPI ID for payment."}

    claims = []
    for c in ex.claims:
        direction_note = scale_note = None
        factor = 1.0
        if c.symbol and (c.expected_prices or c.price_at_post):
            ref_day = posted_on - dt.timedelta(days=1) if point_in_time else posted_on
            close, close_day = _close_on(prices, c.symbol, ref_day)
            factor, scale_note = _price_scale(c.price_at_post, c.expected_prices, close)
            if (factor and c.direction == "unclear" and not c.negated and c.expected_prices and close):
                level = c.expected_prices[0] / factor
                c.direction = "up" if level > close else "down"
                direction_note = (f"Worked out from the price the post names ({c.expected_prices[0]:g}) "
                                  f"compared with the closing price on {close_day} ({close:,.2f}).")
        item = {
            "symbol": c.symbol, "company": c.company, "mentions": c.mentions,
            "direction": c.direction, "direction_text": DIRECTION_TEXT[c.direction],
            "expected_prices": c.expected_prices, "stop_loss": c.stop_loss, "price_at_post": c.price_at_post,
            "ambiguous": c.ambiguous, "candidates": c.candidates, "matched_text": c.matched_text,
            "renamed_from": c.renamed_from, "direction_note": direction_note, "price_scale_note": scale_note,
            "found_in": _found_in(c, parts) if text_parts else None,
        }
        if c.ambiguous:
            item["note"] = f"\"{c.matched_text}\" could mean several listed companies, so we did not check it."
        elif len([x for x in claims if not x["ambiguous"]]) < max_stocks:
            sig = pumpdump.market_signals(c.symbol, posted_on, prices, include_after=not point_in_time)
            item["market"] = sig.to_dict()
            item["exchange"] = exchange_of(prices, c.symbol)
            tech = indicators.snapshot(prices.history(c.symbol), posted_on)  # sessions before the post only
            if tech:
                item["technicals"] = tech
            warnings.extend({**w, "symbol": c.symbol} for w in _market_warnings(c.symbol, sig))
            seg = _segment_warning(c.symbol)
            if seg:
                warnings.append({**seg, "symbol": c.symbol})
            if c.direction in ("up", "down") and not point_in_time:
                usable = factor and c.expected_prices
                tip = Tip("card", "card", "this post", c.symbol, c.direction, posted_on,
                          expected_price=c.expected_prices[0] / factor if usable else None)
                scored = score_tip(tip, prices).to_dict()
                item["after_post"] = {"horizons": scored["horizons"],
                                      "expected_price_reached": scored["expected_price_reached"],
                                      "days_to_expected_price": scored["days_to_expected_price"]}
        claims.append(item)

    # The "only education" loophole: a disclaimer, yet specific price levels for a named stock.
    priced = [c for c in claims if not c["ambiguous"] and c["direction"] in ("up", "down")
              and (c["expected_prices"] or c["stop_loss"] or c["price_at_post"])]
    # Media & impersonation cues (fake-video and social scam patterns); observed cues, not proof.
    price_call = any(not c["ambiguous"] and (c["expected_prices"] or c["stop_loss"] or c["price_at_post"]) for c in claims)
    warnings.extend(media.flags(text, kind, sebi_numbers=ex.sebi_numbers, priced_call=price_call))
    if ex.disclaimers and priced:
        lead = ("Says it is not SEBI registered or only for education" if ex.says_not_registered
                else "Calls itself education or 'not advice'")
        warnings.append({"code": "education_loophole", "evidence": ex.disclaimers[:3], "symbol": priced[0]["symbol"],
                         "text": f"{lead}, but still gives price levels for {priced[0]['symbol']}."})

    track = _track_record(ledger, source_key, as_of=posted_on if point_in_time else None)
    provenance = list(DATA_PROVENANCE)
    if track.get("provenance"):
        provenance.append({"what": "Past tips of this source", "provenance": track["provenance"],
                           "source": "FinProof tip ledger"})

    n = len(warnings)
    card = {
        "disclaimer": DISCLAIMER,
        "post": {"kind": kind, "title": title, "channel": channel, "link": link,
                 "posted_on": posted_on.isoformat(), "posted_on_note": posted_on_note, "words": ex.words,
                 "point_in_time": point_in_time, "provenance": post_provenance,
                 "as_of_text": (f"Uses only information available before {posted_on.isoformat()}."
                                if point_in_time else None)},
        "summary": {"warning_count": n,
                    "text": "No warning signs found." if n == 0 else f"{n} warning sign{'s' if n != 1 else ''} found."},
        "sebi": sebi_check.to_dict(),
        "claims": claims,
        "no_stock_text": None if claims else "We did not find an NSE-listed company in this post.",
        "track_record": track,
        "warnings": warnings,
        "payments": payments,
        "data_provenance": provenance,
    }
    card["media"] = media.audit(card)
    problems = wording_problems(card)
    if problems:  # never ship advice wording, even if a template slips
        raise ValueError(f"advice wording in card: {problems}")
    return card
