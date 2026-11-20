"""Terminal features: volume radar, UPI and 'educational only' checks, split scale, Claim Auditor,
journal, chart API, and the no-advice rule across every new output and the dashboard's own text."""

import datetime as dt
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import FakePrices, make_df
from finproof import api, auditor, config, extract, journal
from finproof.card import ADVICE_RE, _price_scale, build_card, wording_problems
from finproof.ledger import Ledger
from finproof.pumpdump import market_signals, volume_anomalies

DASHBOARD = Path(__file__).resolve().parents[2] / "dashboard"


# ------------------------------------------------------------------ volume radar

def spike_frame(post_day_volume=10_000.0, after_close=None):
    """60 quiet sessions, a 3-session window before the post with one 40k day, then the post day and after."""
    vols = [10_000.0] * 57 + [12_000.0, 40_000.0, 11_000.0] + [post_day_volume] + [10_000.0] * 40
    closes = [100.0] * 60 + ([after_close] * 41 if after_close else [100.0] * 41)
    return make_df(closes, volumes=vols)


def test_spike_ratio_is_max_of_3_sessions_over_prior_20_average():
    df = spike_frame()
    post = df.index[60].date()
    sig = market_signals("X", post, FakePrices({"X": df}))
    assert sig.spike_ratio == 4.0  # 40,000 / 10,000
    assert sig.spike_date == df.index[58].date().isoformat()
    assert "volume_spike" in sig.flags
    assert sig.last_session_used == df.index[59].date().isoformat()


def test_spike_threshold_is_2_5x():
    vols = [10_000.0] * 57 + [24_000.0, 10_000.0, 10_000.0] + [10_000.0] * 41
    df = make_df([100.0] * 101, volumes=vols)
    sig = market_signals("X", df.index[60].date(), FakePrices({"X": df}))
    assert sig.spike_ratio == 2.4 and "volume_spike" not in sig.flags


def test_thin_trading_uses_20_session_average_traded_value():
    df = spike_frame()
    sig = market_signals("X", df.index[60].date(), FakePrices({"X": df}))
    assert sig.avg_traded_value_20d < 1e7 and "thin_trading" in sig.flags
    big = make_df([2000.0] * 101, volumes=[5_000_000.0] * 101)
    assert "thin_trading" not in market_signals("B", big.index[60].date(), FakePrices({"B": big})).flags


def test_pre_post_signals_never_see_the_post_day_or_later():
    calm = spike_frame()
    wild = spike_frame(post_day_volume=9_000_000.0, after_close=10.0)  # huge reaction on and after the post
    post = calm.index[60].date()
    a = market_signals("X", post, FakePrices({"X": calm}), include_after=False)
    b = market_signals("X", post, FakePrices({"X": wild}), include_after=False)
    for field in ("spike_ratio", "spike_date", "avg_traded_value_20d", "run_up_20d", "last_session_used"):
        assert getattr(a, field) == getattr(b, field), field
    assert b.fall_after is None and "fell_after" not in b.flags


def test_point_in_time_card_ignores_post_day_volume():
    nifty = make_df([100.0] * 101)
    calm, wild = spike_frame(), spike_frame(post_day_volume=9_000_000.0, after_close=10.0)
    post = calm.index[60].date()
    cards = [build_card(text="BUY SBIN", ledger=Ledger(FakePrices({}), tips=[]),
                        prices=FakePrices({"SBIN": f, config.BENCHMARK: nifty}), posted_on=post,
                        posted_on_note="t", point_in_time=True) for f in (calm, wild)]
    assert cards[0]["claims"][0]["market"] == cards[1]["claims"][0]["market"]
    assert cards[0]["warnings"] == cards[1]["warnings"]


def test_daily_volume_anomaly_uses_only_earlier_sessions():
    df = make_df([100.0] * 30, volumes=[10_000.0] * 25 + [30_000.0] + [10_000.0] * 4)
    ratios = volume_anomalies(df)
    assert ratios.iloc[:20].isna().all()      # needs 20 earlier sessions
    assert ratios.iloc[25] == 3.0
    assert ratios.iloc[26] == pytest.approx(10_000 / 11_000)  # the spike is now in its past window


# ------------------------------------------------------------------ UPI and "educational only"

def card_for(text, day=dt.date(2025, 12, 29)):
    stock = make_df([50.0] * 400, volumes=[2_000_000.0] * 400, start="2024-06-03")
    prices = FakePrices({config.BENCHMARK: make_df([100.0] * 400, start="2024-06-03"), "SBIN": stock, "ITC": stock})
    return build_card(text=text, ledger=Ledger(prices, tips=[]), prices=prices, posted_on=day, posted_on_note="t")


