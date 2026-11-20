"""Real SEBI pump-and-dump cases, shown on real exchange prices.

The case facts come from SEBI's order and the reports listed as sources. Every price and volume number is
computed from the cached exchange data at scan time, never typed in by hand.

Sadhna Broadcast is listed only on BSE (scrip 540821; renamed Crystal Business System, BSE symbol CRYSTAL),
so a tool that reads only NSE prices cannot see it: this case is why FinProof has a BSE fallback.
"""

from __future__ import annotations

import pandas as pd

from . import config

CASES = [
    {
        "id": "sadhna",
        "symbol": "BSE:CRYSTAL",
        "scrip": "540821",
        "company": "Sadhna Broadcast Ltd (now Crystal Business System Ltd)",
        "order": "SEBI interim order, 2 March 2023",
        "summary": "SEBI's interim order of 2 March 2023 says misleading YouTube videos promoted this stock in the "
                   "second half of July 2022.",
        "listing": "Listed only on BSE (scrip 540821); not listed on NSE.",
        "promotion_from": "2022-07-18",  # first trading session of the second half of July 2022
        "provenance": config.REAL_LABEL,
        "sources": [
            {"label": "YourStory: SEBI cracks down on YouTube pump and dump (March 2023)",
             "url": "https://yourstory.com/2023/03/pump-and-dump-sebi-cracks-down-on-youtube-channels-finfluencers"},
            {"label": "Sadhna Broadcast on BSE (Zerodha)", "url": "https://www.zerodha.com/markets/stocks/BSE/SADHNA/"},
            {"label": "Crystal Business System on BSE (Zerodha)", "url": "https://zerodha.com/markets/stocks/BSE/CRYSTAL/"},
            {"label": "Not listed on NSE (Nirmal Bang)", "url": "https://www.nirmalbang.com/company/sadhna-broadcast/288240"},
        ],
    },
]


def find(symbol: str | None) -> dict | None:
    return next((c for c in CASES if symbol and c["symbol"] == symbol.upper()), None)


def _pct(x: float) -> str:
    return f"{round(float(x) * 100, 1):+.1f}%"


def facts(case: dict, prices) -> dict | None:
    """Volume and price around the promotion window, from the exchange data. None if the data is not there."""
    df = prices.history(case["symbol"])
    if df.empty:
        return None
    df = df.dropna(subset=["Close", "Volume"])
    start = int(df.index.searchsorted(pd.Timestamp(case["promotion_from"])))
    if start < 20 or start + 30 > len(df):
        return None
    base = df.iloc[start - 20:start]
    window = df.iloc[start:start + 30]
    later = df.iloc[min(len(df) - 1, start + 60)]
    avg_vol = float(base["Volume"].mean())
    if avg_vol <= 0:
        return None
    before = float(base["Close"].iloc[-1])
    peak_day = window["Close"].idxmax()
    peak = float(window["Close"].max())
    vol_day = window["Volume"].idxmax()
    vol_ratio = float(window["Volume"].max()) / avg_vol
    after = float(later["Close"])
    lines = [
        f"Before the promotion: ₹{before:,.2f} on {base.index[-1].date().isoformat()}, about "
        f"{avg_vol:,.0f} shares a day (20-session average).",
        f"In the 30 sessions from {df.index[start].date().isoformat()}: volume up to {vol_ratio:.1f}× that average "
        f"({vol_day.date().isoformat()}); price up to ₹{peak:,.2f} ({peak_day.date().isoformat()}), {_pct(peak / before - 1)}.",
        f"60 sessions after the window opened: ₹{after:,.2f} ({_pct(after / peak - 1)} from the peak).",
    ]
    return {"lines": lines, "volume_ratio": round(vol_ratio, 2), "peak": round(peak, 2), "before": round(before, 2),
            "after": round(after, 2), "pin": df.index[start].date().isoformat(), "exchange": "BSE",
            "provenance": config.REAL_LABEL}


def attach(card: dict, prices) -> None:
    """If the post names a known SEBI case stock, add the case and its computed price facts to the card."""
    for claim in card.get("claims", []):
        case = find(claim.get("symbol"))
        if case:
            card["case"] = {**case, "facts": facts(case, prices)}
            return
