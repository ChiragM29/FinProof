"""Price History mode: a bare Nifty 50 ticker or company name (or BSE:<SYMBOL>) opens that stock's chart with a
neutral, past-only overview. There is no post, so there is nothing to flag and no warning is ever raised.

(Named "Price History", not "research": in SEBI's rules research is regulated work that needs registration.)
"""

from __future__ import annotations

import datetime as dt
import re
from functools import lru_cache

import pandas as pd

from . import config, indicators
from .card import DISCLAIMER, wording_problems
from .market import company_name, current_symbol, display_symbol, exchange_of, nse_companies, split_exchange

NOTE = "Price History: past prices only. No post, so nothing to judge and no flags."


@lru_cache(maxsize=1)
def nifty50() -> list[dict]:
    """The 50 Nifty 50 companies from NSE's own constituents file in data/real (dated in its name)."""
    files = sorted(config.REAL.glob("nifty50_constituents_*.csv"))
    if not files:
        return []
    df = pd.read_csv(files[-1])
    as_of = files[-1].stem.rsplit("_", 1)[-1]
    return [{"symbol": str(s).strip().upper(), "name": str(n).strip(), "industry": str(i).strip(), "as_of": as_of,
             "provenance": config.REAL_LABEL} for s, n, i in zip(df["Symbol"], df["Company Name"], df["Industry"])]


def _norm(text: str) -> str:
    text = re.sub(r"\b(?:ltd|limited|the|co|company|corporation|india)\b\.?", " ", text.lower().replace("&", " and "))
    return re.sub(r"[^a-z0-9]+", "", text)


def resolve(query: str) -> str | None:
    """The symbol for a bare ticker or company name typed into the scanner, or None if it is not one."""
    q = (query or "").strip()
    if not q or len(q) > 60 or "\n" in q:
        return None
    bare, exchange = split_exchange(q)
    if exchange == "BSE":
        return f"BSE:{bare}" if re.fullmatch(r"[A-Z0-9&\-]{2,20}", bare) else None
    upper = q.upper()
    listed = set(nse_companies()["SYMBOL"])
    if any(r["symbol"] == upper for r in nifty50()) or upper in listed:
        return current_symbol(upper)
    key = _norm(q)
    if len(key) < 3:
        return None
    exact = [r["symbol"] for r in nifty50() if _norm(r["name"]) == key]
    if exact:
        return exact[0]
    prefix = [r["symbol"] for r in nifty50() if len(key) >= 5 and _norm(r["name"]).startswith(key)]
    if len(prefix) == 1:  # "Bajaj" alone matches three companies: not a bare name, so no guess
        return prefix[0]
    names = nse_companies()
    hits = [s for s, n in zip(names["SYMBOL"], names["NAME"]) if _norm(n) == key]
    return hits[0] if len(hits) == 1 else None


def _pct(x: float) -> str:
    return f"{round(float(x) * 100, 1):+.1f}%"


def build(symbol: str, prices) -> dict | None:
    """A card-shaped object (so the Claim Auditor can still answer and refuse), with no warnings at all."""
    df = prices.history(symbol)
    if df.empty or len(df) < 21:
        return None
    df = df.dropna(subset=["Close"])
    nifty = prices.history(config.BENCHMARK).dropna(subset=["Close"]) if not prices.history(config.BENCHMARK).empty else None
    last_day = df.index[-1].date()
    close = float(df["Close"].iloc[-1])
    facts = [f"Last close ₹{close:,.2f} on {last_day.isoformat()} ({_pct(close / float(df['Close'].iloc[-2]) - 1)} on the day)."]

    def change(frame, sessions):
        return float(frame["Close"].iloc[-1]) / float(frame["Close"].iloc[-1 - sessions]) - 1 if len(frame) > sessions else None

    perf = {}
    for label, n in (("30 sessions", 30), ("1 year (252 sessions)", 252)):
        own = change(df, n)
        idx = change(nifty, n) if nifty is not None else None
        if own is not None:
            perf[label] = {"stock": round(own, 4), "nifty": None if idx is None else round(idx, 4)}
            facts.append(f"Over {label}: {display_symbol(symbol)} {_pct(own)}"
                         + (f", Nifty 50 {_pct(idx)}." if idx is not None else "."))
    vol_avg = float(df["Volume"].iloc[-21:-1].mean()) if "Volume" in df else 0.0
    if vol_avg > 0:
        facts.append(f"Latest volume {float(df['Volume'].iloc[-1]) / vol_avg:.1f}× its 20-day average.")
    tech = indicators.snapshot(df, last_day + dt.timedelta(days=1))
    if tech:
        facts += [f["text"] for f in tech.get("facts", []) if f["code"] in ("atr14", "levels", "vwap20")]
    sym_label = display_symbol(symbol)
    exchange = exchange_of(prices, symbol)
    company = company_name(sym_label)
    in_n50 = any(r["symbol"] == symbol for r in nifty50())
    card = {
        "mode": "history", "disclaimer": DISCLAIMER,
        "post": {"kind": "history", "title": None, "channel": None, "link": "", "posted_on": last_day.isoformat(),
                 "posted_on_note": "latest session", "point_in_time": False, "provenance": config.REAL_LABEL, "words": 0},
        "summary": {"warning_count": 0, "text": NOTE},
        "sebi": {"status": "not_checked", "text": "No post, so no SEBI registration to check.", "coverage_text": ""},
        "claims": [{"symbol": symbol, "company": company, "exchange": exchange, "direction": "unclear",
                    "direction_text": "Price History: no post, so no claim.", "expected_prices": [], "stop_loss": None,
                    "price_at_post": None, "ambiguous": False, "mentions": 0, "candidates": [symbol],
                    "matched_text": sym_label, "technicals": tech}],
        "warnings": [], "track_record": {"status": "no_history", "text": "No post, so no source record to check."},
        "payments": None, "media": {"title": "", "note": "", "codes": [], "platform": "history"},
        "data_provenance": [{"what": "Stock prices and volumes", "provenance": config.REAL_LABEL,
                             "source": f"{exchange} prices via Yahoo Finance"}],
        "history": {"symbol": symbol, "label": sym_label, "company": company, "exchange": exchange, "nifty50": in_n50,
                    "as_of": last_day.isoformat(), "facts": facts, "performance": perf, "note": NOTE,
                    "provenance": config.REAL_LABEL},
        "detected": {"platform": "Price History", "tickers": [sym_label], "exchanges": [exchange],
                     "posted_on": last_day.isoformat(), "posted_time": None, "date_how": "latest session",
                     "date_origin": "extracted", "source": "No post", "source_how": "Price History mode",
                     "source_origin": "extracted", "renamed": []},
    }
    problems = wording_problems(card)
    if problems:
        raise ValueError(f"advice wording in price history: {problems}")
    return card
