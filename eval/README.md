# eval

How we prove FinProof works. Results go here as CSV files plus a short summary.

## 1. Decision test (main evidence)

The challenge asks for a tool that *measurably* improves decisions. This test measures it.

### Design (fixed before collecting any answers)

- **Tips:** 12 real past tips whose 30-day outcome is known: 6 good and 6 bad.
  - A tip is **bad** if, 30 days after it was posted, the stock did worse than the Nifty 50 in the direction the tip claimed; otherwise it is **good**. Labels are computed from NSE prices by the same code as the ledger, never chosen by hand. A tip from a SEBI order may be labelled by hand, with the order as its `label_basis`.
- **Two halves:** the 12 tips are split into sets X and Y, each with 3 good and 3 bad.
- **Each person sees both:** one set with the FinProof card, the other without it.
- **Four groups, assigned in turn:** which set gets the card × whether the card part comes first. This balances tip difficulty and practice effects. Tip order inside each part is shuffled per person.
- **The card shows only the past:** in the test, the card uses only what was known before the tip was posted. It has no "what happened after", no fall-after signal, and a track record counting only tips whose result was already known. The indicator readings on each card (SMA, VWAP, RSI, ATR, key levels) are taken from the last session before the post. Tests check all of this, including that changing every price after the post leaves the card unchanged.
- **Question per tip:** "Would you act on this tip?" (yes or no), then "How sure are you?" (1-5). Time to answer is recorded.
- **People:** at least 20, aiming for 30. No names are collected.

### Success, decided in advance

| | Hypothesis | Counts as met when |
|---|---|---|
| H1 | With the card, people act on fewer bad tips | 95% CI of the within-person difference is entirely below 0 |
| H2 | With the card, people don't lose trust in good tips | Lower end of the 95% CI of the difference is above −10 points |
| Calibration | Confidence matches outcomes better with the card | Brier score of confidence vs outcome (lower is better); fixed 21 Nov 2026, 04:15 IST, before any participant data |

Reported with each: the mean for each condition, the difference, a bootstrap 95% CI over people, and a paired sign-flip permutation p-value. As a check, the first part alone is also compared between people who saw the card first and people who didn't, since that comparison has no carry-over. Everything is recomputed from the answer log.

H2 matters because a tool that makes people distrust every tip would "pass" H1 for the wrong reason.

### Running it

1. Build the real tip set in `decision_test/tips_real.json` (format below), then check it:
   `..\.venv\Scripts\python scripts\check_test_set.py real`
2. Pick the 12 tips by a rule decided **before** looking at their cards, so the set can't be tilted towards tips the card flags. For example: all clear-outcome tips from `data/real/tips_real.csv`, then 6 good and 6 bad drawn at random with a fixed seed.
3. Start the server so phones on the same Wi-Fi can connect, with a facilitator key:
   ```powershell
   $env:FINPROOF_STUDY_KEY = "choose-a-key"
   ..\.venv\Scripts\python -m uvicorn finproof.api:app --host 0.0.0.0 --port 8000
   ```
   Allow Python through Windows Firewall on private networks when asked.
4. Open `http://localhost:8000/results.html` (enter the key). It shows the address participants open on their phones, and the results update live.
5. After the session, download the CSV from the results page. Commit `decision_test/responses/responses_real.jsonl` as evidence: it holds no names.
6. Before real participants arrive, make sure the answer log holds no test sessions. Trying the screens yourself writes to the practice log (`responses_practice.jsonl`); empty it afterwards. It was emptied after the final walkthroughs (20–21 Nov 2026).

### Tip set format (`tips_real.json`)

```json
{
  "practice": false,
  "tips": [
    {
      "tip_id": "R01",
      "platform": "telegram",
      "source_id": "UCxxxxxxxxxxxxxxxxxxxxxx",
      "source_label": "Channel A",
      "posted_on": "2025-03-14",
      "symbol": "SBIN",
      "direction": "up",
      "title": "",
      "text": "The post exactly as it appeared",
      "link": "https://... (kept server-side, never shown to participants)",
      "provenance": "REAL"
    }
  ]
}
```

`platform` is one of telegram, whatsapp, youtube, instagram, x or other. For YouTube, put the video title in `title` and the part of the transcript where the tip is given in `text`. Optional fields: `set` (`X` or `Y`, otherwise assigned automatically) and `label` with `label_basis` (for SEBI cases).

### Practice set

`decision_test/tips_practice.json` holds 12 **made-up posts** on real stocks and dates, built by `backend/scripts/make_practice_test.py`, so the screens can be tried before real tips exist. The writing style of each post was picked at random, independently of its outcome, so **the card is not expected to help on the practice set**. Its answers are git-ignored and are never evidence. Once `tips_real.json` exists, the server uses it automatically.

