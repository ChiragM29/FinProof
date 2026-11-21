"""The "Signal or Noise" label: a nutrition-label view of one post.

Two separate questions, because the brief separates honest-but-wrong tips from pump-and-dump schemes:
  "Were they right before?"  the source's record in the tip ledger (30 days vs the Nifty 50)
  "Are they playing fair?"   SEBI registration, conflict disclosure, pressure, payment route, pump pattern
plus one line for the message type. It judges the message and its sender, never the stock. Every line
states a fact, carries a REAL or SYNTHETIC tag, and has a "why" that names the rule or the source.
"""

from __future__ import annotations

import datetime as dt
import re

from . import config, media, surveillance

TITLE = "Signal or Noise"
NOTE = "Judges the message and its sender, never the stock."
PRESSURE_CODES = ("guarantee", "urgency", "big_promise", "insider", "paid_group", "percent_promise", "funnel", "impersonation")
PRESSURE_NAMES = {"guarantee": "certain profit", "urgency": "urgency", "big_promise": "big promises", "insider": "insider talk",
                  "paid_group": "paid group", "percent_promise": "large % promise", "funnel": "scam funnel",
                  "impersonation": "famous-name bait"}
DISCLOSURE_RE = re.compile(r"\b(?:disclosure|conflict of interest|vested interest|(?:i|we)\s+(?:am|are|have)\s+(?:invested|"
                           r"a position|positions)|(?:i|we)\s+(?:own|have)\s+(?:shares|this stock)|my position)\b", re.I)
EDU_RULE_FROM = dt.date(2026, 7, 1)

WHY = {
    "type": "Education teaches a method; an opinion gives a view; a tip names prices to act on; a pressure pitch pushes "
            "you to act or pay; a pump pattern adds unusual trading around the post.",
    "record": "FinProof tip ledger: every past call is scored against the Nifty 50 30 days after posting. A share is "
              "shown only after 10 scored calls.",
    "sebi": "SEBI (Research Analysts) Regulations, 2014 and SEBI (Investment Advisers) Regulations, 2013: research and "
            "advice for a fee need SEBI registration. Checked against FinProof's dated copy of SEBI's lists.",
    "disclosure": "SEBI's research analyst rules require disclosing any position or financial interest in a stock they "
                  "write about.",
    "pressure": "SEBI investor alerts warn about promised returns, deadlines and paid 'VIP' groups.",
    "payment": "SEBI: from 1 October 2025, registered intermediaries collect payments through validated '@valid' UPI "
               "handles.",
    "pump": "Pattern from SEBI pump-and-dump orders: unusual trading before a promotion, a poor showing after it "
            "(e.g. Sadhna Broadcast, SEBI interim order of 2 March 2023).",
    "liquidity": "Average daily traded value (price x volume) over the 20 sessions before the post. Thinly traded "
                 "stocks (under ₹1 crore a day) are easier to move.",
    "surveillance": "NSE's own Additional (ASM), Graded (GSM) and Enhanced (ESM) Surveillance Measure lists, saved as a "
                    "dated snapshot. They show the exchange's current view, not the view on the post date.",
    "education": "SEBI circular HO/47/17/12(11)2025-MRD-POD3/I/11107/2026 of 8 May 2026 (as reported by Bigul): from "
                 "1 July 2026, price data used for education must be at least 30 days old.",
}


def _line(key: str, label: str, value: str, provenance: str, tone: str = "info", evidence: list[str] | None = None) -> dict:
    return {"key": key, "label": label, "value": value, "provenance": provenance, "tone": tone, "why": WHY.get(key, ""),
            "evidence": evidence or []}


def _pct(x: float) -> str:
    return f"{round(float(x) * 100, 1):+.1f}"


def is_pump(codes: set[str]) -> bool:
    """Unusual volume before a hyped post in a thin or already-running stock, or a sharp fall after it.
    Volume alone is not enough: a large one-off trade in a big stock looks the same (see Failure Cases)."""
    hype = codes & (set(PRESSURE_CODES) | {"personal_upi"})
    return bool(("volume_spike" in codes and hype and codes & {"thin_trading", "run_up"}) or "fell_after" in codes)