def test_personal_upi_is_flagged_with_the_quoted_id():
    card = card_for("Join VIP calls, pay 999 to rahul.trader@ybl. BUY SBIN CMP 50 TGT 60")
    w = next(w for w in card["warnings"] if w["code"] == "personal_upi")
    assert w["evidence"] == ["rahul.trader@ybl"]
    assert "@valid" in w["text"]


def test_valid_handle_is_noted_not_flagged():
    card = card_for("Fees only via xyz.brk@validhdfc. SBIN CMP 50 target 60")
    assert not any(w["code"] == "personal_upi" for w in card["warnings"])
    assert card["payments"]["upi_ids"][0]["validated_format"] is True


def test_emails_and_mentions_are_not_upi_ids():
    assert extract.extract("Mail me at someone@gmail.com. Follow @stockguru").upi_ids == []


def test_masked_phone_upi_is_not_a_10x_promise():
    ex = extract.extract("pay 98xxxxxx01@paytm for calls")
    assert ex.upi_ids and "big_promise" not in ex.pressure


def test_educational_loophole_needs_a_disclaimer_and_price_levels():
    flagged = card_for("For educational purposes only, not SEBI registered. BUY ITC CMP 50 target 60 SL 45")
    w = next(w for w in flagged["warnings"] if w["code"] == "education_loophole")
    assert "not sebi registered" in w["evidence"] and "ITC" in w["text"]
    calm = card_for("For educational purposes only. Today we learn how candlestick charts work.")
    assert not any(w["code"] == "education_loophole" for w in calm["warnings"])


def test_not_sebi_registered_is_not_a_claim_of_registration():
    assert extract.extract("I am not SEBI registered").claims_sebi_registration is False
    assert extract.extract("We are SEBI registered").claims_sebi_registration is True


def test_split_scale():
    assert _price_scale(1930, [2050], 386.0)[0] == 5.0      # pre-split prices
    assert _price_scale(712, [780], 711.6)[0] == 1.0        # same scale
    assert _price_scale(None, [9000], 760.0)[0] is None     # not comparable


# ------------------------------------------------------------------ Claim Auditor

ADVICE_QUESTIONS = ["Should I buy this stock?", "Is it a good time to sell?", "Should I hold ITC?", "What's the target price?",
                    "Will it go up next week?", "Is this a safe stock?", "Bhai kharidu kya?", "Should I invest?"]


@pytest.fixture
def busy_card():
    return card_for("🚀 SURE SHOT 🚀 Join VIP calls, pay to x.y@ybl. For educational purposes only. "
                    "BUY SBIN CMP 50 TGT 60 SL 45. 100% guaranteed, jaldi karo!")


@pytest.mark.parametrize("question", ADVICE_QUESTIONS)
def test_advice_questions_are_refused(question, busy_card):
    a = auditor.answer(question, busy_card)
    assert a["refused"] is True and a["refusal"] == auditor.REFUSAL
    assert a["lines"]  # still points to the facts


@pytest.mark.parametrize("question,intent", [
    ("Why are these warning signs flagged?", "warnings"),
    ("Explain this source's track record vs. Nifty 50", "track"),
    ("Is there an abnormal volume spike?", "volume"),
    ("Is the UPI ID legit?", "concept_upi"),
    ("Is the source SEBI registered?", "sebi"),
])
def test_audit_questions_are_answered_from_the_card(question, intent, busy_card):
    a = auditor.answer(question, busy_card)
    assert a["refused"] is False and a["intent"] == intent
    for line in a["lines"]:
        assert not ADVICE_RE.search(line["text"]), line["text"]


def test_warning_answers_repeat_the_card_exactly(busy_card):
    a = auditor.answer("Why are these warning signs flagged?", busy_card)
    texts = [ln["text"] for ln in a["lines"]]
    assert a["headline"] == f"{len(busy_card['warnings'])} warning signs in this post."
    assert texts == [w["text"] for w in busy_card["warnings"]]
    assert [ln["evidence"] for ln in a["lines"]] == [w.get("evidence", []) for w in busy_card["warnings"]]


def test_volume_answer_uses_the_card_numbers(busy_card):
    m = busy_card["claims"][0]["market"]
    a = auditor.answer("Is there an abnormal volume spike?", busy_card)
    assert f"{m['spike_ratio']:.1f}x" in a["lines"][0]["text"]


def test_auditor_without_a_card():
    a = auditor.answer("Should I buy?", None)
    assert a["refused"] is True and a["refusal"] == auditor.REFUSAL  # refused even before any tip
    b = auditor.answer("Why is this flagged?", None)
    assert b["intent"] == "no_card" and not b["refused"]


def test_point_in_time_card_does_not_reveal_the_outcome():
    card = card_for("BUY SBIN CMP 50 TGT 60")
    card["post"]["point_in_time"] = True
    a = auditor.answer("What happened after this post?", card)
    assert "does not show what happened" in a["lines"][0]["text"]


# ------------------------------------------------------------------ journal

