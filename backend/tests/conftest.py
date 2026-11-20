import pandas as pd
import pytest


def make_df(closes, volumes=None, start="2025-01-01", highs=None, lows=None):
    """Daily price frame on business days, shaped like YahooPrices.history()."""
    idx = pd.bdate_range(start=start, periods=len(closes), name="Date")
    closes = [float(c) for c in closes]
    return pd.DataFrame({
        "Open": closes,
        "High": highs or closes,
        "Low": lows or closes,
        "Close": closes,
        "Adj Close": closes,
        "Volume": volumes or [100_000.0] * len(closes),
    }, index=idx)


class FakePrices:
    def __init__(self, frames: dict[str, pd.DataFrame]):
        self.frames = frames

    def history(self, symbol):
        return self.frames.get(symbol, make_df([])[0:0])


@pytest.fixture
def flat_nifty():
    return make_df([100.0] * 300)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Tests never touch the internet: the hybrid probe reports no network unless a test says otherwise."""
    from finproof import net

    monkeypatch.setattr(net, "_probe", lambda: False)
    monkeypatch.setattr(net, "_last", {"at": 0.0, "ok": False})
