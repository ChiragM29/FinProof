# dashboard

Plain HTML, CSS and JavaScript served by the backend. No build step, no CDNs, no web fonts: it works offline.

| Page | For | What it does |
|---|---|---|
| `index.html` + `cc.js` + `cc.css` | everyone | **FinProof workspace.** Scanner bar with a Samples ▾ menu, the chart beside the side panel, then a metadata caption, the four key signals and the Credibility X-Ray. Paste a post or a YouTube / Instagram / X link and press Scan Tip: date, source and ticker are detected automatically (pills with an optional Edit), a 4-step scan runs, then the KPI cards, chart (tip pin, volume spike, Nifty overlay, one-click indicators: SMA 20, EMA 50, VWAP 20D, Bollinger, Key Levels, RSI and MACD panes, ATR swing in the legend), Credibility X-Ray, Veteran's Desk Note (Mentor / Raw toggle) and Claim Auditor update. Also: Sources, Decision Study and Failure Cases views, the Noise Journal (1-click Demo Investor) and the 6-step Judge Tour |
| `study.html` | participants | The decision test, one screen at a time; works on phones; keyboard: Y/N then 1/2/3, Enter |
| `results.html` | facilitator | Live results with confidence intervals, per-tip table, CSV download |

- `card-view.js` draws cards for all pages. `glass.css` gives the study and results pages the same dark theme without changing their structure.
- `vendor/lightweight-charts-5.3.0/` is TradingView Lightweight Charts™, copied unchanged from npm with its Apache-2.0 license; the attribution logo stays on. FinProof is not affiliated with TradingView.
- Animations respect `prefers-reduced-motion`.
- Everything is built with `textContent`, never `innerHTML`, because posts are untrusted text.
- The Demo Investor journal has no password and keeps its data only in this browser (`localStorage`).
- Every data module carries a REAL or SYNTHETIC badge; the sample posts are SYNTHETIC (one "Demo samples · SYNTHETIC" label for the sample buttons, and SYNTHETIC on every finding read from a sample post).
- Indicator values come from the backend (`finproof/indicators.py`), computed from the cached prices; the page only draws them.
