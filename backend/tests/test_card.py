"""The card must never tell anyone what to buy or sell."""

import datetime as dt

import pandas as pd
import pytest

from conftest import FakePrices, make_df
from finproof import config, sebi
from finproof.card import ADVICE_RE, DIRECTION_TEXT, DISCLAIMER, PRESSURE_TEXT, build_card, wording_problems
from finproof.ledger import Ledger
from finproof.market import nse_companies

SAMPLES = [
    "BUY SBIN CMP 780 TGT 820/850 SL 760. Sure shot, buy now!",
    "Sell HDFCBANK, strong sell, exit all positions, hold cash",
    "BUY TATAMOTORS CMP 650 TGT 700 SL 620, 100% guaranteed, join VIP group t.me/abc",
    "SEBI registered INH999999999. Accumulate RELIANCE, target price 3000, safe stock, must buy",
    "Tata looks strong, don't sell",
    "the market will open high today",
    "",
]


@pytest.fixture
def prices():
    nifty = make_df([100.0] * 400, start="2024-06-03")
    stock = make_df([50.0] * 395 + [80.0] * 5, volumes=[1000.0] * 395 + [50_000.0] * 5, start="2024-06-03")
    frames = {config.BENCHMARK: nifty}
    for sym in ("SBIN", "HDFCBANK", "TMPV", "RELIANCE"):
        frames[sym] = stock
    return FakePrices(frames)


@pytest.mark.parametrize("text", SAMPLES)
def test_cards_never_contain_advice(text, prices):
    card = build_card(text=text, ledger=Ledger(prices, tips=[]), prices=prices,
                      posted_on=dt.date(2025, 12, 29), posted_on_note="test")
    assert wording_problems(card) == []


def test_fixed_wording_is_clean():
    for s in [DISCLAIMER, *DIRECTION_TEXT.values(), *PRESSURE_TEXT.values()]:
        assert not ADVICE_RE.search(s), s


def test_guard_catches_advice_but_ignores_quotes():
    assert wording_problems({"text": "You should buy this"}) == ["You should buy this"]
    assert wording_problems({"evidence": ["buy now"]}) == []


def test_no_nse_symbol_is_an_advice_word():
    bad = [s for s in nse_companies()["SYMBOL"] if ADVICE_RE.fullmatch(s.lower())]
    assert bad == []


def _registry(complete: bool) -> sebi.Registry:
    listed = 1 if complete else 2404
    return sebi.Registry(
        pd.DataFrame([{"name": "Asha Research", "reg_no": "INH000000001", "category": "RA", "validity": ""}]),
        saved_on="2026-11-20", coverage={"RA": {"saved": 1, "listed": listed}})


def _card(text, prices):
    return build_card(text=text, ledger=Ledger(prices, tips=[]), prices=prices,
                      posted_on=dt.date(2025, 12, 29), posted_on_note="test")


def test_unknown_sebi_number_is_flagged_with_a_complete_list(prices, monkeypatch):
    monkeypatch.setattr(sebi, "load_registry", lambda: _registry(complete=True))
    codes = {w["code"] for w in _card("SEBI registered INH999999999. BUY SBIN", prices)["warnings"]}
    assert "not_on_sebi_list" in codes and "unverified_sebi_claim" in codes


def test_incomplete_list_raises_no_sebi_warning(prices, monkeypatch):
    monkeypatch.setattr(sebi, "load_registry", lambda: _registry(complete=False))
    card = _card("SEBI registered INH999999999. BUY SBIN", prices)
    codes = {w["code"] for w in card["warnings"]}
    assert not codes & {"not_on_sebi_list", "unverified_sebi_claim"}
    assert "incomplete" in card["sebi"]["text"]


def test_direction_from_named_price(prices):
    # SBIN closes at 80 before the post; a named price of 100 means the post expects a rise.
    card = _card("SBIN target 100", prices)
    sbin = card["claims"][0]
    assert sbin["direction"] == "up" and sbin["direction_note"]


def test_negated_post_is_not_given_a_direction(prices):
    card = _card("Don't touch SBIN, target 100", prices)
    assert card["claims"][0]["direction"] == "unclear"


def test_market_warnings_show_up(prices):
    card = build_card(text="BUY SBIN", ledger=Ledger(prices, tips=[]), prices=prices,
                      posted_on=dt.date(2025, 12, 29), posted_on_note="test")
    codes = {w["code"] for w in card["warnings"]}
    assert {"volume_spike", "thin_trading"} <= codes
