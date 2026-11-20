"""Check a source against our saved copy of SEBI's registered lists.

We state facts only ("found" / "not found in our saved copy"), never legal verdicts.
The copy may be incomplete, so every answer says how much of SEBI's list it covers.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from functools import lru_cache

import pandas as pd
from rapidfuzz import fuzz, process

from . import config

CATEGORY_NAMES = {"RA": "Research Analyst", "IA": "Investment Adviser"}


@dataclass
class Registry:
    entries: pd.DataFrame  # name, reg_no, category, validity
    saved_on: str | None
    coverage: dict[str, dict]  # category -> {"saved": n, "listed": n}

    @property
    def complete(self) -> bool:
        return bool(self.coverage) and all(c["saved"] >= c["listed"] for c in self.coverage.values())


@lru_cache(maxsize=1)
def load_registry() -> Registry:
    files = sorted(config.REAL.glob("sebi_registry_*.csv"))
    if not files:
        return Registry(pd.DataFrame(columns=["name", "reg_no", "category", "validity"]), None, {})
    df = pd.read_csv(files[-1], dtype=str, keep_default_na=False)
    df["reg_no"] = df["reg_no"].str.upper().str.strip()
    meta_path = files[-1].with_suffix(".json")
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    return Registry(df, meta.get("saved_on"), meta.get("coverage", {}))


@dataclass
class SebiCheck:
    status: str  # registered | number_not_found | name_match | name_not_found | not_checked
    text: str
    reg_no: str | None = None
    registered_name: str | None = None
    category: str | None = None
    copy_saved_on: str | None = None
    copy_complete: bool = False
    coverage_text: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _coverage_text(reg: Registry) -> str:
    if not reg.coverage:
        return "Our saved copy of SEBI's list has no size information."
    parts = [f"{c['saved']:,} of {c['listed']:,} {CATEGORY_NAMES.get(k, k)}s" for k, c in reg.coverage.items()]
    return f"Saved copy of SEBI's list from {reg.saved_on}: " + ", ".join(parts) + "."


def check(reg_numbers: list[str], name: str | None, registry: Registry | None = None) -> SebiCheck:
    reg = registry or load_registry()
    common = dict(copy_saved_on=reg.saved_on, copy_complete=reg.complete, coverage_text=_coverage_text(reg))
    if reg.entries.empty:
        return SebiCheck("not_checked", "SEBI list not loaded, so registration was not checked.", **common)

    for num in reg_numbers:
        hit = reg.entries[reg.entries["reg_no"] == num.upper()]
        if not hit.empty:
            row = hit.iloc[0]
            cat = CATEGORY_NAMES.get(row["category"], row["category"])
            return SebiCheck("registered", f"Registration number {num.upper()} is on SEBI's list as a {cat}.",
                             reg_no=num.upper(), registered_name=row["name"], category=cat, **common)
    if reg_numbers:
        where = "SEBI's list" if reg.complete else "our saved copy of SEBI's list (the copy is incomplete)"
        return SebiCheck("number_not_found",
                         f"The post quotes {', '.join(n.upper() for n in reg_numbers)}, which is not in {where}.",
                         reg_no=reg_numbers[0].upper(), **common)

    if name:
        best = process.extractOne(name, reg.entries["name"].tolist(), scorer=fuzz.token_set_ratio, score_cutoff=92)
        if best:
            row = reg.entries.iloc[best[2]]
            cat = CATEGORY_NAMES.get(row["category"], row["category"])
            return SebiCheck("name_match",
                             f"A {cat} with a similar name is on SEBI's list ({row['reg_no']}). "
                             "The post gives no registration number, so this may be a different person.",
                             reg_no=row["reg_no"], registered_name=row["name"], category=cat, **common)
        where = "SEBI's list" if reg.complete else "our saved copy of SEBI's list (the copy is incomplete)"
        return SebiCheck("name_not_found",
                         f"No registration number in the post, and the name was not found in {where}.", **common)
    return SebiCheck("not_checked", "No name or registration number to check.", **common)
