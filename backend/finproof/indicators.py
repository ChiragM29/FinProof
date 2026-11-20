"""Technical indicators from daily OHLCV, computed locally from the price cache (no network, no CDN).

They describe what prices and volumes already did. FinProof shows them to fact-check a post's story
("rock bottom", "breakout of the year"), never as a signal to act. Every explanation below passes the
same no-advice check as the cards.

Definitions (the common textbook ones, as used by most charting tools):
- SMA n: mean of the last n closes.
- EMA n: alpha = 2 / (n + 1), seeded with the SMA of the first n closes.
- Rolling VWAP n: sum(typical price x volume) / sum(volume) over the last n sessions,
  typical price = (high + low + close) / 3.
- Bollinger (n, k): SMA n +/- k population standard deviations of the last n closes.
- RSI n (Wilder): first average gain/loss = simple mean of the first n changes, then
  avg = (avg x (n - 1) + new) / n. RSI = 100 - 100 / (1 + gain / loss); 100 when there were
  no losses, 50 when the price did not move at all.
- MACD (fast, slow, signal): EMA fast - EMA slow; signal = EMA signal of the MACD line; histogram = MACD - signal.
- ATR n (Wilder): true range = max(high - low, |high - previous close|, |low - previous close|)
  (high - low on the first session), first ATR = mean of the first n true ranges, then Wilder smoothing.
- Key levels: highest high and lowest low of the last 30 sessions and of the last 252 sessions (about 52 weeks).
"""

from __future__ import annotations

import math
from typing import Sequence

import pandas as pd

from . import config

SMA_N, EMA_N, VWAP_N, BB_N, BB_K, RSI_N, ATR_N = 20, 50, 20, 20, 2.0, 14, 14
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
LEVELS_30, LEVELS_52W = 30, 252
VOL_AVG_N = 20
RSI_HIGH, RSI_LOW = 70, 30

Num = float | None

# One line each: what it measures, and how a beginner uses it to check a tip. Facts, never signals.
EXPLAIN = {
    "sma20": "SMA 20: the average closing price of the last 20 sessions. Use it to see whether a 'cheap' or "
             "'expensive' claim matches where the price has been sitting recently.",
    "ema50": "EMA 50: a 50-session average that gives more weight to recent days. It shows the slower, longer "
             "trend, so you can tell a short burst from a lasting move.",
    "vwap20": "VWAP (20D): the average price paid per share over 20 sessions, weighted by volume. Compare the "
              "post's price with it to see how far it sits from what most traders recently paid.",
    "bollinger": "Bollinger (20, 2): bands 2 standard deviations around the 20-session average. A price outside "
                 "the bands has moved further than usual; it describes the stretch, not what comes next.",
    "levels": "Key levels: the highest and lowest prices of the last 30 sessions and of about 52 weeks. Use them "
              "to fact-check words like 'rock bottom' or 'breakout of the year'.",
    "vol_avg20": "20D Vol Avg: the average volume of the 20 sessions before each day. Bars at 2.5 times this line "
                 "or more are the unusual-volume days FinProof flags.",
    "rsi14": "RSI (14): a 0 to 100 gauge of how fast the price rose or fell over 14 sessions. Above 70 means a "
             "rapid recent climb, below 30 a rapid recent drop. It describes the past, not the next move.",
    "macd": "MACD (12, 26, 9): the gap between a fast and a slow average, with a signal line. The bars show "
            "whether recent momentum was picking up or slowing down.",
    "atr14": "ATR (14): the typical daily price swing over 14 sessions, shown as a % of the price. Know the normal "
             "daily move before you call any move big.",
}


# ------------------------------------------------------------------ the math
def _clean(values: Sequence) -> list[Num]:
    out = []
    for v in values:
        try:
            f = float(v)
        except (TypeError, ValueError):
            f = math.nan
        out.append(None if math.isnan(f) or math.isinf(f) else f)
    return out


def sma(values: Sequence, n: int) -> list[Num]:
    v = _clean(values)
    out: list[Num] = [None] * len(v)
    for i in range(n - 1, len(v)):
        window = v[i - n + 1:i + 1]
        if None not in window:
            out[i] = sum(window) / n
    return out


