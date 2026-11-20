import datetime as dt

from conftest import FakePrices, make_df
from finproof.pumpdump import market_signals


def test_volume_spike_run_up_and_fall_after():
    closes = [10.0] * 80 + [10 + i for i in range(1, 21)] + [30.0] * 5 + [15.0] * 40
    volumes = [10_000.0] * 95 + [100_000.0] * 5 + [10_000.0] * 45
    df = make_df(closes, volumes=volumes)
    post_day = df.index[100].date()
    sig = market_signals("X", post_day, FakePrices({"X": df}))
    assert sig.status == "ok"
    assert sig.volume_ratio == 10.0
    assert {"volume_spike", "run_up", "thin_trading", "fell_after"} <= set(sig.flags)


def test_quiet_large_stock_has_no_flags():
    df = make_df([2000.0] * 200, volumes=[5_000_000.0] * 200)
    sig = market_signals("BIG", df.index[150].date(), FakePrices({"BIG": df}))
    assert sig.flags == []


def test_too_little_history():
    df = make_df([10.0] * 15)
    assert market_signals("X", df.index[10].date(), FakePrices({"X": df})).status == "too_little_history"


def test_unknown_stock():
    assert market_signals("NONE", dt.date(2025, 1, 1), FakePrices({})).status == "no_data"