def message_type(card: dict) -> tuple[str, str]:
    """(type, tone). Pump pattern > Pressure pitch > Unverified tip > Opinion > Education."""
    codes = {w["code"] for w in card.get("warnings", [])}
    claims = [c for c in card.get("claims", []) if not c.get("ambiguous") and c.get("symbol")]
    hype = codes & set(PRESSURE_CODES) | (codes & {"personal_upi"})
    if is_pump(codes):
        return "Pump pattern", "danger"
    if len(codes & set(PRESSURE_CODES)) >= 2 or "personal_upi" in codes or "paid_group" in codes or "funnel" in codes:
        return "Pressure pitch", "danger"
    priced = any(c.get("expected_prices") or c.get("stop_loss") or c.get("price_at_post") for c in claims)
    registered = (card.get("sebi") or {}).get("status") in ("registered", "name_match")
    if priced and not registered:
        return "Unverified tip", "warning"
    if claims and any(c.get("direction") in ("up", "down", "mixed") for c in claims):
        return "Opinion", "info"
    return "Education", "ok"


def build_label(card: dict, text: str = "") -> dict:
    post_prov = (card.get("post") or {}).get("provenance") or config.REAL_LABEL
    warnings = card.get("warnings", [])
    codes = {w["code"] for w in warnings}
    claim = next((c for c in card.get("claims", []) if not c.get("ambiguous") and c.get("symbol")), None)

    # ---- Were they right before?
    tr = card.get("track_record") or {}
    period = tr.get("period") or {}
    span = f" ({period['first']} to {period['last']})" if period.get("first") else ""
    if tr.get("status") == "ok":
        record = _line("record", "Track record", f"{tr['worked']} of {tr['scored']} calls beat the Nifty 50 at 30 days{span}",
                       tr.get("provenance") or post_prov, "ok" if tr.get("hit_rate", 0) >= 0.5 else "warning")
    elif tr.get("status") == "not_enough":
        record = _line("record", "Track record", f"Not enough history ({tr.get('scored', 0)} scored calls; 10 needed)",
                       tr.get("provenance") or post_prov, "info")
    else:
        record = _line("record", "Track record", "Not enough history (no recorded calls from this source)", post_prov, "info")

    # ---- Are they playing fair?
    s = card.get("sebi") or {}
    snap = "" if not (s.get("copy_saved_on") and s.get("list_size")) else (
        f" (list saved {s['copy_saved_on']})" if s.get("status") == "name_not_found"
        else f" (list of {s['list_size']:,} names saved {s['copy_saved_on']})")
    sebi_text = s.get("short") or "Not checked"
    sebi_line = _line("sebi", "SEBI registration", f"{sebi_text}{snap}", post_prov,
                      "ok" if s.get("status") == "registered" and s.get("name_matches") is not False else "warning")

    disclosed = sorted({m.group(0).lower() for m in DISCLOSURE_RE.finditer(text or "")})[:3]
    disclosure = _line("disclosure", "Conflict disclosure",
                       "Discloses a position or interest" if disclosed else "No disclosure in the post",
                       post_prov, "ok" if disclosed else "warning", disclosed)

    pressure = [c for c in PRESSURE_CODES if c in codes]
    pressure_line = _line("pressure", "Pressure signals",
                          f"{len(pressure)}: {', '.join(PRESSURE_NAMES[c] for c in pressure)}" if pressure else "0",
                          post_prov, "danger" if pressure else "ok",
                          [e for w in warnings if w["code"] in pressure for e in w.get("evidence", [])][:4])

    ids = (card.get("payments") or {}).get("upi_ids") or []
    personal = [u["id"] for u in ids if not u.get("validated_format")]
    valid = [u["id"] for u in ids if u.get("validated_format")]
    if personal:
        pay = _line("payment", "Payment route", "Personal UPI ID, not a SEBI-validated @valid handle", post_prov, "danger", personal)
    elif valid:
        pay = _line("payment", "Payment route", "@valid handle: check it on SEBI's own service", post_prov, "info", valid)
    else:
        pay = _line("payment", "Payment route", "No payment requested", post_prov, "ok")

    m = (claim or {}).get("market") or {}
    after = ((claim or {}).get("after_post") or {}).get("horizons", {}).get("30") or {}
    if not claim or not m:
        pump = _line("pump", "Pump pattern", "No NSE or BSE stock with prices to check", post_prov, "info")
    else:
        bits = []
        if m.get("spike_ratio") is not None:
            bits.append(f"volume {m['spike_ratio']:.1f}x its 20-day average before the post")
        if after.get("status") == "scored":
            bits.append(f"{_pct(after['excess_return'])} points vs the Nifty 50 over 30 days after")
        detail = "; ".join(bits) if bits else "not enough price history"
        if is_pump(codes):
            pump = _line("pump", "Pump pattern", f"Seen: {detail}", config.REAL_LABEL, "danger")
        elif "volume_spike" in codes:
            pump = _line("pump", "Pump pattern", f"Partly seen (unusual volume only): {detail}", config.REAL_LABEL, "warning")
        else:
            pump = _line("pump", "Pump pattern", f"Not seen: {detail}", config.REAL_LABEL, "ok")

    fair = [sebi_line, disclosure, pressure_line, pay, pump]
    if claim and m.get("avg_traded_value_20d") is not None:
        crore = m["avg_traded_value_20d"] / 1e7
        thin = "thin_trading" in codes
        fair.append(_line("liquidity", "Liquidity", f"₹{crore:,.2f} crore traded a day (20 sessions before the post)"
                          + ("; thinly traded" if thin else ""), config.REAL_LABEL, "warning" if thin else "info"))
    surv = surveillance.check((claim or {}).get("symbol"), (claim or {}).get("exchange") or "NSE") if claim else None
    if surv is not None:
        if not surv["checked"]:
            value, tone = "BSE stock: NSE's surveillance lists do not cover it", "info"
        elif surv["entries"]:
            value = "Under NSE surveillance: " + "; ".join(
                f"{e['measure']} {e['stage']} (as of {e['as_of']})" for e in surv["entries"][:3])
            tone = "warning"
        else:
            value, tone = f"Not on NSE's ASM, GSM or ESM lists (snapshot {surv['as_of']})", "ok"
        fair.append(_line("surveillance", "Exchange surveillance", value, config.REAL_LABEL, tone))
    if "education_loophole" in codes:
        posted = (card.get("post") or {}).get("posted_on")
        rule = posted and dt.date.fromisoformat(posted) >= EDU_RULE_FROM
        edu = _line("education", "'Educational' label",
                    "Calls itself educational but names current price levels"
                    + ("; SEBI's 30-day price-data lag for education applies" if rule else ""),
                    post_prov, "warning")
        if not rule:
            edu["why"] = "Calling a post 'educational' while giving price levels for a named stock is a known way around SEBI's rules."
        fair.append(edu)

    kind, tone = message_type(card)
    case = card.get("case")
    if case:  # a real SEBI case: the order and the computed price facts replace the post-based lines
        f = case.get("facts") or {}
        why = f"{case['order']}. Sources: " + "; ".join(x["label"] for x in case.get("sources", []))
        order = _line("order", "SEBI order", case["summary"], config.REAL_LABEL, "danger")
        order["why"] = why
        listing = _line("listing", "Exchange", case["listing"], config.REAL_LABEL, "info")
        listing["why"] = "An NSE-only tool cannot see this stock; FinProof falls back to BSE prices."
        pump = _line("pump", "Pump pattern", " ".join(f.get("lines", [])) or "Not enough data", config.REAL_LABEL, "danger")
        pump["why"] = why
        fair = [order, listing, pump]
        kind, tone = "Pump pattern (SEBI case)", "danger"
    out = {"title": TITLE, "note": NOTE,
            "message_type": _line("type", "Message type", kind, post_prov, tone),
            "right_before": {"title": "Were they right before?", "lines": [record]},
            "fair": {"title": "Are they playing fair?", "lines": fair},
            "media_codes": [c for c in media.MEDIA_CODES if c in codes]}
    from .card import wording_problems  # the label goes through the same no-advice check as the card
    bad = wording_problems(out)
    if bad:
        raise ValueError(f"advice wording in label: {bad}")
    return out
