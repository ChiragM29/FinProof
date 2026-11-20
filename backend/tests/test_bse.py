"""BSE fallback: NSE first, BSE (.BO) when NSE has no data or the post says BSE:<SYMBOL>, and the BSE Ltd clash."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from conftest import FakePrices, make_df
from finproof import api, config, extract
from finproof.card import build_card
from finproof.chart import chart_payload
from finproof.ledger import Ledger
from finproof.market import YahooPrices, exchange_of, split_exchange, yahoo_ticker


def write(cache, name, close):
    make_df([close] * 300, volumes=[1000.0] * 300, start="2024-01-01").to_csv(cache / name)


@pytest.fixture
def cache(tmp_path):
    write(tmp_path, "^NSEI.csv".replace("^", "_"), 100.0)  # Nifty 50 cache name: _NSEI.csv
    return tmp_path


def test_prefix_and_tickers():
    assert split_exchange("BSE:CRYSTAL") == ("CRYSTAL", "BSE") and split_exchange("bse: 540821") == ("540821", "BSE")
    assert split_exchange("BSE") == ("BSE", None)  # bare BSE is the company BSE Ltd
    assert yahoo_ticker("BSE:CRYSTAL") == "CRYSTAL.BO" and yahoo_ticker("ITC") == "ITC.NS" and yahoo_ticker("BSE") == "BSE.NS"


def test_nse_first_then_bse_fallback_offline(cache):
    write(cache, "ABCX_NS.csv", 50.0)
    write(cache, "ABCX_BO.csv", 51.0)
    write(cache, "ONLYBSE_BO.csv", 7.0)
    prices = YahooPrices(cache_dir=cache, offline=True)
    nse = prices.history("ABCX")
    assert nse.attrs["exchange"] == "NSE" and float(nse["Close"].iloc[-1]) == 50.0  # NSE first
    bse = prices.history("ONLYBSE")
    assert bse.attrs["exchange"] == "BSE" and float(bse["Close"].iloc[-1]) == 7.0     # not on NSE: BSE
    forced = prices.history("BSE:ABCX")
    assert forced.attrs["exchange"] == "BSE" and float(forced["Close"].iloc[-1]) == 51.0  # prefix wins
    assert prices.history("NOWHERE").empty
    assert [exchange_of(prices, s) for s in ("ABCX", "ONLYBSE", "BSE:ABCX", "^NSEI")] == ["NSE", "BSE", "BSE", "INDEX"]


def test_extraction_reads_the_prefix_and_the_bse_ltd_clash():
    syms = lambda t: [c.symbol for c in extract.extract(t).claims]  # noqa: E731
    assert syms("BSE:CRYSTAL breakout soon") == ["BSE:CRYSTAL"]
    assert syms("Check BSE: 540821 today") == ["BSE:540821"]
    assert syms("#BSE looks strong") == ["BSE"] and syms("BSE Ltd shares are up") == ["BSE"]
    assert syms("BSE Sensex fell 300 points; listed on NSE and BSE") == []  # the exchange, not the company


def test_card_and_chart_say_which_exchange(cache):
    write(cache, "ONLYBSE_BO.csv", 7.0)
    prices = YahooPrices(cache_dir=cache, offline=True)
    card = build_card(text="BSE:ONLYBSE breakout, target 9", ledger=Ledger(prices, tips=[]), prices=prices,
                      posted_on=dt.date(2024, 9, 2), posted_on_note="t")
    claim = card["claims"][0]
    assert claim["symbol"] == "BSE:ONLYBSE" and claim["exchange"] == "BSE" and claim["market"]["status"] == "ok"
    data = chart_payload("BSE:ONLYBSE", prices)
    assert data["exchange"] == "BSE" and data["label"] == "ONLYBSE" and len(data["candles"]) == 300


def test_api_chart_accepts_bse_symbols(cache, monkeypatch):
    write(cache, "ONLYBSE_BO.csv", 7.0)
    prices = YahooPrices(cache_dir=cache, offline=True)
    monkeypatch.setattr(api, "PRICES", prices)
    monkeypatch.setattr(api, "LEDGER", Ledger(prices, tips=[]))
    client = TestClient(api.app)
    r = client.get("/api/chart/BSE:ONLYBSE")
    assert r.status_code == 200 and r.json()["exchange"] == "BSE"
    card = client.post("/api/analyze", json={"text": "BSE:ONLYBSE breakout, target 9", "posted_on": "2024-09-02"}).json()
    assert card["claims"][0]["exchange"] == "BSE"


def test_fake_prices_default_to_nse():
    prices = FakePrices({"ITC": make_df([1.0] * 5)})
    assert exchange_of(prices, "ITC") == "NSE" and exchange_of(prices, "BSE:ITC") == "BSE"
    assert config.REAL_LABEL == "REAL"
