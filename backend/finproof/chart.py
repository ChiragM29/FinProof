"""Candles, volume and the Nifty 50 for the terminal chart. All REAL NSE data from the price cache."""

from __future__ import annotations

import math

import pandas as pd

from . import config, indicators
from .market import company_name, current_symbol, display_symbol, exchange_of, split_exchange
from .pumpdump import BASE_WINDOW, VOLUME_SPIKE_RATIO, volume_anomalies

CHART_START = "2019-01-01"
WATCHLIST = ["^NSEI", "RELIANCE", "HDFCBANK", "ICICIBANK", "SBIN", "INFY", "TCS", "ITC", "TMPV", "KOTAKBANK",
             "BHARTIARTL"]
NIFTY_NAMES = {"NIFTY", "NIFTY50", "NIFTY 50", "^NSEI"}


def resolve(symbol: str) -> str:
    s = symbol.strip().upper()
    if s in NIFTY_NAMES:
        return config.BENCHMARK
    return s if split_exchange(s)[1] == "BSE" else current_symbol(s)


def quote(symbol: str, prices) -> dict | None:
    """Last close and day change for the watchlist, from the price cache."""
    sym = resolve(symbol)
    df = prices.history(sym)
    if len(df) < 2:
        return None
    last, prev = float(df["Close"].iloc[-1]), float(df["Close"].iloc[-2])
    return {"symbol": sym, "label": "NIFTY 50" if sym == config.BENCHMARK else sym,
            "company": "Nifty 50 index" if sym == config.BENCHMARK else company_name(sym),
            "last": round(last, 2), "change": round(last - prev, 2), "change_pct": round((last / prev - 1) * 100, 2),
            "date": df.index[-1].date().isoformat(), "provenance": config.REAL_LABEL}


def _num(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) or math.isinf(v) else round(v, 2)


def chart_payload(symbol: str, prices, start: str = CHART_START, levels_before: str | None = None) -> dict | None:
    """Candles, volume, Nifty 50 and every indicator, all from the price cache.

    Indicators are computed on the full cached history (so long averages are warmed up), then cut to `start`.
    Key levels use only sessions before `levels_before` (the post date) when it is given."""
    sym = resolve(symbol)
    full = prices.history(sym)
    if full.empty:
        return None
    full = full.dropna(subset=["Open", "High", "Low", "Close"])
    if full.empty:
        return None
    ratios = volume_anomalies(full)  # computed on full history: each day vs the 20 sessions before it
    ind = indicators.series(full)
    keep = [i for i, day in enumerate(full.index) if day >= pd.Timestamp(start)]
    candles, volume = [], []
    for i in keep:
        day, row = full.index[i], full.iloc[i]
        o, h, l, c = (_num(row[k]) for k in ("Open", "High", "Low", "Close"))
        t = day.strftime("%Y-%m-%d")
        candles.append({"time": t, "open": o, "high": h, "low": l, "close": c})
        r = _num(ratios.get(day))
        volume.append({"time": t, "value": _num(row["Volume"]) or 0.0, "ratio": r, "up": c >= o})
    bench = prices.history(config.BENCHMARK)
    bench = bench.loc[bench.index >= start] if not bench.empty else bench
    nifty = [{"time": d.strftime("%Y-%m-%d"), "value": v} for d, v in
             ((d, _num(x)) for d, x in bench["Close"].items()) if v is not None] if not bench.empty else []
    return {
        "symbol": sym, "label": "NIFTY 50" if sym == config.BENCHMARK else display_symbol(sym), "requested": symbol.upper(),
        "company": "Nifty 50 index" if sym == config.BENCHMARK else company_name(display_symbol(sym)),
        "exchange": exchange_of(prices, sym),
        "provenance": config.REAL_LABEL, "source": "NSE prices via Yahoo Finance",
        "candles": candles, "volume": volume, "nifty": nifty,
        "spike_ratio": VOLUME_SPIKE_RATIO, "spike_window": BASE_WINDOW,
        "indicators": {k: [v[i] for i in keep] for k, v in ind.items()},
        "levels": indicators.levels_as_of(full, levels_before), "explain": indicators.EXPLAIN,
        "indicators_provenance": config.REAL_LABEL,
        "first_date": candles[0]["time"] if candles else None, "last_date": candles[-1]["time"] if candles else None,
    }
