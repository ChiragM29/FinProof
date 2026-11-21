"""Zero-manual-entry scanning: date, time and source are worked out from the post itself."""

import datetime as dt
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import FakePrices, make_df
from finproof import api, config, youtube
from finproof.ledger import Ledger, Tip
from finproof.meta import UNATTRIBUTED, extract, extract_metadata

TODAY = dt.date(2026, 11, 20)
DASHBOARD = Path(__file__).resolve().parents[2] / "dashboard"


def meta(text, known=None):
    return extract(text, known_sources=known, today=TODAY)


# ------------------------------------------------------------------ chat headers

def test_whatsapp_iphone_header():
    m = meta("[14/03/2025, 9:42 am] Stock Guru VIP: Join our VIP calls, pay to x@ybl\nBUY ITC TGT 460")
    assert (m.posted_on, m.posted_time, m.source) == (dt.date(2025, 3, 14), "09:42", "Stock Guru VIP")
    assert m.date_how == "WhatsApp message header" and m.source_how == "WhatsApp sender name"
    assert "Stock Guru" not in m.body and m.body.startswith("Join our VIP calls")


def test_whatsapp_android_header_with_two_digit_year_and_pm():
    m = meta("14/03/25, 2:15 PM - Rakesh Bhai: SBIN abhi le lo")
    assert (m.posted_on, m.posted_time, m.source) == (dt.date(2025, 3, 14), "14:15", "Rakesh Bhai")


def test_day_month_order_is_indian():
    assert meta("05/03/2025, 10:00 - A: hi").posted_on == dt.date(2025, 3, 5)  # 5 March, not 3 May


def test_telegram_forward_line():
    m = meta("Forwarded from Fin Hype Calls\nMarch 24, 2025 9:42 AM\nBUY SBIN TGT 900")
    assert (m.posted_on, m.posted_time, m.source) == (dt.date(2025, 3, 24), "09:42", "Fin Hype Calls")
    assert "Forwarded" not in m.body


def test_telegram_desktop_copy_header():
    m = meta("Fin Hype Calls, [24.03.2025 09:42]\nBUY SBIN TGT 900")
    assert (m.posted_on, m.posted_time, m.source, m.date_how) == (dt.date(2025, 3, 24), "09:42", "Fin Hype Calls", "Telegram message header")


# ------------------------------------------------------------------ inline dates and handles

@pytest.mark.parametrize("text,expected", [
    ("Posted 24 Mar 2025: SBIN tgt 900", dt.date(2025, 3, 24)),
    ("24-03-2025 SBIN tgt 900", dt.date(2025, 3, 24)),
    ("24/03/25 SBIN tgt 900", dt.date(2025, 3, 24)),
    ("2025-03-24 SBIN tgt 900", dt.date(2025, 3, 24)),
    ("March 24, 2025 SBIN tgt 900", dt.date(2025, 3, 24)),
    ("24th March 2025 SBIN tgt 900", dt.date(2025, 3, 24)),
])
def test_inline_dates(text, expected):
    m = meta(text)
    assert m.posted_on == expected and m.date_how == "date written in the post"


def test_relative_words():
    assert meta("yesterday's call: SBIN").posted_on == TODAY - dt.timedelta(days=1)
    assert meta("Today SBIN looks strong").posted_on == TODAY


def test_future_and_impossible_dates_are_ignored():
    assert meta("SBIN results on 30 Jun 2027").posted_on is None
    assert meta("SBIN 31/02/2025").posted_on is None


def test_prices_are_not_dates():
    assert meta("BUY SBIN CMP 780 TGT 820/850 SL 760").posted_on is None


def test_handle_and_known_source():
    assert meta("@MarketGyaanDaily · KOTAKBANK target 2050").source == "@MarketGyaanDaily"
    assert meta("pay to stockguru.calls@ybl").source is None  # a UPI ID is not a handle
    m = meta("ICICIBANK tgt 1500 (Demo Channel A (synthetic))", known=["Demo Channel A (synthetic)"])
    assert m.source == "Demo Channel A (synthetic)" and m.source_how == "matched a source in the FinProof ledger"


def test_nothing_found():
    m = meta("BUY INFY")
    assert m.posted_on is None and m.source is None and m.body == "BUY INFY"


def test_brief_name_alias():
    assert extract_metadata is extract


# ------------------------------------------------------------------ the scan API

@pytest.fixture
def client(monkeypatch, tmp_path):
    nifty = make_df([100.0] * 400, start="2024-06-03")
    prices = FakePrices({config.BENCHMARK: nifty, "ITC": make_df([100.0] * 400, start="2024-06-03"),
                         "TMPV": make_df([100.0] * 400, start="2024-06-03")})
    tips = [Tip(f"t{i}", "demo_a", "Demo Channel A (synthetic)", "ITC", "up", dt.date(2024, 7, 1) + dt.timedelta(days=7 * i),
                provenance="SYNTHETIC") for i in range(12)]
    monkeypatch.setattr(api, "PRICES", prices)
    monkeypatch.setattr(api, "LEDGER", Ledger(prices, tips=tips))
    monkeypatch.setattr(youtube, "YT_CACHE", tmp_path)
    return TestClient(api.app), nifty


