"""Download SEBI's full lists of registered Research Analysts and Investment Advisers.

Reads every page of sebi.gov.in's "Recognised Intermediaries" lists (25 names a page) and writes a dated snapshot:
  data/real/sebi_registry_<date>.csv   name, reg_no, category, validity, provenance
  data/real/sebi_registry_<date>.json  saved_on, source, coverage {category: {saved, listed}}

Run from backend/:  ..\\.venv\\Scripts\\python scripts\\fetch_sebi_lists.py
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
REAL = ROOT / "data" / "real"
BASE = "https://www.sebi.gov.in"
LISTS = {"RA": 14, "IA": 13}  # SEBI's intermediary ids
PER_PAGE = 25

# SEBI's first page uses double quotes and the paged (AJAX) responses single quotes, so both are accepted.
BLOCK_RE = re.compile(r"""class=["']fixed-table-body card-table["'](.*?)(?=class=["']fixed-table-body card-table["']|</table>|$)""", re.S)
PAIR_RE = re.compile(r"""<div class=["']title["']><span>\s*(.*?)\s*</span></div><div class=["']value[^"']*["']><span>(.*?)</span>""", re.S)
TOTAL_RE = re.compile(r"of\s+([\d,]+)\s+records", re.I)


def parse(text: str, category: str) -> list[dict]:
    rows = []
    for block in BLOCK_RE.findall(text):
        f = {html.unescape(k).strip(): html.unescape(re.sub("<[^>]+>", "", v)).strip() for k, v in PAIR_RE.findall(block)}
        if f.get("Registration No."):
            rows.append({"name": f.get("Name", ""), "reg_no": f["Registration No."].upper().strip(), "category": category,
                         "validity": f.get("Validity", ""), "provenance": "REAL"})
    return rows


UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
PARTS = ROOT / "data" / "cache" / "sebi_pages"  # one JSON file per downloaded page, so a dropped connection can resume


def _open(intm: int) -> tuple[requests.Session, requests.Response]:
    s = requests.Session()
    s.headers["User-Agent"] = UA
    first = s.get(f"{BASE}/sebiweb/other/OtherAction.do?doRecognisedFpi=yes&intmId={intm}", timeout=40)
    first.raise_for_status()
    return s, first


def fetch(category: str, intm: int) -> tuple[list[dict], int]:
    PARTS.mkdir(parents=True, exist_ok=True)
    session, first = _open(intm)
    listed = int(TOTAL_RE.search(first.text).group(1).replace(",", ""))
    rows = parse(first.text, category)
    pages = -(-listed // PER_PAGE)
    for page in range(1, pages):
        part = PARTS / f"{category}_{page:04d}.json"
        if part.exists():
            rows += json.loads(part.read_text(encoding="utf-8"))
            continue
        form = dict(nextValue="1", next="n", intmId=str(intm), contPer="", name="", regNo="", email="", location="",
                    exchange="", affiliate="", alp="", language="2", model="", esgCategory="", doDirect=str(page), intmIds="")
        for attempt in range(6):
            try:
                r = session.post(f"{BASE}/sebiweb/ajax/other/getintmfpiinfo.jsp", data=form, timeout=40,
                                 headers={"Referer": first.url, "X-Requested-With": "XMLHttpRequest", "Origin": BASE})
                got = parse(r.text, category) if r.ok and "Request Blocked" not in r.text else []
            except requests.RequestException:
                got = []
            if got:
                rows += got
                part.write_text(json.dumps(got), encoding="utf-8")
                break
            time.sleep(2 * (attempt + 1))
            try:
                session, first = _open(intm)  # a fresh session after SEBI drops or blocks one
            except requests.RequestException:
                pass
        else:
            print(f"  {category} page {page + 1}: no rows after 6 tries", file=sys.stderr)
        time.sleep(0.6)
        if page % 10 == 0:
            print(f"  {category}: page {page + 1} of {pages}, {len(rows)} rows", flush=True)
    unique = list({r["reg_no"]: r for r in rows}.values())
    return unique, listed


def main() -> int:
    today = dt.date.today().isoformat()
    rows, coverage = [], {}
    for cat, intm in LISTS.items():
        got, listed = fetch(cat, intm)
        print(f"{cat}: saved {len(got)} of {listed}")
        rows += got
        coverage[cat] = {"saved": len(got), "listed": listed}
    csv_path = REAL / f"sebi_registry_{today}.csv"
    pd.DataFrame(rows, columns=["name", "reg_no", "category", "validity", "provenance"]).to_csv(csv_path, index=False)
    csv_path.with_suffix(".json").write_text(json.dumps({
        "saved_on": today,
        "source": "sebi.gov.in Recognised Intermediaries: Research Analysts (intmId 14) and Investment Advisers (intmId 13), every page",
        "coverage": coverage}, indent=2), encoding="utf-8")
    print("wrote", csv_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
