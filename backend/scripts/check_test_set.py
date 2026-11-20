"""Check a decision-test tip set before running the study.

  python scripts/check_test_set.py           # the active set (real if tips_real.json exists)
  python scripts/check_test_set.py practice

Prints each tip's 30-day outcome, label and set, the warnings its point-in-time card
would show, and any problem that would stop the test from starting.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finproof import study  # noqa: E402
from finproof.ledger import Ledger  # noqa: E402
from finproof.market import YahooPrices  # noqa: E402


def main(args: list[str]) -> int:
    prices = YahooPrices()
    ts = study.load_test_set(prices, args[0] if args else None)
    ledger = Ledger(prices)
    print(f"Tip set: {ts.path}  ({len(ts.tips)} tips, version {ts.digest}, {'practice' if ts.practice else 'REAL'})\n")
    print(f"{'tip':6} {'set':3} {'label':5} {'vs Nifty':>9}  {'stock':12} {'dir':4} {'posted':10}  card warnings")
    for t in sorted(ts.tips, key=lambda t: (t.set or "", t.tip_id)):
        outcome = "–" if t.outcome is None else f"{t.outcome * 100:+.1f}%"
        flag = "" if t.clear else " (unclear)"
        try:
            card = study.card_for(t, ts, ledger, prices)
            warn = ", ".join(w["code"] for w in card["warnings"]) or "none"
        except Exception as exc:  # the card must build, or the test can't show it
            warn = f"CARD FAILED: {exc}"
        print(f"{t.tip_id:6} {t.set or '-':3} {t.label or '-':5} {outcome:>9}  {t.symbol:12} {t.direction:4} "
              f"{t.posted_on.isoformat():10}  {warn}{flag}")
    for label in ("good", "bad"):
        print(f"\n{label}: " + ", ".join(f"set {s} = {sum(1 for t in ts.tips if t.set == s and t.label == label)}"
                                         for s in ("X", "Y")), end="")
    print("\n")
    for note in ts.notes:
        print("Note:", note)
    for problem in ts.problems:
        print("PROBLEM:", problem)
    print("Ready to run." if not ts.problems else "Not ready: fix the problems above.")
    return 0 if not ts.problems else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
