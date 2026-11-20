"""NSE price data and the list of listed companies.

Prices come from Yahoo Finance and are cached on disk, so a rehearsed demo still
works when the venue Wi-Fi does not.
"""

from __future__ import annotations

import logging
import time
from functools import lru_cache
from pathlib import Path

import pandas as pd

from . import config

log = logging.getLogger(__name__)

PRICE_CACHE = config.CACHE / "prices"
HISTORY_START = "2018-01-01"
COLUMNS = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]


def yahoo_ticker(symbol: str) -> str:
    """NSE symbol -> Yahoo ticker. Index (^) and BSE (.BO) tickers pass through.
    Old symbols (e.g. TATAMOTORS) are mapped to today's symbol first."""
    s = symbol.strip().upper()
    if s.startswith("^") or s.endswith((".NS", ".BO")):
        return s
    return f"{current_symbol(s)}.NS"


@lru_cache(maxsize=1)
def symbol_changes() -> dict[str, str]:
    """Old NSE symbol -> new symbol, from NSE's symbol change file saved in data/real."""
    files = sorted(config.REAL.glob("nse_symbol_changes_*.csv"))
    if not files:
        return {}
    df = pd.read_csv(files[-1], dtype=str, keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    return {o.strip().upper(): n.strip().upper() for o, n in zip(df["OLD SYMBOL"], df["NEW SYMBOL"]) if o and n}


def current_symbol(symbol: str) -> str:
    """Follow NSE renames (LTI -> LTIM -> LTM). A symbol in use today is returned as is."""
    s = symbol.strip().upper()
    listed = set(nse_companies()["SYMBOL"])
    changes = symbol_changes()
    for _ in range(10):
        if s in listed or s not in changes:
            return s
        s = changes[s]
    return s


def _cache_name(ticker: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in ticker) + ".csv"


class YahooPrices:
    """Daily prices for one ticker at a time.

    `Adj Close` (split and dividend adjusted) is used for returns.
    Raw `High`/`Low` are used to check whether a price named in a tip was reached.
    """

    def __init__(self, cache_dir: Path = PRICE_CACHE, max_age_hours: float = 12, offline: bool | None = None):
        self.cache_dir = Path(cache_dir)
        self.max_age = max_age_hours * 3600
        self.offline = config.OFFLINE if offline is None else offline
        self._memo: dict[str, pd.DataFrame] = {}

    def history(self, symbol: str) -> pd.DataFrame:
        ticker = yahoo_ticker(symbol)
        if ticker in self._memo:
            return self._memo[ticker]
        path = self.cache_dir / _cache_name(ticker)
        fresh = path.exists() and (time.time() - path.stat().st_mtime) < self.max_age
        if path.exists() and (fresh or self.offline):
            df = _read(path)
        elif self.offline:
            df = _empty()
        else:
            try:
                df = self._download(ticker)
                if not df.empty:
                    self.cache_dir.mkdir(parents=True, exist_ok=True)
                    df.to_csv(path)
            except Exception as exc:  # network trouble: fall back to an old cache
                log.warning("price download failed for %s: %s", ticker, exc)
                df = _read(path) if path.exists() else _empty()
            if df.empty and path.exists():
                df = _read(path)
        self._memo[ticker] = df
        return df

    def _download(self, ticker: str) -> pd.DataFrame:
        import yfinance as yf

        df = yf.download(ticker, start=HISTORY_START, progress=False, auto_adjust=False, threads=False)
        if df is None or df.empty:
            return _empty()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df[[c for c in COLUMNS if c in df.columns]].dropna(subset=["Close"])
        if "Adj Close" not in df.columns:
            df["Adj Close"] = df["Close"]
        df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
        df.index.name = "Date"
        return df


def _read(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, index_col="Date", parse_dates=["Date"])
    return df.sort_index()


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=COLUMNS, index=pd.DatetimeIndex([], name="Date"))


@lru_cache(maxsize=1)
def nse_companies() -> pd.DataFrame:
    """The NSE equity list saved in data/real (SYMBOL, NAME, SERIES)."""
    files = sorted(config.REAL.glob("nse_equity_list_*.csv"))
    if not files:
        return pd.DataFrame(columns=["SYMBOL", "NAME", "SERIES"])
    df = pd.read_csv(files[-1])
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns={"NAME OF COMPANY": "NAME"})
    df["SYMBOL"] = df["SYMBOL"].astype(str).str.strip().str.upper()
    df["NAME"] = df["NAME"].astype(str).str.strip()
    df["SERIES"] = df["SERIES"].astype(str).str.strip()
    df.attrs["file"] = files[-1].name
    return df[["SYMBOL", "NAME", "SERIES"]]


def company_name(symbol: str) -> str | None:
    df = nse_companies()
    hit = df.loc[df["SYMBOL"] == symbol.upper(), "NAME"]
    return None if hit.empty else str(hit.iloc[0])
