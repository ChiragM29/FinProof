"""Download and cache everything the demo needs, so it can run with FINPROOF_OFFLINE=1.

  python scripts/warm_cache.py                      # prices (OHLCV) for every demo stock + sample cards
  python scripts/warm_cache.py VIDEO_ID VIDEO_ID    # also cache these YouTube videos

Covers: the tip ledger, the dashboard samples (incl. the SYNTHETIC demo X post and Instagram reel), the decision-test tip sets, the Demo Investor
journal, and the chart data (candles, volume, Nifty 50) for all of their stocks.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finproof import config, journal, social, youtube  # noqa: E402
from finproof.card import build_card  # noqa: E402
from finproof.chart import WATCHLIST, chart_payload  # noqa: E402
from finproof.ledger import Ledger  # noqa: E402
from finproof.market import YahooPrices  # noqa: E402

# The made-up sample posts on the Command Center (same stocks and dates as dashboard/cc.js SAMPLES).
SAMPLES = [
    ("BUY TATAMOTORS CMP 712 TGT 780/820 SL 690. 100% guaranteed profit. Join our VIP group before 3 pm!", "2025-06-02", ""),
    ("Bhai SBIN abhi le lo, operator ne bola hai big news coming. Paisa double pakka. Target 900, jaldi karo!", "2025-02-03", ""),
    ("Join our VIP calls for just ₹999/month, pay to stockguru.calls@ybl\nBUY ITC CMP 418 TGT 460 SL 400", "2025-06-02", ""),
    ("For educational purposes only, not SEBI registered.\nKOTAKBANK breakout, CMP 1930, target 2050, SL 1880", "2025-02-10", ""),
    ("ICICIBANK looking bullish here, tgt 1500 sl 1350", "2025-08-04", "Demo Channel A (synthetic)"),
]


def main(video_ids: list[str]) -> int:
    start = time.time()
    prices = YahooPrices(max_age_hours=0)  # force a fresh download
    ledger = Ledger(prices)
    symbols = {config.BENCHMARK}
    for sid in ledger.sources():
        rec, scored = ledger.record(sid)
        symbols |= {s.tip.symbol for s in scored}
        print(f"{rec.source_label}: {rec.scored} scored tips")
    for text, day, source in SAMPLES:
        card = build_card(text=text, ledger=ledger, prices=prices, posted_on=dt.date.fromisoformat(day),
                          posted_on_note="warm", channel=source or None, source_key=source or None)
        symbols |= {c["symbol"] for c in card["claims"] if c["symbol"]}
    for path in sorted((config.ROOT / "eval" / "decision_test").glob("tips_*.json")):
        symbols |= {t["symbol"] for t in json.loads(path.read_text(encoding="utf-8")).get("tips", [])}
    symbols |= {e["symbol"] for e in journal.demo_seed()} | set(WATCHLIST)
    for vid in video_ids:
        vid = youtube.video_id(vid)
        if not vid:
            continue
        data = youtube.fetch_video(vid)
        print(f"video {vid}: {data.get('title')!r}, transcript {'yes' if data.get('transcript') else 'no'}")
        text = "\n".join([data.get("title") or "", data.get("description") or "", data.get("transcript") or ""])
        day = dt.date.fromisoformat(data["published_on"]) if data.get("published_on") else dt.date.today()
        card = build_card(text=text, ledger=ledger, prices=prices, posted_on=day, posted_on_note="warm")
        symbols |= {c["symbol"] for c in card["claims"] if c["symbol"]}

    for url in social.write_demo_cache():  # one X post and one Instagram reel, both SYNTHETIC
        print(f"demo post cached (SYNTHETIC): {url}")
    for post in social.DEMO_POSTS.values():
        card = build_card(text=post["text"], ledger=ledger, prices=prices, posted_on=dt.date.fromisoformat(post["posted_on"]),
                          posted_on_note="warm", kind=post["platform"])
        symbols |= {c["symbol"] for c in card["claims"] if c["symbol"]}

    missing = []
    for sym in sorted(symbols):
        if sym.startswith("^"):
            prices.history(sym)
            continue
        if chart_payload(sym, prices) is None:
            missing.append(sym)
    print(f"Chart data cached for {len(symbols) - len(missing)} symbols (incl. Nifty 50).")
    if missing:
        print("No price data for:", ", ".join(missing))
    print(f"Cache ready in {time.time() - start:.0f}s. Run the server with FINPROOF_OFFLINE=1 for the demo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
