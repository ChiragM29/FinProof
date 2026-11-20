"""Market warning signs around the day a tip was posted.

These are signals, not verdicts. Thresholds are starting values; tune them on the
SEBI cases vs random stock-days in eval/ and report the numbers honestly.

Everything except `fall_after` uses only sessions strictly BEFORE the post date, so the
same numbers are safe on point-in-time cards. The post day itself is excluded on
purpose: a tip posted at 10 am makes that day's volume partly a reaction to the tip.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

SPIKE_WINDOW = 3               # sessions just before the post
BASE_WINDOW = 20               # sessions before those, for the usual level
VOLUME_SPIKE_RATIO = 2.5       # biggest volume in the spike window vs the 20-session average
RUN_UP_20D = 0.25              # price rise over the 20 sessions before the post
THIN_TRADING_RUPEES = 1e7      # 20-session average daily traded value below ₹1 crore
FALL_AFTER = -0.25             # drop from the post-week peak within the next 30 sessions


@dataclass
class MarketSignals:
    symbol: str
    status: str  # ok | no_data | too_little_history
    spike_ratio: float | None = None          # max volume (3 sessions before) / 20-session average
    spike_date: str | None = None
    avg_traded_value_20d: float | None = None  # rupees per day
    volume_ratio: float | None = None         # 5-session mean / 60-session median (older measure)
    run_up_20d: float | None = None
    median_traded_value: float | None = None
    fall_after: float | None = None
    last_session_used: str | None = None      # latest date that fed the pre-post signals
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def market_signals(symbol: str, posted_on: dt.date, prices, include_after: bool = True) -> MarketSignals:
    """Signals from the sessions before the post; with include_after, also the fall after it."""
    df = prices.history(symbol)
    if df.empty:
        return MarketSignals(symbol, "no_data")
    i = int(df.index.searchsorted(pd.Timestamp(posted_on), side="left"))
    spike = df.iloc[max(0, i - SPIKE_WINDOW):i]
    base = df.iloc[max(0, i - SPIKE_WINDOW - BASE_WINDOW):max(0, i - SPIKE_WINDOW)]
    if len(spike) < SPIKE_WINDOW or len(base) < 15:
        return MarketSignals(symbol, "too_little_history")

    out = MarketSignals(symbol, "ok", last_session_used=df.index[i - 1].date().isoformat())
    base_mean = float(base["Volume"].mean())
    if base_mean > 0:
        top = int(np.argmax(spike["Volume"].to_numpy()))
        out.spike_ratio = round(float(spike["Volume"].iloc[top]) / base_mean, 2)
        out.spike_date = spike.index[top].date().isoformat()
    last20 = df.iloc[max(0, i - BASE_WINDOW):i]
    out.avg_traded_value_20d = round(float((last20["Close"] * last20["Volume"]).mean()), 0)

    long_base = df.iloc[max(0, i - 65):max(0, i - 5)]
    pre5 = df.iloc[max(0, i - 5):i]
    if len(long_base) >= 20 and len(pre5) >= 3:
        med = float(np.median(long_base["Volume"]))
        out.volume_ratio = round(float(pre5["Volume"].mean()) / med, 2) if med > 0 else None
        out.median_traded_value = round(float(np.median(long_base["Close"] * long_base["Volume"])), 0)

    adj = df["Adj Close"].to_numpy(dtype=float)
    if i >= 21:
        out.run_up_20d = round(adj[i - 1] / adj[i - 21] - 1, 4)
    if include_after and i + 30 < len(df):
        peak_at = i + int(adj[i:i + 5].argmax())
        out.fall_after = round(adj[peak_at:i + 30].min() / adj[peak_at] - 1, 4)

    if out.spike_ratio is not None and out.spike_ratio >= VOLUME_SPIKE_RATIO:
        out.flags.append("volume_spike")
    if out.run_up_20d is not None and out.run_up_20d >= RUN_UP_20D:
        out.flags.append("run_up")
    if out.avg_traded_value_20d is not None and out.avg_traded_value_20d < THIN_TRADING_RUPEES:
        out.flags.append("thin_trading")
    if out.fall_after is not None and out.fall_after <= FALL_AFTER:
        out.flags.append("fell_after")
    return out


def volume_anomalies(df: pd.DataFrame, ratio: float = VOLUME_SPIKE_RATIO, window: int = BASE_WINDOW) -> pd.Series:
    """Each session's volume divided by the average of the `window` sessions before it.

    Uses only earlier sessions for every day, so a day is never compared with its own future.
    """
    if df.empty:
        return pd.Series(dtype=float)
    prior_mean = df["Volume"].shift(1).rolling(window, min_periods=window).mean()
    return (df["Volume"] / prior_mean).replace([np.inf, -np.inf], np.nan)
