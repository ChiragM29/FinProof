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


COMPLETE_SHARE = 0.98  # a category counts as complete when we hold at least 98% of the names SEBI says it lists
NAME_CUTOFF = 92        # fuzzy score for "possible match by name" (never "verified")
SAME_NAME = 85          # fuzzy score for "the registered name matches this channel"


@dataclass
class Registry:
    entries: pd.DataFrame  # name, reg_no, category, validity
    saved_on: str | None
    coverage: dict[str, dict]  # category -> {"saved": n, "listed": n}

    @property
    def complete(self) -> bool:
        return bool(self.coverage) and all(c["saved"] >= COMPLETE_SHARE * c["listed"] for c in self.coverage.values())

    @property
    def size(self) -> int:
        return len(self.entries)


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
    short: str = ""
    reg_no: str | None = None
    registered_name: str | None = None
    category: str | None = None
    found_in: str | None = None
    name_matches: bool | None = None
    copy_saved_on: str | None = None
    copy_complete: bool = False
    list_size: int = 0
    coverage_text: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _coverage_text(reg: Registry) -> str:
    if not reg.coverage:
        return "Our saved copy of SEBI's list has no size information."
    parts = [f"{c['saved']:,} of {c['listed']:,} {CATEGORY_NAMES.get(k, k)}s" for k, c in reg.coverage.items()]
    return f"Saved copy of SEBI's list from {reg.saved_on}: " + ", ".join(parts) + "."


def check(reg_numbers: list[str], name: str | None, registry: Registry | None = None, *,
          where: str = "the post", found_in: dict[str, str] | None = None) -> SebiCheck:
    """Facts about a source against SEBI's lists. `where` names what was searched for a number (for the message);
    `found_in` maps a registration number to the part it was found in (title, description, ...)."""
    reg = registry or load_registry()
    common = dict(copy_saved_on=reg.saved_on, copy_complete=reg.complete, list_size=reg.size, coverage_text=_coverage_text(reg))
    if reg.entries.empty:
        return SebiCheck("not_checked", "SEBI list not loaded, so registration was not checked.", "Not checked: SEBI list not loaded", **common)
    found_in = found_in or {}
    the_list = f"SEBI's list (saved {reg.saved_on})" if reg.complete else "our saved copy of SEBI's list (the copy is incomplete)"

    for num in reg_numbers:
        num = num.upper()
        hit = reg.entries[reg.entries["reg_no"] == num]
        if not hit.empty:
            row = hit.iloc[0]
            cat = CATEGORY_NAMES.get(row["category"], row["category"])
            same = None if not name else fuzz.token_set_ratio(name.lower(), row["name"].lower()) >= SAME_NAME
            tail = "" if same is None else ("; the name matches this channel" if same
                                            else f"; the name doesn't match this channel ({name})")
            where_found = f" in the {found_in[num]}" if found_in.get(num) else ""
            return SebiCheck("registered",
                             f"Shows {num}{where_found} → registered to {row['name']} ({cat}){tail}.",
                             f"Shows {num} → registered to {row['name']}{tail}",
                             reg_no=num, registered_name=row["name"], category=cat, found_in=found_in.get(num),
                             name_matches=same, **common)
    if reg_numbers:
        num = reg_numbers[0].upper()
        where_found = f" in the {found_in[num]}" if found_in.get(num) else ""
        return SebiCheck("number_not_found", f"Shows {num}{where_found} → not in {the_list}.",
                         f"Shows {num} → not in SEBI's list" + ("" if reg.complete else " (copy incomplete)"),
                         reg_no=num, found_in=found_in.get(num), **common)

    if name:
        best = process.extractOne(name, reg.entries["name"].tolist(), scorer=fuzz.token_set_ratio, score_cutoff=NAME_CUTOFF)
        if best:
            row = reg.entries.iloc[best[2]]
            cat = CATEGORY_NAMES.get(row["category"], row["category"])
            return SebiCheck("name_match",
                             f"No SEBI registration number in {where}. Possible match by name only: {row['name']} "
                             f"({row['reg_no']}, {cat}). A similar name is not proof that it is the same person.",
                             f"Possible match by name only: {row['name']} ({row['reg_no']})",
                             reg_no=row["reg_no"], registered_name=row["name"], category=cat, **common)
        if reg.complete:
            return SebiCheck("name_not_found",
                             f"No SEBI registration number in {where}, and the name doesn't match any of "
                             f"{reg.size:,} registered analysts and advisers (list saved {reg.saved_on}).",
                             f"No SEBI number; the name doesn't match any of {reg.size:,} registered names", **common)
        return SebiCheck("name_not_found",
                         f"No SEBI registration number in {where}, and the name was not found in {the_list}.",
                         "No SEBI number; name not in the saved copy (copy incomplete)", **common)
    return SebiCheck("not_checked", f"No name or SEBI registration number in {where} to check.",
                     "No name or registration number to check", **common)
