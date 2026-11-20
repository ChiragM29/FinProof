# data

The Finance track rule: say clearly which data is real and which is synthetic. We keep them in separate folders, and every tip has a `provenance` column set to `REAL` or `SYNTHETIC`.

## real/

| File | What it is | Source |
|---|---|---|
| `nse_equity_list_2026-11-20.csv` | Every NSE-listed company: symbol, name, series | archives.nseindia.com, saved 2026-11-20 |
| `nse_symbol_changes_2026-11-20.csv` | Old → new NSE symbols (TATAMOTORS → TMPV, ZOMATO → ETERNAL) | archives.nseindia.com, saved 2026-11-20 |
| `sebi_registry_2026-11-20.csv` + `.json` | Registered research analysts, with how much of SEBI's list is covered | sebi.gov.in list pages. **Only page 1 so far: 25 of 2,404.** |
| `tips_real.csv` | Public tips: source, stock, direction, date posted, prices named, link | Collected by hand from YouTube and Telegram. **Empty, to fill.** |
| `sebi_cases.csv` | Pump-and-dump cases named in SEBI orders, with stocks and dates | SEBI orders. **To add.** |

NSE prices are fetched on demand and cached in `data/cache/`, which is not committed.

## synthetic/

| File | What it is |
|---|---|
| `synthetic_tips.csv` | 34 made-up tips from three demo channels, built by `backend/scripts/make_synthetic_tips.py` with a fixed seed. Their outcomes are computed from real NSE prices, but the tips themselves are invented. |

Never report a synthetic tip as evidence.

## Adding real tips

One row per tip in `tips_real.csv`:

```
tip_id,source_id,source_label,symbol,direction,posted_on,expected_price,stop_loss,link,provenance,note
yt-0001,UCxxxxxxxxxxxxxxxxxxxxxx,Channel A,SBIN,up,2025-03-14,900,760,https://youtu.be/...,REAL,
```

- `source_id`: the YouTube channel id (starts with `UC`) or the Telegram group handle, so the extension can match it.
- `source_label`: **Channel A, B, C**, never the real name, unless the source is named in a SEBI order.
- `direction`: `up` or `down`, as the tip claimed.

## Rules

- A source with fewer than 10 scored tips shows "not enough history", not a percentage.
