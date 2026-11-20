"""Create clearly labelled SYNTHETIC demo tips in data/synthetic/synthetic_tips.csv.

The tips are made up (random stocks, dates and directions, fixed seed) so the
dashboard has something to show before real tips are collected. Their outcomes
are still computed from REAL NSE prices. Never report these as evidence.
"""

from __future__ import annotations

import csv
import datetime as dt
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "synthetic" / "synthetic_tips.csv"

STOCKS = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "ITC", "LT", "BHARTIARTL", "AXISBANK",
          "KOTAKBANK", "MARUTI", "SUNPHARMA", "TITAN", "ASIANPAINT", "HINDUNILVR", "BAJFINANCE", "WIPRO",
          "TATASTEEL", "ADANIENT", "ETERNAL", "TMPV", "POWERGRID", "NTPC", "ONGC"]
SOURCES = [("demo_a", "Demo Channel A (synthetic)", 14),
           ("demo_b", "Demo Channel B (synthetic)", 14),
           ("demo_c", "Demo Channel C (synthetic)", 6)]
START, END = dt.date(2024, 1, 1), dt.date(2025, 10, 31)


def main() -> None:
    rng = random.Random(2026)
    days = [START + dt.timedelta(d) for d in range((END - START).days) if (START + dt.timedelta(d)).weekday() < 5]
    rows = []
    for sid, label, n in SOURCES:
        for k, day in enumerate(sorted(rng.sample(days, n)), 1):
            rows.append({
                "tip_id": f"{sid}-{k:02d}", "source_id": sid, "source_label": label,
                "symbol": rng.choice(STOCKS), "direction": "up" if rng.random() < 0.85 else "down",
                "posted_on": day.isoformat(), "expected_price": "", "stop_loss": "", "link": "",
                "provenance": "SYNTHETIC", "note": "made-up demo tip; outcome uses real NSE prices",
            })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} synthetic tips to {OUT}")


if __name__ == "__main__":
    main()
