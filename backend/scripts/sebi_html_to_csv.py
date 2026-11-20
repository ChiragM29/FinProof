"""Turn saved SEBI list pages into data/real/sebi_registry_<date>.csv.

SEBI's site blocks automated requests, so save the pages from a normal browser:
  Research Analysts:   https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRecognisedFpi=yes&intmId=14
  Investment Advisers: https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRecognisedFpi=yes&intmId=13
Save each page (Ctrl+S, "Webpage, HTML only") into one folder per category, then run:

  python scripts/sebi_html_to_csv.py --ra path/to/ra_pages --ia path/to/ia_pages --saved-on 2026-11-20
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
REAL = ROOT / "data" / "real"

BLOCK_RE = re.compile(r'class="fixed-table-body card-table"(.*?)(?=class="fixed-table-body card-table"|</table>|$)', re.S)
PAIR_RE = re.compile(r'<div class="title"><span>\s*(.*?)\s*</span></div><div class="value[^"]*"><span>(.*?)</span>', re.S)
TOTAL_RE = re.compile(r"of\s+([\d,]+)\s+records", re.I)


def parse_pages(folder: Path, category: str) -> tuple[list[dict], int]:
    rows, listed = [], 0
    for page in sorted(folder.glob("*.htm*")):
        text = page.read_text(encoding="utf-8", errors="replace")
        m = TOTAL_RE.search(text)
        if m:
            listed = max(listed, int(m.group(1).replace(",", "")))
        for block in BLOCK_RE.findall(text):
            fields = {html.unescape(k).strip(): html.unescape(re.sub("<[^>]+>", "", v)).strip() for k, v in PAIR_RE.findall(block)}
            if fields.get("Registration No."):
                rows.append({
                    "name": fields.get("Name", ""),
                    "reg_no": fields["Registration No."].upper(),
                    "category": category,
                    "validity": fields.get("Validity", ""),
                })
    return rows, listed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ra", type=Path, help="folder of saved Research Analyst pages")
    ap.add_argument("--ia", type=Path, help="folder of saved Investment Adviser pages")
    ap.add_argument("--saved-on", required=True, help="date the pages were saved, YYYY-MM-DD")
    args = ap.parse_args()

    rows, coverage = [], {}
    for cat, folder in (("RA", args.ra), ("IA", args.ia)):
        if folder:
            got, listed = parse_pages(folder, cat)
            got = list({r["reg_no"]: r for r in got}.values())
            rows += got
            coverage[cat] = {"saved": len(got), "listed": listed or len(got)}
    if not rows:
        print("No records found. Check the folders.", file=sys.stderr)
        return 1
    out = REAL / f"sebi_registry_{args.saved_on}.csv"
    pd.DataFrame(rows).assign(provenance="REAL").to_csv(out, index=False)
    out.with_suffix(".json").write_text(json.dumps({
        "saved_on": args.saved_on,
        "source": "sebi.gov.in Recognised Intermediaries pages, saved by hand",
        "coverage": coverage,
    }, indent=2), encoding="utf-8")
    print(f"Wrote {len(rows)} records to {out.name}: {coverage}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