def ema(values: Sequence, n: int) -> list[Num]:
    """EMA seeded with the SMA of the first n values. Leading None values (e.g. the MACD line) are skipped."""
    v = _clean(values)
    out: list[Num] = [None] * len(v)
    start = next((i for i, x in enumerate(v) if x is not None), None)
    if start is None or len(v) - start < n:
        return out
    alpha = 2 / (n + 1)
    prev = sum(v[start:start + n]) / n
    out[start + n - 1] = prev
    for i in range(start + n, len(v)):
        if v[i] is None:
            break
        prev = alpha * v[i] + (1 - alpha) * prev
        out[i] = prev
    return out


def rolling_vwap(high: Sequence, low: Sequence, close: Sequence, volume: Sequence, n: int = VWAP_N) -> list[Num]:
    h, l, c, vol = _clean(high), _clean(low), _clean(close), _clean(volume)
    out: list[Num] = [None] * len(c)
    for i in range(n - 1, len(c)):
        rows = range(i - n + 1, i + 1)
        if any(None in (h[j], l[j], c[j], vol[j]) for j in rows):
            continue
        total = sum(vol[j] for j in rows)
        if total > 0:
            out[i] = sum((h[j] + l[j] + c[j]) / 3 * vol[j] for j in rows) / total
    return out


def bollinger(close: Sequence, n: int = BB_N, k: float = BB_K) -> tuple[list[Num], list[Num], list[Num]]:
    c = _clean(close)
    mid = sma(c, n)
    upper: list[Num] = [None] * len(c)
    lower: list[Num] = [None] * len(c)
    for i, m in enumerate(mid):
        if m is None:
            continue
        sd = math.sqrt(sum((x - m) ** 2 for x in c[i - n + 1:i + 1]) / n)  # population standard deviation
        upper[i], lower[i] = m + k * sd, m - k * sd
    return mid, upper, lower


def rsi(close: Sequence, n: int = RSI_N) -> list[Num]:
    c = _clean(close)
    out: list[Num] = [None] * len(c)
    if len(c) <= n or None in c:
        return out

    def value(gain: float, loss: float) -> float:
        if loss == 0:
            return 100.0 if gain > 0 else 50.0
        return 100 - 100 / (1 + gain / loss)

    changes = [c[i] - c[i - 1] for i in range(1, len(c))]
    gain = sum(max(d, 0) for d in changes[:n]) / n
    loss = sum(max(-d, 0) for d in changes[:n]) / n
    out[n] = value(gain, loss)
    for i in range(n + 1, len(c)):
        d = changes[i - 1]
        gain = (gain * (n - 1) + max(d, 0)) / n
        loss = (loss * (n - 1) + max(-d, 0)) / n
        out[i] = value(gain, loss)
    return out


def macd(close: Sequence, fast: int = MACD_FAST, slow: int = MACD_SLOW, signal: int = MACD_SIGNAL
         ) -> tuple[list[Num], list[Num], list[Num]]:
    f, s = ema(close, fast), ema(close, slow)
    line = [a - b if a is not None and b is not None else None for a, b in zip(f, s)]
    sig = ema(line, signal)
    hist = [a - b if a is not None and b is not None else None for a, b in zip(line, sig)]
    return line, sig, hist


def true_range(high: Sequence, low: Sequence, close: Sequence) -> list[Num]:
    h, l, c = _clean(high), _clean(low), _clean(close)
    out: list[Num] = []
    for i in range(len(c)):
        if None in (h[i], l[i]):
            out.append(None)
        elif i == 0 or c[i - 1] is None:
            out.append(h[i] - l[i])
        else:
            out.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
    return out


def atr(high: Sequence, low: Sequence, close: Sequence, n: int = ATR_N) -> list[Num]:
    tr = true_range(high, low, close)
    out: list[Num] = [None] * len(tr)
    if len(tr) < n or None in tr[:n]:
        return out
    prev = sum(tr[:n]) / n
    out[n - 1] = prev
    for i in range(n, len(tr)):
        if tr[i] is None:
            break
        prev = (prev * (n - 1) + tr[i]) / n
        out[i] = prev
    return out