## Automated checks (287 tests)

| Area | What the tests prove |
|---|---|
| No advice | Every card, Desk Note, auditor answer, indicator explanation and dashboard string is free of buy/sell/hold, target-price and signal wording; live AI replies with such words fall back to the local engine |
| Point in time | Study cards and indicator snapshots never change when prices after the post change |
| Indicator math | SMA 20, EMA 50, rolling VWAP 20D, Bollinger (20, 2), RSI 14 (Wilder), MACD (12, 26, 9), ATR 14 (Wilder) and key levels against hand-worked values, including series too short for each window |
| Desk Note | Distinct, data-accurate notes for a hype + volume-spike post, a personal-UPI post and a calm post; no number in any note that is not in the scan; findings read from a sample post labelled SYNTHETIC |
| Hybrid auditor | Mocked timeout, lost connection, quota and server errors all return the local answer in under a second, then skip the API during a cool-down |
| Hybrid mode and links | YouTube fetched live when online and cached, cache used when the network drops; X and Instagram links detected and tagged; login walls, rate limits and timeouts give the paste-caption prompt, never an error; the suite never touches the real network |
| Media cues | Impersonation, scam-funnel and missing-context flags on the right posts and not on group names or calls that mention risk; every new string free of advice |
| Round 2 | The Signal or Noise label (two separate axes, tags, "not enough history" below 10 calls, the education rule only from 1 July 2026), BSE fallback and the BSE Ltd clash, Price History (exactly 50 Nifty 50 companies, no flags), the real SEBI case computed from prices, the reply card in 3 languages, the Signal Map, NSE surveillance and journal outcomes |

## 2. Extraction accuracy

About 50 videos and messages labelled by hand (stock, direction, target). Report how often extraction gets each field right.

## 3. Pump-and-dump check

Known cases from SEBI orders against random stock-days. Report catches and false alarms for a simple volume-spike rule and for our combined check.

## Where it fails

### Found while building (each one now has a test)

| Input | What went wrong | What we did |
|---|---|---|
| "paisa double **pakka**" | "pakka" (Hinglish for "for sure") matched the listed company Pakka Ltd | Added common Hinglish and Kannada words to an ignore list. Other everyday words may still slip through |
| A song's lyrics: "**Music** video", "**West**" | A capitalised word that starts exactly one company name (Music Broadcast, West Coast Paper) was taken as that stock | A single word now counts only if it is the company's full short name or a known nickname |
| "**Adani** stocks are falling" | Read as Adani Enterprises, though it names a group of several listed companies | Group names (Adani, Tata, Bajaj) are shown as ambiguous and not scored |
| "BUY **TATAMOTORS**" | Symbol no longer exists after the 2025 demerger | Old symbols are mapped with NSE's symbol-change file (TATAMOTORS → TMPV). Returns across a demerger date may still be off if the adjusted price ignores the spin-off |
| "**Don't touch** SBIN, target 100" | Negation without a buy/sell word; the named price made it look like a rise call | Any negation in the sentence now stops us from guessing a direction |
| "Bajaj Finance **target 9000**" | No direction word at all | Direction is worked out from the named price versus the real closing price that day, and the card says so. Wrong if the post quotes an old price |
| SEBI check | Our saved copy has 25 of 2,404 research analysts | "Not found" is not shown as a warning until the copy is complete |
| KOTAKBANK post quoting ₹1,930 (Feb 2025) | Yahoo's price history is split-adjusted (about ₹386 that day), so the post's price levels were off by about 5× | The card compares the post's prices with that day's price; at a 2/3/4/5/10/20× gap it divides them before comparing and says so; at any other big gap it does not compare |
| "pay 98xxxxxx01@paytm" | "98x" inside a masked phone number was read as a "10x"-style promise | The pattern now needs a whole word ("10x", not "98xxx") |
| "I am **not** SEBI registered" | Counted as a post *claiming* SEBI registration | Negated mentions no longer count as a claim |
| ITC, 28 May 2025 | 32× its usual volume in the sessions before a calm post | Kept as a known limit: volume alone can't tell a pump from a large one-off trade, so the card states the fact and never calls it a pump |

### Still open

- Sarcasm ("sure, this will definitely double")
- Hindi or Kannada captions in their own script: our patterns only read English letters
- Long transcripts with no punctuation: direction is read from the 14 words on each side of a stock name
- Sources with fewer than 10 tips show no percentage
- Pump-and-dump thresholds are starting values, not yet tuned on SEBI cases
