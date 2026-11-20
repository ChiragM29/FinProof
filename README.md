# FinProof

**Check the tipper before you trust the tip.**

We don't rate stocks. We keep score on the people who tip them.

FinProof records stock tips posted by finfluencers on YouTube, Telegram and WhatsApp, then checks each tip against what the market actually did afterwards. A retail investor can see a source's real track record before acting on its next tip.

Built by **VVCE Builders** at **The Big Hack 2.0**, Bengaluru — Track 01 (Finance), problem **F3: Signal versus noise for retail investors**.

---

## The problem

- India has more than 21 crore demat accounts. Young investors open about three in four new ones.
- 62% of investors say finfluencers influence their decisions (SEBI Investor Survey 2025).
- 91% of individual F&O traders lost money in 2024-25, a net loss of ₹1.06 lakh crore (SEBI study).
- In 2026 SEBI barred seven unregistered finfluencers over an alleged ₹20 crore social-media scheme.
- **Nobody tracks most tips over time**, so an investor cannot see which sources were right in the past.

**The challenge:** build a tool that measurably improves how a retail investor makes decisions, without ever telling them what to buy or sell.

## What FinProof does

1. **Tip ledger.** Stores real public tips (stock, direction, date posted, source) and scores each one against the Nifty 50 at 7, 30 and 90 days.
2. **Credibility card.** Shown on a YouTube finance video, or for a pasted message or screenshot:
   - whether the source is on SEBI's registered list (research analysts and investment advisers)
   - the source's track record from the ledger, or "not enough history" below about 10 tips
   - the claim itself: the stock, any target, and pressure phrases such as "guaranteed"
   - whether trading volume spiked before the post
   - a **REAL** or **SYNTHETIC** label on every line
3. **Pump-and-dump check.** Combines a volume and price anomaly check with hype-language signals, tested on cases SEBI has ruled on.
4. **Decision test.** A controlled study showing that people shown the card act on fewer bad tips while still trusting good ones.

## What FinProof never does

- It never says buy, sell, hold, accumulate or exit, and never gives a target price or calls a stock "safe". An automated test checks every card text for this language.
- It rates the **source and the claim**, never the stock.
- It states facts, not legal verdicts: "Not on SEBI's registered list", never "illegal".
- It does not put a computed success rate next to a real person's name. Only people named in SEBI orders (public record) are named; other sources appear as Channel A, B, C.

## Real vs synthetic data

The Finance track requires us to say which data is real and which is synthetic. Every record carries a `provenance` field, and the card shows it. See [data/README.md](data/README.md) for the full list.

| Data | Type |
|---|---|
| NSE daily prices and volumes, Nifty 50 | REAL |
| SEBI registered research analyst and investment adviser list (dated snapshot) | REAL |
| Public tips collected from YouTube and Telegram | REAL |
| SEBI pump-and-dump orders used as known cases | REAL |
| Demo filler sources and tips | SYNTHETIC (labelled) |

## Repository layout

```
finproof/
├── backend/      Python + FastAPI: ledger, market data, SEBI lookup, tip extraction, pump-and-dump check, card API
├── extension/    Chrome extension that shows the credibility card on YouTube
├── dashboard/    Web app: paste a link, message or screenshot and see the card
├── data/         real/ and synthetic/ data, kept apart
├── eval/         decision test, extraction accuracy, pump-and-dump detection results
└── docs/         architecture notes, pitch material, failure cases
```

## Evidence we will report

| Question | How we measure it |
|---|---|
| Does the card improve decisions? | Split-group decision test, 20-30 people, 12 real past tips |
| Does extraction find the right tip? | Accuracy on about 50 hand-labelled videos and messages |
| Does the pump-and-dump check work? | Catch rate and false alarms on SEBI cases vs random stock-days, against a simple volume-spike rule |
| Where does it fail? | Documented failure cases in [eval/README.md](eval/README.md) |

## Team

Team **VVCE Builders**.

| Member | Owns |
|---|---|
| Thaha Ahmed Baig (team leader) | [TEAM: fill in, e.g. pitch, decision study] |
| Chirag M | [TEAM: fill in, e.g. backend and data] |
| Salahudheen Ayyubhi | [TEAM: fill in] |
| R P Jeetender Singh | [TEAM: fill in] |

## How we work

- Everyone commits from their own GitHub account, in small commits, every hour or two.
- Pull before you push: `git pull --rebase`, then `git push`.
- Never commit `.env` or any key. Copy `.env.example` to `.env` and fill it locally.
- API keys stay on the backend, never in the extension.

