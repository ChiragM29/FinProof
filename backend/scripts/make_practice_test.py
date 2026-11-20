"""Build a PRACTICE tip set for the decision test: eval/decision_test/tips_practice.json.

The posts are made up (SYNTHETIC) so the screens can be tried before real tips are
collected. Stocks and dates are real, and each tip's outcome comes from real NSE prices:
6 tips that beat the Nifty 50 in the claimed direction over 30 days and 6 that did not,
each by at least 3 points. The writing style of each post (hype, urgency, calm) is picked
at random, independently of the outcome, so the practice set is not rigged in favour of
the card. Never report practice answers as evidence.
"""

from __future__ import annotations

import datetime as dt
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finproof import config  # noqa: E402
from finproof.ledger import Tip, score_tip  # noqa: E402
from finproof.market import YahooPrices, company_name  # noqa: E402

OUT = config.ROOT / "eval" / "decision_test" / "tips_practice.json"
STOCKS = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "ITC", "LT", "BHARTIARTL", "AXISBANK",
          "KOTAKBANK", "MARUTI", "SUNPHARMA", "TITAN", "ASIANPAINT", "HINDUNILVR", "BAJFINANCE", "WIPRO",
          "TATASTEEL", "ADANIENT", "ETERNAL", "TMPV", "POWERGRID", "NTPC", "ONGC"]
START, END = dt.date(2024, 4, 1), dt.date(2025, 9, 30)
PER_LABEL = 6
MIN_GAP = 0.03

SOURCES = [("demo_a", "Demo Channel A (synthetic)"), ("demo_b", "Demo Channel B (synthetic)"),
           ("demo_c", "Demo Channel C (synthetic)"), ("", "Forwarded message")]

UP_POSTS = [
    ("telegram", "", "{sym} looking strong on the daily chart. CMP {cmp}, target {t1}. SL {sl}."),
    ("telegram", "", "🚀 SURE SHOT CALL 🚀\nBUY {sym} CMP {cmp} TGT {t1}/{t2} SL {sl}\nJoin our VIP group for more calls!"),
    ("whatsapp", "", "Bhai {sym} abhi le lo, {t1} jaayega pakka. Jaldi karo!"),
    ("telegram", "", "Breakout in {sym}. Levels to watch: {t1} and {t2}. Stop-loss {sl}. "
                     "Not a recommendation, do your own research."),
    ("youtube", "{company} share: is {t1} next?",
     "so friends {sym} has given a clean breakout with good volumes, my view is positive, "
     "first level {t1} then {t2}, keep a stop loss of {sl}"),
    ("whatsapp", "", "Insider news coming in {sym} 🔥 Operators are active. Target {t2} in 2 weeks. 100% sure."),
]
DOWN_POSTS = [
    ("telegram", "", "SELL {sym} below {cmp}. TGT {t1}, SL {sl}. Weak chart."),
    ("youtube", "{company}: time to get out?",
     "friends {sym} is looking weak, breakdown below {cmp}, I see downside towards {t1}, stop loss {sl}"),
]


def last_close(prices, symbol: str, day: dt.date) -> float:
    df = prices.history(symbol)
    return float(df.loc[df.index < str(day), "Close"].iloc[-1])


def main() -> int:
    pick = random.Random(11)
    style = random.Random(23)
    prices = YahooPrices()
    days = [START + dt.timedelta(d) for d in range((END - START).days) if (START + dt.timedelta(d)).weekday() < 5]

    chosen = {"good": [], "bad": []}
    used: set[str] = set()
    for _ in range(3000):
        if all(len(v) >= PER_LABEL for v in chosen.values()):
            break
        sym = pick.choice(STOCKS)
        day = pick.choice(days)
        direction = "down" if pick.random() < 0.2 else "up"
        if sym in used:
            continue
        h = score_tip(Tip("x", "x", "x", sym, direction, day), prices).horizons[config.MAIN_HORIZON]
        if h.status != "scored":
            continue
        outcome = h.excess_return if direction == "up" else -h.excess_return
        bucket = "good" if outcome > 0 else "bad"
        if abs(outcome) < MIN_GAP or len(chosen[bucket]) >= PER_LABEL:
            continue
        chosen[bucket].append((sym, day, direction))
        used.add(sym)
    if any(len(v) < PER_LABEL for v in chosen.values()):
        print("Could not find enough clear tips; check the price cache.", file=sys.stderr)
        return 1

    picks = chosen["good"] + chosen["bad"]
    pick.shuffle(picks)  # ids must not follow the outcome
    tips = []
    for n, (sym, day, direction) in enumerate(picks, 1):
        cmp_ = last_close(prices, sym, day)
        sign = 1 if direction == "up" else -1
        t1 = cmp_ * (1 + sign * style.uniform(0.08, 0.15))
        t2 = cmp_ * (1 + sign * style.uniform(0.16, 0.25))
        sl = cmp_ * (1 - sign * style.uniform(0.04, 0.06))
        platform, title, body = style.choice(UP_POSTS if direction == "up" else DOWN_POSTS)
        source_id, source_label = style.choice(SOURCES)
        fill = {"sym": sym, "company": (company_name(sym) or sym).replace(" Limited", ""),
                "cmp": f"{cmp_:.0f}", "t1": f"{t1:.0f}", "t2": f"{t2:.0f}", "sl": f"{sl:.0f}"}
        tips.append({
            "tip_id": f"P{n:02d}", "platform": platform, "source_id": source_id, "source_label": source_label,
            "posted_on": day.isoformat(), "symbol": sym, "direction": direction,
            "title": title.format(**fill), "text": body.format(**fill),
            "provenance": "SYNTHETIC", "note": "made-up post; stock, date and outcome are real",
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "name": "practice",
        "practice": True,
        "description": "Made-up posts on real stocks and dates, for trying the decision test. Not evidence.",
        "tips": tips,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(tips)} practice tips to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
