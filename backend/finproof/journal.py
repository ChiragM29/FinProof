"""Noise-avoidance journal: what happened to tips a user skipped or set aside for research.

Looks back only: it reports what the stock did after each logged tip, against the Nifty 50.
It never suggests what to do next. The decision labels never say bought or sold.
"""

from __future__ import annotations

import datetime as dt

from . import config
from .ledger import Tip, score_tip

DECISIONS = {
    "skipped": "Skipped after X-Ray",
    "research": "Saved for research",
}

# Four made-up journal entries on real stocks and dates, so the demo account has something
# to show on first load. The decisions are mixed on purpose (one skipped tip did well).
DEMO_SEED = [
    {"symbol": "INFY", "direction": "up", "posted_on": "2025-02-21", "decision": "skipped",
     "source_label": "Demo Channel B (synthetic)", "note": "Hinglish forward: 'pakka', 'jaldi'"},
    {"symbol": "ITC", "direction": "up", "posted_on": "2025-04-07", "decision": "skipped",
     "source_label": "Demo Channel B (synthetic)", "note": "'Insider news', 'operators are active'"},
    {"symbol": "BHARTIARTL", "direction": "up", "posted_on": "2024-04-05", "decision": "skipped",
     "source_label": "Demo Channel A (synthetic)", "note": "'Sure shot call', VIP group"},
    {"symbol": "ASIANPAINT", "direction": "up", "posted_on": "2025-05-06", "decision": "research",
     "source_label": "Demo Channel C (synthetic)", "note": "Calm YouTube breakout call"},
]


def demo_seed() -> list[dict]:
    return [{**e, "provenance": config.SYNTHETIC_LABEL} for e in DEMO_SEED]


def summarize(entries: list[dict], prices, horizon: int = config.MAIN_HORIZON) -> dict:
    rows, problems = [], []
    for i, e in enumerate(entries[:200]):
        try:
            decision = e["decision"]
            direction = str(e["direction"]).lower()
            posted = dt.date.fromisoformat(str(e["posted_on"]))
            symbol = str(e["symbol"]).upper()
            if decision not in DECISIONS or direction not in ("up", "down"):
                raise ValueError("decision or direction")
        except (KeyError, ValueError, TypeError):
            problems.append(f"Entry {i + 1} is missing a field or has a wrong value.")
            continue
        h = score_tip(Tip(f"j{i}", "journal", "journal", symbol, direction, posted), prices).horizons[horizon]
        claimed = None
        if h.status == "scored":
            claimed = h.excess_return if direction == "up" else -h.excess_return
        rows.append({
            "symbol": symbol, "direction": direction, "posted_on": posted.isoformat(), "decision": decision,
            "decision_label": DECISIONS[decision], "source_label": e.get("source_label", ""), "note": e.get("note", ""),
            "provenance": str(e.get("provenance") or config.REAL_LABEL).upper(),
            "status": h.status, "stock_return": h.stock_return, "nifty_return": h.nifty_return,
            "vs_nifty_in_claimed_direction": None if claimed is None else round(claimed, 4),
        })

    groups = {}
    for decision, label in DECISIONS.items():
        scored = [r for r in rows if r["decision"] == decision and r["status"] == "scored"]
        avg = round(sum(r["vs_nifty_in_claimed_direction"] for r in scored) / len(scored), 4) if scored else None
        if not scored:
            text = f"{label}: no tips with a {horizon}-day result yet."
        else:
            trailed = sum(1 for r in scored if r["vs_nifty_in_claimed_direction"] < 0)
            text = (f"{label}: {len(scored)} tip{'s' if len(scored) != 1 else ''}. Over the {horizon} days after "
                    f"each post, the stock did {avg * 100:+.1f} points against the Nifty 50 in the direction the tip "
                    f"claimed, on average. {trailed} of {len(scored)} trailed the Nifty.")
        groups[decision] = {"label": label, "scored": len(scored), "avg_vs_nifty": avg, "text": text}

    provs = {r["provenance"] for r in rows}
    return {"rows": rows, "groups": groups, "problems": problems, "horizon_days": horizon,
            "provenance": provs.pop() if len(provs) == 1 else ("MIXED" if provs else None),
            "prices_provenance": config.REAL_LABEL}