def prior_mean(values: Sequence, n: int = VOL_AVG_N) -> list[Num]:
    """Mean of the n values before each one (the day itself excluded), as in the volume-spike check."""
    v = _clean(values)
    out: list[Num] = [None] * len(v)
    for i in range(n, len(v)):
        window = v[i - n:i]
        if None not in window:
            out[i] = sum(window) / n
    return out


def key_levels(high: Sequence, low: Sequence, dates: Sequence[str] | None = None) -> dict:
    """30-session and 52-week (252-session) high and low, ending at the last session given.
    A level is None when there is not enough history for its window."""
    h, l = _clean(high), _clean(low)
    dates = list(dates) if dates is not None else [None] * len(h)
    out: dict = {"sessions": len(h)}
    for name, n in (("30d", LEVELS_30), ("52w", LEVELS_52W)):
        if len(h) < n:
            out[f"high_{name}"] = out[f"low_{name}"] = out[f"high_{name}_date"] = out[f"low_{name}_date"] = None
            continue
        hs = [(x, d) for x, d in zip(h[-n:], dates[-n:]) if x is not None]
        ls = [(x, d) for x, d in zip(l[-n:], dates[-n:]) if x is not None]
        hi = max(hs, key=lambda t: t[0]) if hs else (None, None)
        lo = min(ls, key=lambda t: t[0]) if ls else (None, None)
        out[f"high_{name}"], out[f"high_{name}_date"] = hi
        out[f"low_{name}"], out[f"low_{name}_date"] = lo
    return out


# ------------------------------------------------------------------ outputs
def _r(x: Num, d: int = 2) -> Num:
    return None if x is None else round(float(x), d)


def _frame(df: pd.DataFrame) -> pd.DataFrame:
    return df.dropna(subset=["Open", "High", "Low", "Close"]) if not df.empty else df


def series(df: pd.DataFrame) -> dict[str, list[Num]]:
    """Every chart indicator, one value per row of `df` (None where the window is not full yet)."""
    df = _frame(df)
    h, l, c, v = (df[k].tolist() for k in ("High", "Low", "Close", "Volume"))
    mid, up, lo = bollinger(c)
    m, s, hist = macd(c)
    a = atr(h, l, c)
    return {
        "sma20": [_r(x) for x in sma(c, SMA_N)],
        "ema50": [_r(x) for x in ema(c, EMA_N)],
        "vwap20": [_r(x) for x in rolling_vwap(h, l, c, v)],
        "bb_mid": [_r(x) for x in mid], "bb_upper": [_r(x) for x in up], "bb_lower": [_r(x) for x in lo],
        "rsi14": [_r(x) for x in rsi(c)],
        "macd": [_r(x, 3) for x in m], "macd_signal": [_r(x, 3) for x in s], "macd_hist": [_r(x, 3) for x in hist],
        "atr14": [_r(x) for x in a],
        "atr14_pct": [None if x is None or not cc else round(x / cc, 4) for x, cc in zip(a, c)],
        "vol_avg20": [_r(x, 0) for x in prior_mean(v)],
    }


def levels_as_of(df: pd.DataFrame, before: str | None = None) -> dict:
    """Key levels from the sessions strictly before `before` (YYYY-MM-DD), or from all sessions."""
    df = _frame(df)
    if before:
        df = df.loc[df.index < pd.Timestamp(before)]
    lv = key_levels(df["High"].tolist(), df["Low"].tolist(), [d.date().isoformat() for d in df.index])
    lv["as_of"] = df.index[-1].date().isoformat() if len(df) else None
    return {k: (_r(v) if isinstance(v, float) else v) for k, v in lv.items()}


def _pct_text(x: float) -> str:
    return f"{abs(round(float(x) * 100, 1)):.1f}%"


