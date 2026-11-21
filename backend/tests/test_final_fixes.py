"""Final fixes before judging: a complete SEBI list, number-first SEBI checks, no stale chart, better stock finding."""

import datetime as dt
from pathlib import Path

import pandas as pd
import pytest

from conftest import FakePrices, make_df
from finproof import config, extract, sebi
from finproof.card import build_card
from finproof.ledger import Ledger

DASH = Path(__file__).resolve().parents[2] / "dashboard"


@pytest.fixture
def prices():
    nifty = make_df([100.0] * 400, start="2024-06-03")
    stock = make_df([50.0] * 400, volumes=[1000.0] * 400, start="2024-06-03")
    return FakePrices({"^NSEI": nifty, "SBIN": stock})

FULL = sebi.Registry(
    pd.DataFrame([
        {"name": "Asha Market Research Private Limited", "reg_no": "INH000000001", "category": "RA", "validity": ""},
        {"name": "Ravi Kumar", "reg_no": "INA000000002", "category": "IA", "validity": ""},
    ]),
    saved_on="2026-11-21",
    coverage={"RA": {"saved": 1, "listed": 1}, "IA": {"saved": 1, "listed": 1}},
)


# ---------------------------------------------------------------- 1a: the saved SEBI list is (nearly) complete
def test_saved_sebi_lists_hold_at_least_90_percent_of_what_sebi_states():
    sebi.load_registry.cache_clear()
    reg = sebi.load_registry()
    assert reg.saved_on and set(reg.coverage) == {"RA", "IA"}
    for cat, cov in reg.coverage.items():
        rows = int((reg.entries["category"] == cat).sum())
        assert cov["listed"] > 0 and rows >= 0.9 * cov["listed"], (cat, rows, cov)
        assert cov["saved"] == rows
    assert reg.complete
    assert reg.entries["reg_no"].str.fullmatch(r"IN[AH]\d{9}").mean() > 0.99


# ---------------------------------------------------------------- 1b: number first, then name ("possible match" only)
def test_registered_number_and_matching_channel():
    r = sebi.check(["INH000000001"], "Asha Market Research", FULL, found_in={"INH000000001": "description"})
    assert r.status == "registered" and r.name_matches is True
    assert "Shows INH000000001 in the description → registered to Asha Market Research Private Limited" in r.text
    assert "matches this channel" in r.text


def test_registered_number_used_by_a_different_channel():
    r = sebi.check(["INH000000001"], "Stock Rocket Calls", FULL)
    assert r.status == "registered" and r.name_matches is False
    assert "doesn't match this channel (Stock Rocket Calls)" in r.text


def test_number_not_on_a_complete_list():
    r = sebi.check(["INH999999999"], None, FULL)
    assert r.status == "number_not_found" and r.text == "Shows INH999999999 → not in SEBI's list (saved 2026-11-21)."


def test_no_number_and_no_name_match_states_the_list_size_and_date():
    r = sebi.check([], "Stock Rocket Calls", FULL, where="the video title, description or transcript")
    assert r.status == "name_not_found"
    assert r.text == ("No SEBI registration number in the video title, description or transcript, and the name doesn't "
                      "match any of 2 registered analysts and advisers (list saved 2026-11-21).")


def test_a_name_match_is_only_ever_a_possible_match():
    r = sebi.check([], "Asha Market Research", FULL)
    assert r.status == "name_match" and r.text.count("Possible match by name only") == 1
    assert "verified" not in (r.text + r.short).lower()


def test_youtube_card_says_where_the_number_was_found(prices, monkeypatch):
    monkeypatch.setattr(sebi, "load_registry", lambda: FULL)
    parts = {"title": "SBIN results explained", "description": "Research by Asha. SEBI RA INH000000001", "transcript": ""}
    card = build_card(text="\n".join(parts.values()), ledger=Ledger(prices, tips=[]), prices=prices,
                      posted_on=dt.date(2025, 12, 29), posted_on_note="t", kind="youtube", channel="Asha Market Research",
                      text_parts=parts)
    assert card["sebi"]["status"] == "registered" and card["sebi"]["found_in"] == "description"


def test_unregistered_name_alone_is_not_a_warning(prices, monkeypatch):
    monkeypatch.setattr(sebi, "load_registry", lambda: FULL)
    card = build_card(text="BUY SBIN now", ledger=Ledger(prices, tips=[]), prices=prices,
                      posted_on=dt.date(2025, 12, 29), posted_on_note="t", channel="Stock Rocket Calls")
    assert card["sebi"]["status"] == "name_not_found"
    assert "not_on_sebi_list" not in {w["code"] for w in card["warnings"]}


# ---------------------------------------------------------------- 1c: no stale chart
def test_a_scan_without_a_stock_clears_the_chart():
    js = (DASH / "cc.js").read_text(encoding="utf-8")
    assert "This post doesn't name a stock we could match on NSE or BSE." in js
    run = js[js.index("async function runScan"):js.index("function showRestricted")]
    assert "clearChart(" in run and "else {" in run


# ---------------------------------------------------------------- 1d: company names, where found, ambiguous names
def test_company_names_map_to_nse_symbols():
    syms = lambda t: [c.symbol for c in extract.extract(t).claims if not c.ambiguous]  # noqa: E731
    assert syms("Reliance Industries results analysis") == ["RELIANCE"]
    assert syms("HDFC Bank share price explained") == ["HDFCBANK"]


def test_group_names_list_candidates_instead_of_guessing():
    c = extract.extract("Why Tata stocks are falling").claims[0]
    assert c.ambiguous and c.symbol is None and len(c.candidates) >= 2


def test_card_says_which_part_of_the_video_named_the_stock(prices):
    parts = {"title": "SBIN quarterly results", "description": "Links below", "transcript": "today we look at the bank"}
    card = build_card(text="\n".join(parts.values()), ledger=Ledger(prices, tips=[]), prices=prices,
                      posted_on=dt.date(2025, 12, 29), posted_on_note="t", kind="youtube", text_parts=parts)
    sbin = next(c for c in card["claims"] if c["symbol"] == "SBIN")
    assert sbin["found_in"] == "title"


def test_plain_posts_have_no_found_in(prices):
    card = build_card(text="BUY SBIN now", ledger=Ledger(prices, tips=[]), prices=prices,
                      posted_on=dt.date(2025, 12, 29), posted_on_note="t")
    assert card["claims"][0]["found_in"] is None and config.REAL_LABEL == "REAL"