## What works now

| Part | Status |
|---|---|
| Tip scoring against the Nifty 50 at 7, 30 and 90 days, on real NSE prices | Done |
| Extraction from messages and YouTube (title, description, transcript): stocks, direction, prices named, stop-loss, pressure phrases, SEBI numbers | Done, rule-based |
| Old NSE symbols mapped to today's (TATAMOTORS → TMPV, ZOMATO → ETERNAL) | Done |
| Pump-and-dump signs: volume spike, run-up, thin trading, fall after the post, BE/BZ series | Done; thresholds not tuned yet |
| SEBI lookup from a saved copy of SEBI's lists | Done; copy has only 25 of 2,404 research analysts so far |
| Card with no buy/sell wording, enforced by tests | Done |
| Forensic Command Center at `/`: scanner, auto-detected date/source/ticker pills, 4 KPI cards, candlestick chart with tip pin and volume spike, Credibility X-Ray, Veteran's Desk Note, docked Claim Auditor, Noise Journal, 6-step Judge Tour | Done |
| Veteran's Desk Note: "What is wrong here" / "What is right" in a calm mentor voice, built only from the scan's numbers; **Beginner Mentor View / Raw Forensic Signals** toggle; readable flag names; findings read from a sample post labelled SYNTHETIC | Done |
| Technical analysis suite (all computed locally from cached OHLCV): SMA 20, EMA 50, VWAP (20D), Bollinger (20, 2), Key Levels (30-session and 52-week high/low), 20D Vol Avg, RSI (14) and MACD (12, 26, 9) panes, ATR (14) "Avg Daily Swing" in the legend; live crosshair readout and a `?` explainer | Done |
| Hybrid Claim Auditor: Claude when a key is set, local engine otherwise; buy/sell questions stopped before any API call; 3-second timeout, cool-down after a network failure, no-advice check on every AI reply; answers as a cited brief (headline → [SEBI] [NSE 30D] [Volume] [Quote] [Tech] facts → Mentor's note); beginner Q&A on indicators and concepts | Done |
| Zero manual entry: date, time, source and ticker detected from WhatsApp/Telegram headers, @handles, dates in the post or YouTube metadata; clear fallbacks (latest NSE session, Unattributed Forward) | Done |
| Chart engine: candlestick + volume chart (TradingView Lightweight Charts 5.3.0, bundled locally), tip pins, Nifty 50 overlay, 7D/30D/90D/1Y; volume bars above 5× the 20D average drawn capped (true value in the readout) | Done |
| Volume radar: spike = biggest volume in the 3 sessions before the post ≥ 2.5× the 20-day average; thin trading = 20-day average traded value under ₹1 crore | Done |
| India checks: personal UPI ID for paid calls (vs SEBI's '@valid' handles), "educational only" loophole, split-adjusted price check | Done |
| Claim Auditor: answers only from the card, offline, refuses buy/sell/hold and price questions | Done |
| Demo Investor login (no password, this browser only) and noise journal with 30-day look-back vs Nifty | Done |
| Chrome extension card on YouTube | Done |
| Hybrid mode: online first (live YouTube, X and Instagram fetches, fresh prices), automatic fallback to the local cache; header shows `HYBRID · LIVE` or `HYBRID · CACHE`; `FINPROOF_OFFLINE=1` forces cache only | Done |
| Instagram and X/Twitter links: platform detected automatically; public text fetched online (X oEmbed, Instagram OpenGraph, 4-second timeout); when a platform blocks the fetch, an inline box asks for the caption with the link kept; two SYNTHETIC demo posts cached for offline use | Done |
| Media & Impersonation Flags: famous-name and regulator bait ("leaked interview", "RBI approved", AI trading bots), scam funnels ("link in bio", free VIP groups, fixed daily profit), and video/social calls with no registration number and no word about risk; observed cues, never a claim that a clip is fake | Done |
| Decision test: participant page, 4-group counterbalancing, point-in-time cards, live results with CIs and CSV export | Done; practice set only |
| Real tips collected into `data/real/tips_real.csv` | To do |
| Full SEBI list saved | To do |
| Real tip set for the decision test (`eval/decision_test/tips_real.json`) and 20-30 participants | To do |
| Extraction accuracy, pump-and-dump evaluation | To do |

## Getting started (Windows PowerShell)

```powershell
cd finproof
python -m venv .venv
.venv\Scripts\python -m pip install -r backend\requirements.txt
cd backend
..\.venv\Scripts\python -m pytest
..\.venv\Scripts\python -m uvicorn finproof.api:app --port 8000
```

Open http://localhost:8000: FinProof opens with a sample case already scanned. Paste any WhatsApp/Telegram forward or YouTube link and press **Scan Tip**; click **▶ Judge Tour** for the 7-step walkthrough (Problem Map → a WhatsApp tip and its label → the real SEBI case on BSE → track record and Signal Map → Decision Study → Failure Cases → the refusal). The full talk track is in [DEMO-SCRIPT.md](DEMO-SCRIPT.md). (`/terminal` now redirects to `/`.)

## Round 2: what each line of the brief maps to

| The brief says | FinProof's answer |
|---|---|
| "A few finfluencers are registered with SEBI. Most are not." | SEBI registration check against a dated copy of SEBI's research analyst and investment adviser lists |
| "Some tips are honest but wrong." | "Were they right before?": the ledger track record, kept separate from fairness |
| "Others are part of pump-and-dump schemes." | Pump-pattern check (volume before the post, price after it) and a real SEBI case on BSE (Sadhna Broadcast) |
| "Nobody tracks most tips over time..." | The tip ledger, the Sources tab with the Signal Map, and 7/30-day outcomes in the Noise Journal |
| "Retail investors act on information whose quality they cannot judge" | The Signal or Noise label and the Veteran's Desk explanations |
| "get much of their information from social media" | WhatsApp, Telegram, YouTube, X and Instagram input, the Chrome extension, and a reply card in English, Kannada and Hindi |
| "measurably improves how a retail investor makes decisions" | The Decision Study: crossover design, metrics fixed in advance, live results |
| "without ever telling them what to buy or sell" | The no-advice test over every string, the Claim Auditor's refusal card, past prices only |

**The Signal or Noise label** sits at the top of the right panel. "Were they right before?" shows the source's record (N calls, the share that beat the Nifty 50 at 30 days, the period); below 10 calls it says "Not enough history". "Are they playing fair?" lists SEBI registration (with the snapshot date), conflict disclosure, pressure signals, the payment route (personal UPI vs SEBI-validated @valid), the pump pattern, liquidity and NSE surveillance status (dated snapshot). One line gives the message type: Education, Opinion, Unverified tip, Pressure pitch or Pump pattern. Every line has a REAL or SYNTHETIC tag and a "why" that cites the rule or the source.

**BSE fallback.** NSE first; BSE when NSE has no data or the post writes `BSE:<SYMBOL>`. A bare "BSE" is the company BSE Ltd (now a Nifty 50 stock) only when written #BSE, $BSE or "BSE Ltd". Every ticker shows NSE or BSE.

**Price History** (not "research", a regulated term): type a Nifty 50 ticker or company name, or use the **Nifty 50 ▾** search, to see that stock's chart with past prices only. No post, so no flags.

## The Command Center, piece by piece

**Layout.** One scanner bar (with a **Samples ▾** menu of SYNTHETIC demo posts and links), then the chart and the side panel (Veteran's Desk, Claim Auditor, Noise Journal). Under the chart: a one-line caption with date, source, ticker and platform (with Edit), the four key signals, and the Credibility X-Ray.

**Hybrid mode.** FinProof goes online first and falls back to the cache on its own: the header pill shows `HYBRID · LIVE` or `HYBRID · CACHE`. Only `FINPROOF_OFFLINE=1` forces cache-only, for a rehearsed demo on bad Wi-Fi.

**Links.** Paste a YouTube, Instagram (`/p/`, `/reel/`) or X/Twitter (`x.com`, `twitter.com`) link. YouTube gives title, channel, publish time in IST, description and transcript. X posts come through X's public oEmbed and Instagram through its public page metadata, each with a 4-second timeout. Both platforms often block automated reads; then FinProof shows a quiet box asking for the caption, keeping the platform and link, and audits what you paste.

**Media & Impersonation Flags.** Cues common in fake-video and social-media stock scams: borrowed famous names or regulators, "leaked interview" and AI-bot stories, funnels to private groups or fixed-profit promises, personal UPI IDs, and price calls on videos or reels with no registration number and no mention of risk. They appear in the X-Ray, the Desk Note and the Claim Auditor. FinProof reads the post's words and market data, not the video file, so it reports cues and never claims a clip is fake.

**Auto-extraction (zero manual entry).** FinProof reads the date, time (IST), source and ticker from the post itself:

| Format | Example |
|---|---|
| WhatsApp (Android) | `03/02/25, 10:15 am - Rakesh Bhai: ...` |
| WhatsApp (iPhone) | `[02/06/2025, 9:42 am] Stock Guru VIP: ...` |
| Telegram forward | `Forwarded from Fin Hype Calls (@FinHypeCalls)` then `June 2, 2025 9:42 AM` |
| Handles and dates in the text | `@MarketGyaanDaily · 10 Feb 2025`, Indian dd/mm dates, "today" / "yesterday" |
| YouTube link | channel name and publish date/time from the video |
| X / Twitter link | author and post date from the public post |
| Instagram link | account and caption when public, otherwise the account in the link plus the caption you paste |

If nothing is found, the date falls back to the latest NSE session and the source to "Unattributed Forward"; each pill says Auto, Fallback or Edited, and **Edit** lets you override both.

**Veteran's Desk Note.** The first tab on the right. *Beginner Mentor View* explains each warning sign in plain words ("What is wrong here") and the checking habits that apply ("What is right"), plus what the chart showed before the post. A calm post gets an honest, balanced note rather than praise. *Raw Forensic Signals* lists every number and quote behind those sentences, each with its own REAL or SYNTHETIC label. Every sentence is built from the scan; tests check that it never gives advice and never prints a number that is not in the scan.

**Technical analysis suite.** One click each, above the chart: SMA 20 (amber), EMA 50 (cyan), VWAP 20D (violet), Bollinger (20, 2), Key Levels (30-session and 52-week high/low, as of the session before the post), RSI (14) and MACD (12, 26, 9) in their own lower panes. The default chart stays clean: candles, tip pin, volume and its 20D average. The legend always shows the ATR (14) average daily swing and updates with the crosshair. Indicators describe what prices already did; they are never shown as signals.

**Claim Auditor (online or offline).** Four one-tap prompts: *Should I buy this?* (always the red guardrail card), *Why flagged?*, *Source record* and *Volume & chart check*. With `ANTHROPIC_API_KEY` in `finproof/.env`, Claude answers from the card's facts only; without it, or with no Wi-Fi, the local engine answers. Buy/sell/hold/target questions get the red No-Advice Guardrail card before any API call. A live answer that times out (3 s), fails, or contains advice or signal words is replaced by the local answer. Both engines answer as a short brief: a headline, facts tagged [SEBI] [NSE 30D] [Volume] [Quote] [Tech], and a one-line Mentor's note. The local engine also explains indicators (RSI, MACD, VWAP, ATR, Bollinger, SMA, EMA, key levels) and beginner concepts (pump and dump, why compare with the Nifty 50, SEBI registration, thin liquidity, personal UPI IDs) using the stock's own numbers.

**Extension:** open `chrome://extensions`, turn on Developer mode, click **Load unpacked** and choose the `extension` folder. Keep the backend running, then open any YouTube video.

**Demo without internet:** before the demo, cache everything once (add the YouTube video ids you plan to show), then start the server in offline mode:

```powershell
..\.venv\Scripts\python scripts\warm_cache.py VIDEO_ID_1 VIDEO_ID_2
$env:FINPROOF_OFFLINE = "1"
..\.venv\Scripts\python -m uvicorn finproof.api:app --port 8000
```

**Decision test:** participants open `/study.html`, the facilitator watches `/results.html`. How to run it at the venue: [eval/README.md](eval/README.md).

**SEBI list:** SEBI's site blocks automated downloads. Save the list pages from a browser and convert them with `scripts\sebi_html_to_csv.py` (instructions at the top of that file).

## Prior work

What FinProof reuses, so the judges know exactly what was built during the event:

- **Look and fonts from our earlier project T.R.U.C.E. AI** (truthshield-ai): the colour values, panel and button styles in `dashboard/truce.css`, and three font files (Inter, Space Grotesk, JetBrains Mono, SIL Open Font License, licences in `dashboard/fonts`). The idea of a browser-extension card also came from T.R.U.C.E. AI.
- **Libraries**, used unchanged: TradingView Lightweight Charts 5.3.0 (Apache-2.0, bundled in `dashboard/vendor`), FastAPI, pandas, NumPy, yfinance, youtube-transcript-api, httpx, and the Anthropic SDK (optional AI answers).
- **Data** from public sources, each dated in its file name: NSE company, symbol-change, Nifty 50 constituent and surveillance lists; a partial copy of SEBI's registered lists; prices via Yahoo Finance.
- **AI assistance:** parts of the code and documents were written with an AI coding assistant (Claude Code); the commits say so.
- [TEAM: add any other code reused from earlier projects, and confirm when coding started.]