def snapshot(df: pd.DataFrame, posted_on) -> dict | None:
    """Indicator readings at the last session BEFORE the post (point-in-time safe), with neutral one-line facts."""
    df = _frame(df)
    if df.empty:
        return None
    past = df.loc[df.index < pd.Timestamp(posted_on)]
    if len(past) < SMA_N:
        return None
    ind = series(past)
    last = {k: v[-1] for k, v in ind.items()}
    close = float(past["Close"].iloc[-1])
    snap = {
        "as_of": past.index[-1].date().isoformat(), "close": round(close, 2), "provenance": config.REAL_LABEL,
        **{k: last[k] for k in ("sma20", "ema50", "vwap20", "bb_upper", "bb_lower", "rsi14", "macd", "macd_signal",
                                "macd_hist", "atr14", "atr14_pct")},
        "levels": levels_as_of(past),
    }
    for key, base in (("dist_sma20", "sma20"), ("dist_ema50", "ema50"), ("dist_vwap20", "vwap20")):
        snap[key] = round(close / snap[base] - 1, 4) if snap[base] else None
    hist_prev = ind["macd_hist"][-2] if len(past) > 1 else None
    snap["macd_trend"] = (None if snap["macd_hist"] is None or hist_prev is None else
                          ("picking up" if abs(snap["macd_hist"]) > abs(hist_prev) else "slowing down"))
    snap["facts"] = facts(snap)
    return snap


def rsi_words(value: float) -> str:
    if value >= RSI_HIGH:
        return "a rapid recent climb"
    if value <= RSI_LOW:
        return "a rapid recent drop"
    return "no extreme reading"


def facts(s: dict) -> list[dict]:
    """Neutral, numbered facts from a snapshot, each tagged with what it is about."""
    out = []

    def side(d: float) -> str:
        return "above" if d >= 0 else "below"

    if s.get("dist_sma20") is not None:
        out.append({"code": "sma20", "text": f"Price {_pct_text(s['dist_sma20'])} {side(s['dist_sma20'])} its 20-day "
                                             f"average (SMA 20 ₹{s['sma20']:,.2f})."})
    if s.get("dist_vwap20") is not None:
        out.append({"code": "vwap20", "text": f"Price {_pct_text(s['dist_vwap20'])} {side(s['dist_vwap20'])} its 20-day "
                                              f"VWAP (₹{s['vwap20']:,.2f})."})
    if s.get("dist_ema50") is not None:
        out.append({"code": "ema50", "text": f"Price {_pct_text(s['dist_ema50'])} {side(s['dist_ema50'])} its 50-day "
                                             f"EMA (₹{s['ema50']:,.2f})."})
    if s.get("rsi14") is not None:
        out.append({"code": "rsi14", "text": f"RSI(14) at {s['rsi14']:.1f}: {rsi_words(s['rsi14'])}."})
    if s.get("macd_hist") is not None and s.get("macd_trend"):
        direction = "upward" if s["macd_hist"] >= 0 else "downward"
        out.append({"code": "macd", "text": f"MACD histogram {s['macd_hist']:+.3f}: {direction} momentum was "
                                            f"{s['macd_trend']}."})
    if s.get("bb_upper") is not None and s.get("close") is not None:
        where = ("above the upper band" if s["close"] > s["bb_upper"] else "below the lower band"
                 if s["close"] < s["bb_lower"] else "inside the bands")
        out.append({"code": "bollinger", "text": f"Price {where} (Bollinger 20, 2: ₹{s['bb_lower']:,.2f} to "
                                                 f"₹{s['bb_upper']:,.2f})."})
    if s.get("atr14_pct") is not None:
        out.append({"code": "atr14", "text": f"Typical daily swing (ATR 14): ±{_pct_text(s['atr14_pct'])}."})
    lv = s.get("levels") or {}
    if lv.get("high_52w") is not None:
        out.append({"code": "levels", "text": f"52-week range ₹{lv['low_52w']:,.2f} to ₹{lv['high_52w']:,.2f}; "
                                              f"30-session range ₹{lv['low_30d']:,.2f} to ₹{lv['high_30d']:,.2f}."})
    elif lv.get("high_30d") is not None:
        out.append({"code": "levels", "text": f"30-session range ₹{lv['low_30d']:,.2f} to ₹{lv['high_30d']:,.2f} "
                                              "(less than 52 weeks of history)."})
    return out
