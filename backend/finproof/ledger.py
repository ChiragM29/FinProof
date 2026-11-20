"""The tip ledger: every recorded tip, scored against what the market did next.

Scoring rule (kept simple so judges can check it by hand):
- Entry: closing price on the first trading day on or after the day the tip was posted.
- Exit after N days: closing price on the last trading day on or before posted date + N days.
- The tip "worked" if the stock beat the Nifty 50 over the same dates in the direction
  the tip claimed (rise: stock return minus Nifty return > 0; fall: < 0).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, field

import pandas as pd

from . import config


@dataclass
class Tip:
    tip_id: str
    source_id: str
    source_label: str
    symbol: str
    direction: str  # "up" or "down"
    posted_on: dt.date
    expected_price: float | None = None
    stop_loss: float | None = None
    link: str = ""
    provenance: str = config.REAL_LABEL
    note: str = ""


@dataclass
class HorizonResult:
    days: int
    status: str  # scored | pending | no_data
    entry_date: str | None = None
    exit_date: str | None = None
    stock_return: float | None = None
    nifty_return: float | None = None
    excess_return: float | None = None
    worked: bool | None = None


@dataclass
class ScoredTip:
    tip: Tip
    horizons: dict[int, HorizonResult] = field(default_factory=dict)
    expected_price_reached: bool | None = None
    days_to_expected_price: int | None = None

    def to_dict(self) -> dict:
        d = asdict(self.tip)
        d["posted_on"] = self.tip.posted_on.isoformat()
        d["horizons"] = {str(k): asdict(v) for k, v in self.horizons.items()}
        d["expected_price_reached"] = self.expected_price_reached
        d["days_to_expected_price"] = self.days_to_expected_price
        return d


TIP_COLUMNS = [
    "tip_id", "source_id", "source_label", "symbol", "direction", "posted_on",
    "expected_price", "stop_loss", "link", "provenance", "note",
]


def _opt_float(v) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == "":
        return None
    return float(v)


def load_tips(paths=None) -> list[Tip]:
    """Read tips from data/real/tips_real.csv and data/synthetic/synthetic_tips.csv."""
    if paths is None:
        paths = [config.REAL / "tips_real.csv", config.SYNTHETIC / "synthetic_tips.csv"]
    tips: list[Tip] = []
    for path in paths:
        if not path.exists():
            continue
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        for row in df.to_dict("records"):
            if not row.get("symbol"):
                continue
            tips.append(Tip(
                tip_id=row["tip_id"],
                source_id=row["source_id"],
                source_label=row.get("source_label") or row["source_id"],
                symbol=row["symbol"].strip().upper(),
                direction=row["direction"].strip().lower(),
                posted_on=dt.date.fromisoformat(row["posted_on"].strip()),
                expected_price=_opt_float(row.get("expected_price")),
                stop_loss=_opt_float(row.get("stop_loss")),
                link=row.get("link", ""),
                provenance=(row.get("provenance") or config.REAL_LABEL).strip().upper(),
                note=row.get("note", ""),
            ))
    return tips


def _first_on_or_after(index: pd.DatetimeIndex, day: dt.date) -> int | None:
    pos = index.searchsorted(pd.Timestamp(day), side="left")
    return int(pos) if pos < len(index) else None


def _last_on_or_before(index: pd.DatetimeIndex, day: dt.date) -> int | None:
    pos = index.searchsorted(pd.Timestamp(day), side="right") - 1
    return int(pos) if pos >= 0 else None


def score_tip(tip: Tip, prices) -> ScoredTip:
    result = ScoredTip(tip=tip)
    stock = prices.history(tip.symbol)
    bench = prices.history(config.BENCHMARK)
    if stock.empty or bench.empty:
        result.horizons = {h: HorizonResult(h, "no_data") for h in config.HORIZONS}
        return result

    entry_pos = _first_on_or_after(stock.index, tip.posted_on)
    if entry_pos is None:
        result.horizons = {h: HorizonResult(h, "pending") for h in config.HORIZONS}
        return result
    entry_day = stock.index[entry_pos]
    entry_px = float(stock["Adj Close"].iloc[entry_pos])
    bench_entry_pos = _last_on_or_before(bench.index, entry_day.date())

    for h in config.HORIZONS:
        target_day = tip.posted_on + dt.timedelta(days=h)
        last_day = min(stock.index[-1].date(), bench.index[-1].date())
        if target_day > last_day:
            result.horizons[h] = HorizonResult(h, "pending", entry_date=entry_day.date().isoformat())
            continue
        exit_pos = _last_on_or_before(stock.index, target_day)
        bench_exit_pos = _last_on_or_before(bench.index, target_day)
        if exit_pos is None or exit_pos <= entry_pos or bench_entry_pos is None or bench_exit_pos is None:
            result.horizons[h] = HorizonResult(h, "no_data")
            continue
        exit_px = float(stock["Adj Close"].iloc[exit_pos])
        s_ret = exit_px / entry_px - 1
        n_ret = float(bench["Adj Close"].iloc[bench_exit_pos]) / float(bench["Adj Close"].iloc[bench_entry_pos]) - 1
        excess = s_ret - n_ret
        worked = excess > 0 if tip.direction == "up" else excess < 0
        result.horizons[h] = HorizonResult(
            h, "scored",
            entry_date=entry_day.date().isoformat(),
            exit_date=stock.index[exit_pos].date().isoformat(),
            stock_return=round(s_ret, 4), nifty_return=round(n_ret, 4),
            excess_return=round(excess, 4), worked=bool(worked),
        )

    if tip.expected_price:
        window_end = tip.posted_on + dt.timedelta(days=max(config.HORIZONS))
        win = stock.loc[(stock.index >= entry_day) & (stock.index <= pd.Timestamp(window_end))]
        if not win.empty:
            hit = win["High"] >= tip.expected_price if tip.direction == "up" else win["Low"] <= tip.expected_price
            if hit.any():
                first = win.index[hit.values.argmax()]
                result.expected_price_reached = True
                result.days_to_expected_price = (first.date() - tip.posted_on).days
            elif window_end <= stock.index[-1].date():
                result.expected_price_reached = False
    return result


@dataclass
class SourceRecord:
    source_id: str
    source_label: str
    provenance: str
    tips_total: int
    scored: int
    worked: int
    hit_rate: float | None
    avg_excess_return: float | None
    enough_history: bool
    horizon_days: int


def source_record(scored_tips: list[ScoredTip], horizon: int = config.MAIN_HORIZON) -> SourceRecord:
    first = scored_tips[0].tip
    done = [s.horizons[horizon] for s in scored_tips if s.horizons.get(horizon) and s.horizons[horizon].status == "scored"]
    worked = sum(1 for r in done if r.worked)
    enough = len(done) >= config.MIN_TIPS_FOR_RECORD
    provs = {s.tip.provenance for s in scored_tips}
    return SourceRecord(
        source_id=first.source_id,
        source_label=first.source_label,
        provenance=provs.pop() if len(provs) == 1 else "MIXED",
        tips_total=len(scored_tips),
        scored=len(done),
        worked=worked,
        hit_rate=round(worked / len(done), 3) if (done and enough) else None,
        avg_excess_return=round(sum(r.excess_return for r in done) / len(done), 4) if (done and enough) else None,
        enough_history=enough,
        horizon_days=horizon,
    )


class Ledger:
    """All tips, scored lazily and grouped by source."""

    def __init__(self, prices, tips: list[Tip] | None = None):
        self.prices = prices
        self.tips = load_tips() if tips is None else tips
        self._scored: dict[str, ScoredTip] = {}

    def scored(self, tip: Tip) -> ScoredTip:
        if tip.tip_id not in self._scored:
            self._scored[tip.tip_id] = score_tip(tip, self.prices)
        return self._scored[tip.tip_id]

    def sources(self) -> dict[str, list[Tip]]:
        out: dict[str, list[Tip]] = {}
        for t in self.tips:
            out.setdefault(t.source_id, []).append(t)
        return out

    def find_source(self, key: str | None) -> str | None:
        if not key:
            return None
        k = key.strip().lower()
        for sid, tips in self.sources().items():
            if k in (sid.lower(), tips[0].source_label.lower()):
                return sid
        return None

    def record(self, source_id: str, as_of: dt.date | None = None) -> tuple[SourceRecord | None, list[ScoredTip]]:
        """Track record of a source. With `as_of`, only tips whose 30-day result was already
        known before that date count (point-in-time cards for the decision test)."""
        tips = self.sources()[source_id]
        if as_of is not None:
            cutoff = as_of - dt.timedelta(days=config.MAIN_HORIZON)
            tips = [t for t in tips if t.posted_on < cutoff]
        if not tips:
            return None, []
        scored = [self.scored(t) for t in sorted(tips, key=lambda t: t.posted_on)]
        return source_record(scored), scored
