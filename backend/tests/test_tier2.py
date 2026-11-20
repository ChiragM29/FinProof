"""Tier 2: exchange surveillance (dated NSE snapshot), the liquidity fact, and 7/30-day journal outcomes."""

import datetime as dt

from conftest import FakePrices, make_df
from finproof import config, journal, label, surveillance
from finproof.card import ADVICE_RE, build_card, wording_problems
from finproof.ledger import Ledger


def test_snapshot_is_dated_and_indexed_by_symbol():
    snap = surveillance.snapshot()
    assert snap["file"].startswith("nse_surveillance_") and snap["as_of"]
    assert sum(len(v) for v in snap["index"].values()) > 100
    some = next(iter(snap["index"]))
    entry = surveillance.check(some)["entries"][0]
    assert entry["measure"] and entry["as_of"]
    assert surveillance.check("XYZ", "BSE") == {"checked": False, "entries": [], "as_of": snap["as_of"]}


def card_for(symbol, text):
    frame = make_df([100.0] * 400, volumes=[2_000_000.0] * 400, start="2024-06-03")
    prices = FakePrices({config.BENCHMARK: frame, symbol: frame})
    return build_card(text=text, ledger=Ledger(prices, tips=[]), prices=prices, posted_on=dt.date(2025, 6, 2), posted_on_note="t")


def test_label_shows_surveillance_and_liquidity_as_facts():
    from finproof.market import nse_companies
    on_nse = set(nse_companies()["SYMBOL"])
    listed = next(s for s, v in surveillance.snapshot()["index"].items() if v and s in on_nse and s.isalpha() and len(s) >= 4)
    lab = label.build_label(card_for(listed, f"#{listed} breakout, CMP 100 TGT 130"))
    keys = {l["key"]: l for l in lab["fair"]["lines"]}
    assert keys["surveillance"]["value"].startswith("Under NSE surveillance") and "as of" in keys["surveillance"]["value"]
    assert keys["surveillance"]["tone"] == "warning"
    lab = label.build_label(card_for("ITC", "ITC CMP 100 TGT 130"))
    keys = {l["key"]: l for l in lab["fair"]["lines"]}
    assert keys["liquidity"]["value"].startswith("₹20.00 crore traded a day") and keys["liquidity"]["provenance"] == "REAL"
    assert keys["surveillance"]["provenance"] == "REAL"
    assert keys["surveillance"]["value"].startswith(("Not on NSE's ASM, GSM or ESM lists (snapshot", "Under NSE surveillance"))
    assert wording_problems(lab) == []


def test_journal_reports_7_and_30_days():
    frame = make_df([100.0 + i * 0.5 for i in range(400)], start="2024-06-03")
    prices = FakePrices({config.BENCHMARK: make_df([100.0] * 400, start="2024-06-03"), "SBIN": frame})
    out = journal.summarize([{"symbol": "SBIN", "direction": "up", "posted_on": "2025-01-06", "decision": "skipped"}], prices)
    row = out["rows"][0]
    assert row["vs_nifty_7d"] is not None and row["vs_nifty_in_claimed_direction"] is not None
    assert row["vs_nifty_7d"] < row["vs_nifty_in_claimed_direction"]  # a steady rise: more by day 30 than day 7
    assert not any(ADVICE_RE.search(g["text"]) for g in out["groups"].values())
