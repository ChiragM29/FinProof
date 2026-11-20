"""Exchange surveillance: NSE's own ASM, GSM and ESM lists, from a dated snapshot in data/real.

These are the exchange's current lists (each entry carries NSE's own date), not the lists on the post date, so
the label always says "as of". A stock not on the lists is reported as such; BSE's lists are not checked.
"""

from __future__ import annotations

import json
from functools import lru_cache

from . import config


@lru_cache(maxsize=1)
def snapshot() -> dict:
    files = sorted(config.REAL.glob("nse_surveillance_*.json"))
    if not files:
        return {"index": {}, "as_of": None, "file": None}
    data = json.loads(files[-1].read_text(encoding="utf-8"))
    index: dict[str, list[dict]] = {}

    def add(row: dict, measure: str, stage: str | None, when: str | None) -> None:
        sym = str(row.get("symbol") or "").strip().upper()
        if sym:
            index.setdefault(sym, []).append({"measure": measure, "stage": stage, "desc": row.get("survDesc"), "as_of": when})

    for part in ("longterm", "shortterm"):
        for row in (data["lists"].get("ASM") or {}).get(part, {}).get("data", []):
            add(row, f"{'Long' if part == 'longterm' else 'Short'}-term ASM", row.get("asmSurvIndicator"), row.get("asmTime"))
    for row in data["lists"].get("GSM") or []:
        add(row, "GSM", row.get("gsmStage"), (row.get("gsmTime") or "")[:11])
    for row in data["lists"].get("ESM") or []:
        add(row, "ESM", row.get("esmSurvIndicator"), row.get("esmTime"))
    return {"index": index, "as_of": data.get("fetched_at", "")[:10], "file": files[-1].name}


def check(symbol: str | None, exchange: str = "NSE") -> dict | None:
    """None when there is no snapshot. Otherwise the stock's entries (empty when it is not on the lists)."""
    snap = snapshot()
    if not snap["file"] or not symbol:
        return None
    if exchange == "BSE":
        return {"checked": False, "entries": [], "as_of": snap["as_of"]}
    return {"checked": True, "entries": snap["index"].get(symbol.upper(), []), "as_of": snap["as_of"]}
