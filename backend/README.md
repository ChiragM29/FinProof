# backend

Python + FastAPI. Every check runs here; the extension and dashboard only display the result.

| Module | Job |
|---|---|
| `finproof/market.py` | NSE daily prices from Yahoo Finance with an on-disk cache; NSE company list; old → new symbol mapping |
| `finproof/ledger.py` | Loads tips and scores each one against the Nifty 50 at 7, 30 and 90 days; per-source track record |
| `finproof/extract.py` | Finds stocks, direction, prices named, stop-loss, pressure phrases and SEBI numbers in text |
| `finproof/youtube.py` | Video title, channel, publish date and time, description and transcript; online first, cache as fallback |
| `finproof/net.py` | Hybrid mode: is the network there (cached 30-second probe); `HYBRID · LIVE` or `HYBRID · CACHE` |
| `finproof/social.py` | Instagram and X/Twitter links: platform detection, public oEmbed/OpenGraph fetch (4 s), cache, "paste the caption" fallback, two SYNTHETIC demo posts |
| `finproof/media.py` | Media & Impersonation Flags: famous-name and regulator bait, scam funnels, video/social calls with no context |
| `finproof/meta.py` | Zero manual entry: finds the post date/time and source in WhatsApp/Telegram headers, @handles, dates in the text |
| `finproof/ai.py` | Optional Claude answers for the Claim Auditor, grounded in the card; 3-second timeout, cool-down after network failures, no-advice and signal-word check; falls back to the local engine |
| `finproof/sebi.py` | Looks a source up in the saved copy of SEBI's lists and says how complete that copy is |
| `finproof/pumpdump.py` | Volume spike (3 sessions before the post vs the 20 before that), run-up, thin trading (20-day traded value), fall-after |
| `finproof/card.py` | Builds the card and refuses any buy/sell/hold wording; UPI, "educational only" and split-scale checks |
| `finproof/auditor.py` | Claim Auditor: answers questions from the card only, as a cited brief (headline, tagged facts, mentor's note); indicator and beginner-concept answers; refuses advice questions |
| `finproof/indicators.py` | SMA 20, EMA 50, rolling VWAP 20D, Bollinger (20, 2), RSI 14, MACD (12, 26, 9), ATR 14, key levels; point-in-time snapshot for cards; plain-English explanations |
| `finproof/veteran.py` | Veteran's Desk Note: mentor-voice "what is wrong / what is right" and the raw signals behind it, from the card only |
| `finproof/chart.py` | Candles, volume (with each day's ratio to its prior 20-day average), the Nifty 50 and every indicator series for the chart |
| `finproof/journal.py` | Noise journal: 30-day look-back of skipped / set-aside tips vs the Nifty 50; Demo Investor seed |
| `finproof/study.py` | Decision test: tip sets, group rotation, answer log, statistics |
| `finproof/api.py` | HTTP API and the dashboard |
| `tests/` | 250 tests: auto-detection, no-advice checks on cards, Desk Notes, auditor answers and the dashboard's own text; indicator math; hybrid AI fallback; hybrid fetching and social links (no real network in tests); media cues; no future data in point-in-time cards |

## Scripts

| Script | What it does |
|---|---|
| `scripts/warm_cache.py` | Downloads prices and videos once and writes the two SYNTHETIC demo posts (X, Instagram), so the demo runs offline |
| `scripts/make_synthetic_tips.py` | Rebuilds the labelled SYNTHETIC demo tips |
| `scripts/make_practice_test.py` | Rebuilds the practice tip set for the decision test |
| `scripts/check_test_set.py` | Checks a decision-test tip set (labels, balance, cards) before a session |
| `scripts/sebi_html_to_csv.py` | Converts SEBI list pages saved from a browser into `data/real/sebi_registry_<date>.csv` |

## Scoring rule

- Entry: closing price on the first trading day on or after the post date.
- Exit after N days: closing price on the last trading day on or before post date + N.
- A tip matched its claim if the stock beat the Nifty 50 over the same dates in the claimed direction.
- A source needs at least 10 scored tips before a percentage is shown.
