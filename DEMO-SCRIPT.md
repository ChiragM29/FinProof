# FinProof: round 2 demo script

Pitch line: **"We never rate stocks. We rate the message, and we keep score on the messenger."**

Before you start: run the server (`..\.venv\Scripts\python -m uvicorn finproof.api:app --port 8000` from `backend`), open http://localhost:8000 and press **▶ Judge Tour**. Every sample is cached, so the tour runs with Wi-Fi off (start the server with `$env:FINPROOF_OFFLINE = "1"` if the venue Wi-Fi is bad).

## 30-second opening

> The booklet says retail investors "act on information whose quality they cannot judge", that "a few finfluencers are registered with SEBI; most are not", that "some tips are honest but wrong; others are part of pump-and-dump schemes", and that "nobody tracks most tips over time". The challenge is to "build a tool that measurably improves how a retail investor makes decisions, without ever telling them what to buy or sell."
>
> FinProof never rates the stock. It judges the message and the person who sent it, keeps score on that person over time, and we measure whether people decide better with it.

## The 3-minute walk-through (the Judge Tour, 7 steps)

1. **Problem Map (20 s).** Every line of the brief, the feature that answers it, and where it is on screen. "Each row has a Show button."
2. **A WhatsApp VIP tip, judged (40 s).** The Signal or Noise label comes first. Two separate questions:
   - *Were they right before?* For this sender: not enough history.
   - *Are they playing fair?* SEBI registration not found (dated snapshot), no conflict disclosure, a paid group, payment to a personal UPI ID instead of a SEBI-validated @valid handle, unusual volume before the post (32.1× its 20-day average), liquidity and NSE surveillance status.
   - Every line has a REAL or SYNTHETIC tag and a "why" that cites the rule. Show the **Reply card** button: one tap copies a facts-only reply for the WhatsApp group in English, Kannada or Hindi.
3. **A real SEBI case on BSE (35 s).** Sadhna Broadcast is listed only on BSE (scrip 540821, now Crystal Business System). SEBI's interim order of 2 March 2023 says misleading YouTube videos promoted it in the second half of July 2022. On real BSE prices: volume up to 12.4× its average and the price up 149% within the promotion window, then back down. "An NSE-only tool cannot see this stock at all."
4. **Track record and Signal Map (25 s).** Every source is scored against the Nifty 50, 30 days after each call. The Signal Map puts "right before" and "playing fair" on separate axes, because the brief separates honest-but-wrong from pump-and-dump. Demo Channel A: 7 of 14 calls beat the Nifty 50 (synthetic sources, real prices). Under 10 calls: "not enough history".
5. **Decision Study (25 s).** Each person sees 6 tips with the label and 6 without (4 groups rotate which half and which order). Metrics were fixed before any data: bad tips acted on, good tips still trusted, and calibration of confidence (Brier score). Results update live on /results.html with N per group.
6. **Failure Cases (15 s).** Where FinProof went wrong on real data and what changed: "pakka" read as a company, a split-adjusted price off by 5×, ITC's 32× volume from a large one-off trade.
7. **The refusal (20 s).** Ask "Should I buy this?": the Claim Auditor refuses and shows the facts instead. An automated test scans every card, label, Desk Note, reply card, auditor answer and dashboard string for buy/sell/hold, target-price and signal words.

## Six judge questions

**How do you measure improvement?**
A counterbalanced decision study: each participant decides on 12 past tips with known 30-day outcomes, 6 with the FinProof label and 6 without, so each person is compared with themselves. We fixed three metrics before any data: the share of bad tips people would act on (should fall), the share of good tips still trusted (should not drop by more than 10 points), and how well confidence matches outcomes (Brier score). We report bootstrap 95% confidence intervals and a paired permutation p-value. [Fill in today's N and results before 12:00.]

**Isn't this advice?**
No. FinProof never says buy, sell or hold, never gives a target and never calls a stock good or safe. It reports facts about the message and the sender: registration, pressure tactics, payment route, the sender's past record, and what prices did. Questions asking for a call get a refusal card, and an automated test fails the build if any advice wording appears anywhere.

**What's real and what's synthetic?**
Every line carries a tag. REAL: NSE and BSE prices, the NSE company and Nifty 50 lists, SEBI's full analyst and adviser lists (3,487 names, saved 21 Nov 2026), NSE's surveillance lists, and the Sadhna Broadcast case. SYNTHETIC: the demo channels and their tips (scored on real prices), the sample posts, the practice tip set for the study, and the demo journal.

**How do you treat honest-but-wrong sources?**
As a separate axis. "Were they right before?" is the track record; "Are they playing fair?" is about pressure, payment and pump patterns. A source can be honest but wrong (fair, low hit rate) or right but unfair. Merging them into one trust score would hide exactly the difference the brief describes.

**What fails?**
See the Failure Cases tab. Known limits: volume alone cannot tell a pump from a large one-off trade (so FinProof says "partly seen"); a channel name rarely matches a legal name, so a name that matches nobody on SEBI's list is shown as a fact, not a warning; sarcasm and non-Latin scripts are not read; the practice study set is made up, so it is not evidence.

**Why is BSE needed?**
Many pump-and-dump stocks are small companies listed only on BSE. Sadhna Broadcast, the subject of a SEBI order about YouTube promotion, has no NSE listing, so a tool that reads only NSE prices would show nothing. FinProof reads NSE first and falls back to BSE, and shows which exchange every number came from.