def journal_prices():
    stock = make_df([100.0] * 10 + [90.0] * 290)
    return FakePrices({config.BENCHMARK: make_df([100.0] * 300), "ITC": stock, "SBIN": make_df([100.0] * 10 + [110.0] * 290)})


def test_journal_summary_looks_back_against_the_nifty():
    entries = [
        {"symbol": "ITC", "direction": "up", "posted_on": "2025-01-01", "decision": "skipped", "provenance": "SYNTHETIC"},
        {"symbol": "SBIN", "direction": "up", "posted_on": "2025-01-01", "decision": "research", "provenance": "SYNTHETIC"},
        {"symbol": "ITC", "direction": "up", "posted_on": "2025-01-01", "decision": "bought"},  # not allowed
    ]
    s = journal.summarize(entries, journal_prices())
    assert [r["vs_nifty_in_claimed_direction"] for r in s["rows"]] == [-0.1, 0.1]
    assert s["groups"]["skipped"]["avg_vs_nifty"] == -0.1 and s["groups"]["research"]["avg_vs_nifty"] == 0.1
    assert len(s["problems"]) == 1 and s["provenance"] == "SYNTHETIC"
    assert wording_problems({k: v for k, v in s.items() if k != "rows"}) == []


def test_demo_seed_is_synthetic_and_never_says_bought_or_sold():
    seed = journal.demo_seed()
    assert len(seed) == 4 and all(e["provenance"] == "SYNTHETIC" for e in seed)
    assert all(e["decision"] in journal.DECISIONS for e in seed)
    for label in journal.DECISIONS.values():
        assert not ADVICE_RE.search(label)


# ------------------------------------------------------------------ API

@pytest.fixture
def client(monkeypatch):
    prices = journal_prices()
    prices.frames["ITC"] = make_df([100.0 + i for i in range(300)], volumes=[1000.0] * 250 + [9000.0] + [1000.0] * 49)
    monkeypatch.setattr(api, "PRICES", prices)
    monkeypatch.setattr(api, "LEDGER", Ledger(prices, tips=[]))
    return TestClient(api.app)


def test_chart_api(client):
    d = client.get("/api/chart/ITC").json()
    assert d["provenance"] == "REAL" and d["symbol"] == "ITC"
    assert len(d["candles"]) == 300 and set(d["candles"][0]) == {"time", "open", "high", "low", "close"}
    assert max(v["ratio"] or 0 for v in d["volume"]) == 9.0
    assert d["nifty"] and d["spike_ratio"] == 2.5
    assert client.get("/api/chart/NOPE").status_code == 404
    assert client.get("/api/chart/A%20B").status_code == 400


def test_auditor_and_journal_api(client):
    card = client.post("/api/analyze", json={"text": "BUY ITC now, sure shot", "posted_on": "2025-06-02"}).json()
    a = client.post("/api/auditor", json={"question": "Should I buy this stock?", "card": card}).json()
    assert a["refused"] is True
    assert client.get("/api/auditor/prompts").json()[0] == "Should I buy this?"
    seed = client.get("/api/journal/demo-seed").json()
    assert client.post("/api/journal/summary", json={"entries": seed}).status_code == 200


def test_static_files_are_revalidated(client):
    r = client.get("/study.html")
    assert r.headers.get("cache-control") == "no-cache"
    assert "cache-control" not in client.get("/api/health").headers


# ------------------------------------------------------------------ the dashboard's own wording

# The only places the dashboard may say "buy"/"sell": statements of the no-advice policy itself.
POLICY_LINES = ("never tells you what to buy or sell", "never says what to buy or sell", "asks for a buy, sell or price call",
                "without ever telling them what to buy or sell")  # the challenge's own words, quoted on the Problem Map
STRING_RE = re.compile(r'"((?:[^"\\]|\\.)*)"|`((?:[^`\\]|\\.)*)`')


def ui_strings():
    for path in sorted(DASHBOARD.glob("*.js")):
        in_samples = False
        for line in path.read_text(encoding="utf-8").splitlines():
            if "const SAMPLES" in line:
                in_samples = True
            if in_samples:  # made-up example posts are quoted content, shown as samples
                in_samples = not line.startswith("];")
                continue
            if any(p in line for p in POLICY_LINES) or line.strip().startswith("//"):
                continue
            for m in STRING_RE.finditer(line):
                yield path.name, m.group(1) or m.group(2) or ""
    for path in sorted(DASHBOARD.glob("*.html")):
        text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", path.read_text(encoding="utf-8"), flags=re.S)
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text))
        for policy in POLICY_LINES:  # the page may state the no-advice policy itself
            text = text.replace(policy, " ")
        yield path.name, text


def test_dashboard_text_never_gives_advice():
    bad = [(name, s) for name, s in ui_strings() if ADVICE_RE.search(s)]
    assert bad == []
