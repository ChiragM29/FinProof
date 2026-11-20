"""Technical indicators: exact math on hand-worked series, short-series edge cases, point-in-time
snapshots, the chart payload, and neutral (no-advice) wording."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from conftest import FakePrices, make_df
from finproof import api, config, indicators as ind
from finproof.card import ADVICE_RE
from finproof.ledger import Ledger
from finproof.veteran import EXTRA_RE

approx = pytest.approx


def linear(n, start=1.0):
    return [start + i for i in range(n)]


# ---------------------------------------------------------------- SMA 20 / EMA 50
def test_sma():
    assert ind.sma([1, 2, 3, 4, 5], 3) == [None, None, 2, 3, 4]
    s = ind.sma(linear(25), 20)
    assert s[18] is None and s[19] == approx(10.5) and s[24] == approx(15.5)


def test_ema_is_seeded_with_the_sma():
    assert ind.ema([10, 11, 12, 13, 20], 3) == [None, None, approx(11), approx(12), approx(16)]


def test_ema_50_on_a_straight_line_lags_by_24_5():
    e = ind.ema(linear(60), 50)  # alpha = 2/51: steady lag (1 - alpha) / alpha = 24.5
    assert e[48] is None and e[49] == approx(25.5) and e[50] == approx(26.5) and e[59] == approx(35.5)


# ---------------------------------------------------------------- VWAP (20D)
def test_rolling_vwap():
    h, l, c, v = [12, 15, 14], [8, 9, 10], [10, 12, 12], [100, 300, 100]
    assert ind.rolling_vwap(h, l, c, v, 2) == [None, approx(11.5), approx(12.0)]  # (10*100 + 12*300) / 400
    assert ind.rolling_vwap(h, l, c, [0, 0, 0], 2) == [None, None, None]  # no volume: no VWAP


def test_vwap_20_uses_exactly_20_sessions():
    n = 25
    out = ind.rolling_vwap([11.0] * n, [9.0] * n, [10.0] * n, [1000.0] * n, 20)
    assert out[18] is None and out[19] == approx(10.0)


# ---------------------------------------------------------------- Bollinger (20, 2)
def test_bollinger_uses_population_standard_deviation():
    mid, up, lo = ind.bollinger([1, 2, 3, 4, 5], 5, 2)
    assert mid[4] == approx(3) and up[4] == approx(3 + 2 * 2 ** 0.5) and lo[4] == approx(3 - 2 * 2 ** 0.5)
    assert mid[3] is up[3] is lo[3] is None


def test_bollinger_20_2_on_a_flat_series_has_zero_width():
    mid, up, lo = ind.bollinger([50.0] * 20)
    assert mid[19] == up[19] == lo[19] == approx(50.0)


# ---------------------------------------------------------------- RSI (14)
def test_rsi_wilder_smoothing():
    out = ind.rsi([10, 11, 10, 12, 11], 3)  # changes +1 -1 +2 -1
    assert out[:3] == [None, None, None]
    assert out[3] == approx(75.0)                    # gain 1, loss 1/3
    assert out[4] == approx(100 - 100 / 2.2)         # gain 2/3, loss 5/9


def test_rsi_14_edge_cases():
    assert ind.rsi(linear(14)) == [None] * 14         # 13 changes: not enough
    up = ind.rsi(linear(20))
    assert up[13] is None and up[14] == 100.0 and up[19] == 100.0  # no losses at all
    assert ind.rsi([5.0] * 20)[19] == 50.0            # no movement at all
    assert ind.rsi(linear(20, 100)[::-1])[19] == 0.0  # only losses


# ---------------------------------------------------------------- MACD (12, 26, 9)
def test_macd_on_a_straight_line():
    line, sig, hist = ind.macd(linear(60))  # lags 5.5 and 12.5 -> MACD 7, signal 7, histogram 0
    assert line[24] is None and line[25] == approx(7.0) and line[59] == approx(7.0)
    assert sig[32] is None and sig[33] == approx(7.0)
    assert hist[33] == approx(0.0) and hist[32] is None


def test_macd_short_series():
    line, sig, hist = ind.macd(linear(30))
    assert line[25] == approx(7.0) and all(x is None for x in sig) and all(x is None for x in hist)


# ---------------------------------------------------------------- ATR (14)
def test_true_range_and_atr():
    h, l, c = [10, 12, 11, 13], [8, 9, 10, 10], [9, 11, 10.5, 12]
    assert ind.true_range(h, l, c) == [2, 3, 1, 3]
    assert ind.atr(h, l, c, 3) == [None, None, approx(2.0), approx(7 / 3)]
    assert ind.true_range([12], [11], [11.5]) == [1]
    assert ind.true_range([10, 12], [8, 11], [9, 11.5])[1] == 3  # gap up: from the previous close


def test_atr_14_needs_14_sessions():
    n = 14
    assert ind.atr([11.0] * (n - 1), [9.0] * (n - 1), [10.0] * (n - 1)) == [None] * (n - 1)
    out = ind.atr([11.0] * n, [9.0] * n, [10.0] * n)
    assert out[12] is None and out[13] == approx(2.0)


# ---------------------------------------------------------------- key levels and the 20D volume average
def test_key_levels():
    highs, lows = linear(40), linear(40, 0)
    dates = [f"d{i}" for i in range(40)]
    lv = ind.key_levels(highs, lows, dates)
    assert lv["high_30d"] == 40 and lv["high_30d_date"] == "d39" and lv["low_30d"] == 10 and lv["low_30d_date"] == "d10"
    assert lv["high_52w"] is None and lv["low_52w"] is None  # not enough history
    long = ind.key_levels(linear(300), linear(300, 0))
    assert long["high_52w"] == 300 and long["low_52w"] == 48  # last 252 sessions: lows 48..299
    short = ind.key_levels([5, 6], [4, 5])
    assert short["high_30d"] is None and short["sessions"] == 2


def test_volume_average_excludes_the_day_itself():
    out = ind.prior_mean(linear(25), 20)
    assert out[19] is None and out[20] == approx(10.5) and out[24] == approx(14.5)


# ---------------------------------------------------------------- snapshot, chart payload and wording
def wavy(n=320, start="2024-01-01"):
    closes = [100 + 10 * ((i % 17) / 17) + i * 0.05 for i in range(n)]
    return make_df(closes, volumes=[1_000_000.0 + (i % 7) * 50_000 for i in range(n)], start=start,
                   highs=[c * 1.01 for c in closes], lows=[c * 0.99 for c in closes])


def test_snapshot_uses_only_sessions_before_the_post():
    df = wavy()
    post = df.index[300].date()
    a = ind.snapshot(df, post)
    changed = df.copy()
    changed.iloc[300:, :] = changed.iloc[300:, :] * 3  # the future is different
    assert ind.snapshot(changed, post) == a
    assert a["as_of"] == df.index[299].date().isoformat()
    assert a["close"] == round(float(df["Close"].iloc[299]), 2)
    assert a["dist_sma20"] == round(a["close"] / a["sma20"] - 1, 4)
    assert a["atr14_pct"] == approx(a["atr14"] / a["close"], abs=1e-4)


def test_snapshot_needs_20_sessions():
    df = wavy(30)
    assert ind.snapshot(df, df.index[15].date()) is None
    assert ind.snapshot(df, df.index[25].date()) is not None


def test_every_explanation_and_fact_is_neutral():
    texts = list(ind.EXPLAIN.values())
    for n in (40, 120, 320):
        for shape in (1, -1):
            closes = [100 + shape * i * 0.8 for i in range(n)]
            df = make_df(closes, start="2024-01-01", highs=[c * 1.02 for c in closes], lows=[c * 0.98 for c in closes])
            texts += [f["text"] for f in ind.snapshot(df, dt.date(2030, 1, 1))["facts"]]
    assert len(texts) > 20
    for t in texts:
        assert not ADVICE_RE.search(t) and not EXTRA_RE.search(t), t
        for word in ("overbought", "oversold", "bullish", "bearish", "signal to"):
            assert word not in t.lower(), t


def test_rsi_words_are_descriptive():
    assert ind.rsi_words(76.2) == "a rapid recent climb"
    assert ind.rsi_words(25) == "a rapid recent drop"
    assert ind.rsi_words(50) == "no extreme reading"


@pytest.fixture
def client(monkeypatch):
    prices = FakePrices({config.BENCHMARK: make_df([100.0] * 320, start="2024-01-01"), "SBIN": wavy()})
    monkeypatch.setattr(api, "PRICES", prices)
    monkeypatch.setattr(api, "LEDGER", Ledger(prices, tips=[]))
    return TestClient(api.app)


def test_chart_payload_carries_aligned_indicators(client):
    data = client.get("/api/chart/SBIN").json()
    n = len(data["candles"])
    assert set(data["indicators"]) >= {"sma20", "ema50", "vwap20", "bb_upper", "bb_lower", "rsi14", "macd",
                                       "macd_signal", "macd_hist", "atr14_pct", "vol_avg20"}
    assert all(len(v) == n for v in data["indicators"].values())
    assert data["indicators"]["sma20"][19] is not None and data["indicators"]["sma20"][18] is None
    assert data["levels"]["high_52w"] is not None and set(data["explain"]) == set(ind.EXPLAIN)


def test_chart_key_levels_can_stop_before_the_post(client):
    full = client.get("/api/chart/SBIN").json()
    day = full["candles"][200]["time"]
    lv = client.get(f"/api/chart/SBIN?levels_before={day}").json()["levels"]
    assert lv["as_of"] == full["candles"][199]["time"] and lv["sessions"] == 200
    assert lv["high_30d"] == max(c["high"] for c in full["candles"][170:200])


def test_point_in_time_cards_carry_indicators_that_ignore_the_future():
    """Study cards (point_in_time=True) get the same pre-post snapshot whatever happened after the post."""
    from finproof.card import build_card

    base = wavy()
    post = base.index[300].date()
    later = base.copy()
    later.iloc[300:, :] = later.iloc[300:, :] * 2
    techs = []
    for df in (base, later):
        prices = FakePrices({config.BENCHMARK: make_df([100.0] * 320, start="2024-01-01"), "SBIN": df})
        card = build_card(text="BUY SBIN TGT 150", ledger=Ledger(prices, tips=[]), prices=prices, posted_on=post,
                          posted_on_note="t", point_in_time=True)
        techs.append(card["claims"][0]["technicals"])
    assert techs[0] == techs[1] and techs[0]["as_of"] < post.isoformat()