def test_scan_auto_detects_everything(client):
    c, _ = client
    d = c.post("/api/analyze", json={"text": "[02/06/2025, 9:42 am] Stock Guru VIP: BUY ITC CMP 100 TGT 110"}).json()
    det = d["detected"]
    assert (det["posted_on"], det["posted_time"], det["source"], det["tickers"]) == ("2025-06-02", "09:42", "Stock Guru VIP", ["ITC"])
    assert det["date_origin"] == "extracted" and det["source_origin"] == "extracted"
    assert d["post"]["posted_on"] == "2025-06-02" and "WhatsApp" in d["post"]["posted_on_note"]


def test_scan_fallbacks_are_tagged(client):
    c, nifty = client
    det = c.post("/api/analyze", json={"text": "BUY TATAMOTORS now"}).json()["detected"]
    assert det["posted_on"] == nifty.index[-1].date().isoformat()   # latest NSE session in the data
    assert det["date_origin"] == "fallback" and "latest NSE session" in det["date_how"]
    assert det["source"] == UNATTRIBUTED and det["source_origin"] == "fallback"
    assert det["renamed"] == [{"from": "TATAMOTORS", "to": "TMPV"}]


def test_user_override_wins(client):
    c, _ = client
    det = c.post("/api/analyze", json={"text": "[02/06/2025, 9:42 am] X: BUY ITC", "posted_on": "2025-01-10",
                                       "source": "My Group"}).json()["detected"]
    assert (det["posted_on"], det["date_origin"], det["source"], det["source_origin"]) == ("2025-01-10", "user", "My Group", "user")


def test_known_source_loads_its_track_record(client):
    c, _ = client
    d = c.post("/api/analyze", json={"text": "Forwarded from Demo Channel A (synthetic)\n4 Aug 2025\nITC looking strong, tgt 110"}).json()
    assert d["detected"]["source"] == "Demo Channel A (synthetic)"
    assert d["track_record"]["status"] == "ok" and d["track_record"]["provenance"] == "SYNTHETIC"


def test_youtube_publish_time_and_channel(client, tmp_path):
    c, _ = client
    (tmp_path / "abcdefghijk.json").write_text(json.dumps({
        "video_id": "abcdefghijk", "title": "ITC breakout?", "channel": "Market Guru", "channel_id": None,
        "published_on": "2025-06-01", "published_at": "2025-06-01T22:30:00-07:00", "description": "",
        "transcript": "BUY ITC now, target 110", "transcript_language": "en", "transcript_error": None}), encoding="utf-8")
    det = c.post("/api/analyze", json={"url": "https://youtu.be/abcdefghijk"}).json()["detected"]
    assert (det["posted_on"], det["posted_time"]) == ("2025-06-02", "11:00")   # 22:30 PDT = 11:00 IST next day
    assert det["source"] == "Market Guru" and det["date_origin"] == "extracted" and det["tickers"] == ["ITC"]


def test_terminal_redirects_to_the_command_center(client):
    c, _ = client
    for path in ("/terminal", "/terminal.html"):
        r = c.get(path, follow_redirects=False)
        assert r.status_code == 307 and r.headers["location"] == "/"


# ------------------------------------------------------------------ the Command Center page

def page():
    return (DASHBOARD / "index.html").read_text(encoding="utf-8")


def test_scanner_has_no_manual_date_or_source_boxes():
    html = page()
    scanner = html[html.index('id="scan-form"'):html.index('id="edit-pop"')]
    assert 'type="date"' not in scanner and "Source (optional)" not in scanner
    assert html.count('type="date"') == 1  # only inside the optional Edit popover


def test_scan_steps_exist_and_every_feature_is_reachable_without_a_tour():
    html = page()
    for step in ("Auto-detecting metadata", "SEBI &amp; UPI audit", "NSE OHLCV &amp; volume spike", "Track record check"):
        assert step in html
    js = (DASHBOARD / "cc.js").read_text(encoding="utf-8")
    assert "Judge Tour" not in html + js and 'id="view-problem"' not in html and "loadProblem" not in js
    # The header names every section; the Auditor and Journal links scroll to their cards.
    for name in ("Workspace", "Sources · Signal Map", "Noise Journal", "Claim Auditor", "Decision Study", "Failure Cases"):
        assert f">{name}</button>" in html
    assert 'data-jump="card-auditor"' in html and 'id="card-auditor"' in html
    assert 'data-jump="card-journal"' in html and 'id="card-journal"' in html
    # Try FinProof: six one-click cards (YouTube, Instagram, WhatsApp, SEBI case, Price History, refusal).
    try_block = js[js.index("const TRY = ["):js.index("function renderTry")]
    assert try_block.count("() =>") == 6 and 'id="try-grid"' in html


def test_pages_load_nothing_from_the_internet():
    for path in DASHBOARD.glob("*.html"):
        assert not re.search(r'<(?:script|link)[^>]+(?:src|href)="(?:https?:)?//', path.read_text(encoding="utf-8")), path.name
    for path in DASHBOARD.glob("*.css"):
        assert "@import" not in path.read_text(encoding="utf-8") and "url(http" not in path.read_text(encoding="utf-8")


def test_study_pages_keep_their_structure_with_the_new_theme():
    for name in ("study.html", "results.html"):
        html = (DASHBOARD / name).read_text(encoding="utf-8")
        assert 'href="glass.css"' in html and 'href="style.css"' in html
    assert 'id="study"' in (DASHBOARD / "study.html").read_text(encoding="utf-8")
