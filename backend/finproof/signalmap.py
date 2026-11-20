"""Signal Map: every source in the ledger on two separate axes.

  across: "Were they right before?"  share of scored calls that beat the Nifty 50 at 30 days
  up:     "Are they playing fair?"   share of calls with no pump pattern in the prices (no unusual volume in the
                                      3 sessions before the call, no sharp fall after it)

Only sources with ledger data are plotted; those with fewer than 10 scored calls are listed as "not enough history".
"""

from __future__ import annotations

from . import config, pumpdump


def build(ledger, prices) -> dict:
    plotted, thin = [], []
    for sid, tips in ledger.sources().items():
        rec, _ = ledger.record(sid)
        checked = pumpy = 0
        for tip in tips:
            sig = pumpdump.market_signals(tip.symbol, tip.posted_on, prices, include_after=True)
            if sig.status != "ok":
                continue
            checked += 1
            pumpy += bool({"volume_spike", "fell_after"} & set(sig.flags))
        row = {"source_id": sid, "source_label": rec.source_label, "provenance": rec.provenance, "calls": rec.tips_total,
               "scored": rec.scored, "worked": rec.worked, "right": rec.hit_rate,
               "fair": round(1 - pumpy / checked, 3) if checked else None, "checked": checked, "pump_calls": pumpy}
        (plotted if rec.enough_history and row["fair"] is not None else thin).append(row)
    return {"plotted": plotted, "not_enough_history": thin, "min_calls": config.MIN_TIPS_FOR_RECORD,
            "axes": {"x": "Were they right before? Share of calls that beat the Nifty 50 at 30 days",
                     "y": "Are they playing fair? Share of calls with no pump pattern in the prices"},
            "note": "Two separate questions: a source can be honest but wrong, or right but unfair."}
