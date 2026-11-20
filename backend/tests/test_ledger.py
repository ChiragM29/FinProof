import datetime as dt

from conftest import FakePrices, make_df
from finproof import config
from finproof.ledger import Tip, score_tip, source_record


def tip(direction="up", posted=dt.date(2025, 1, 4), expected=None, sym="ABC"):
    return Tip("t1", "s1", "Source 1", sym, direction, posted, expected_price=expected)


def test_entry_is_first_trading_day_on_or_after_post(flat_nifty):
    # 2025-01-04 is a Saturday, so entry is Monday 2025-01-06.
    stock = make_df([100 + i for i in range(300)])
    res = score_tip(tip(), FakePrices({"ABC": stock, config.BENCHMARK: flat_nifty}))
    assert res.horizons[7].entry_date == "2025-01-06"
    # Exit after 7 days: last trading day on or before 2025-01-11 (Sat) -> Fri 2025-01-10.
    assert res.horizons[7].exit_date == "2025-01-10"


def test_returns_are_measured_against_the_nifty():
    stock = make_df([100.0] * 10 + [110.0] * 290)
    nifty = make_df([100.0] * 10 + [105.0] * 290)
    res = score_tip(tip(posted=dt.date(2025, 1, 1)), FakePrices({"ABC": stock, config.BENCHMARK: nifty}))
    h = res.horizons[30]
    assert h.status == "scored"
    assert h.stock_return == 0.10 and h.nifty_return == 0.05
    assert h.excess_return == 0.05 and h.worked is True


def test_a_fall_claim_works_only_if_stock_lags_the_nifty():
    stock = make_df([100.0] * 10 + [102.0] * 290)
    nifty = make_df([100.0] * 10 + [105.0] * 290)
    frames = FakePrices({"ABC": stock, config.BENCHMARK: nifty})
    assert score_tip(tip("down", dt.date(2025, 1, 1)), frames).horizons[30].worked is True
    assert score_tip(tip("up", dt.date(2025, 1, 1)), frames).horizons[30].worked is False


def test_horizon_beyond_the_data_is_pending(flat_nifty):
    stock = make_df([100.0] * 40)  # about 8 weeks of data
    res = score_tip(tip(posted=dt.date(2025, 1, 1)), FakePrices({"ABC": stock, config.BENCHMARK: flat_nifty}))
    assert res.horizons[30].status == "scored"
    assert res.horizons[90].status == "pending"


def test_missing_prices_give_no_data(flat_nifty):
    res = score_tip(tip(sym="NOPE"), FakePrices({config.BENCHMARK: flat_nifty}))
    assert all(h.status == "no_data" for h in res.horizons.values())


def test_expected_price_reached_and_days_taken(flat_nifty):
    closes = [100.0] * 300
    highs = [100.0] * 300
    highs[12] = 121.0  # 2025-01-17
    stock = make_df(closes, highs=highs)
    res = score_tip(tip(posted=dt.date(2025, 1, 1), expected=120), FakePrices({"ABC": stock, config.BENCHMARK: flat_nifty}))
    assert res.expected_price_reached is True
    assert res.days_to_expected_price == 16


def test_expected_price_not_reached_when_day_90_is_a_weekend(flat_nifty):
    # 2025-01-01 + 90 days = 2025-04-01 (Tue); 2025-01-03 + 90 = 2025-04-03; use a Saturday end: 2025-01-04 + 90 = 2025-04-05.
    stock = make_df([100.0] * 300)
    res = score_tip(tip(posted=dt.date(2025, 1, 4), expected=150), FakePrices({"ABC": stock, config.BENCHMARK: flat_nifty}))
    assert res.expected_price_reached is False


def test_no_percentage_below_minimum_history(flat_nifty):
    stock = make_df([100.0] * 10 + [110.0] * 290)
    frames = FakePrices({"ABC": stock, config.BENCHMARK: flat_nifty})
    few = [score_tip(tip(posted=dt.date(2025, 1, 1)), frames) for _ in range(config.MIN_TIPS_FOR_RECORD - 1)]
    rec = source_record(few)
    assert rec.enough_history is False and rec.hit_rate is None

    enough = few + [score_tip(tip(posted=dt.date(2025, 1, 1)), frames)]
    rec = source_record(enough)
    assert rec.enough_history is True and rec.hit_rate == 1.0
