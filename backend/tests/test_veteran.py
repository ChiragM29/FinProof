"""Veteran's Desk Note: distinct, data-accurate mentor guidance; never advice; no invented numbers."""

import datetime as dt
import json
import re

import pytest
from fastapi.testclient import TestClient

from conftest import FakePrices, make_df
from finproof import api, auditor, config, study
from finproof.card import ADVICE_RE, build_card
from finproof.ledger import Ledger, Tip, load_tips
from finproof.market import YahooPrices
from finproof.veteran import DISCLAIMER, EXTRA_RE, FLAG_LABELS, build_veteran_brief, veteran_problems

POST = dt.date(2025, 6, 2)
START = "2024-06-03"
N = 400
# Constants the templates themselves use: "1 October 2025", "3 sessions", "20-day", "24 hours", "30 days", "Nifty 50".
TEMPLATE_NUMBERS = {"1", "3", "20", "24", "30", "50", "2025"}
NUM = re.compile(r"\d+(?:[.,]\d+)*")


def post_index():
    return list(make_df([1.0] * N, start=START).index.date).index(POST)


def frame(before, after, volume=2_000_000.0, spike=None):
    """Close `before` up to and including the post day, `after` from the next session; optional volume spike
    on the two sessions just before the post."""
    i = post_index()
    closes = [before] * (i + 1) + [after] * (N - i - 1)
    volumes = [volume] * N
    if spike:
        volumes[i - 2] = volumes[i - 1] = spike
    return make_df(closes, volumes=volumes, start=START)


def card_for(text, frames, ledger_tips=None, source_key=None):
    prices = FakePrices({config.BENCHMARK: make_df([100.0] * N, start=START), **frames})
    return build_card(text=text, ledger=Ledger(prices, tips=ledger_tips or []), prices=prices, posted_on=POST,
                      posted_on_note="test", source_key=source_key)


@pytest.fixture
def hype():
    card = card_for("🚀 SURE SHOT 🚀 BUY SBIN CMP 50 TGT 80. 100% guaranteed profit, today only! Join our VIP group",
                    {"SBIN": frame(50.0, 40.0, spike=20_000_000.0)})
    return card, build_veteran_brief(card)


@pytest.fixture
def upi():
    card = card_for("For educational purposes only. Pay ₹999 to rahul.k@ybl for our premium course. "
                    "BUY ITC CMP 50 TGT 60", {"ITC": frame(50.0, 55.0)})
    return card, build_veteran_brief(card)


@pytest.fixture
def calm():
    card = card_for("SBIN has posted its quarterly results on the NSE website. The full filing is worth reading.",
                    {"SBIN": frame(50.0, 50.0)})
    return card, build_veteran_brief(card)


def codes(brief, part):
    return [x["code"] for x in brief[part]]


def pct(x):
    v = round(x * 100, 1)
    return f"{v:+.1f}%" if v else "0.0%"


# ---------------------------------------------------------------- 1. distinct, data-accurate profiles
def test_hype_and_volume_spike_profile(hype):
    card, brief = hype
    wrong = codes(brief, "wrong")
    assert {"guarantee", "urgency", "volume_spike", "claim_failed"} <= set(wrong)
    m = card["claims"][0]["market"]
    spike = next(x for x in brief["wrong"] if x["code"] == "volume_spike")
    assert f"({m['spike_ratio']:.1f}× the 20-day average)" in spike["title"] and m["spike_date"] in spike["text"]
    after = card["claims"][0]["after_post"]["horizons"]["30"]
    failed = next(x for x in brief["wrong"] if x["code"] == "claim_failed")
    assert pct(after["stock_return"]) in failed["text"] and "-20.0%" in failed["text"]
    assert "downside" in codes(brief, "right") and "primary" not in codes(brief, "right")
    assert brief["intro"].startswith(f"This message uses {len(card['warnings'])} classic pressure signals")
    assert brief["balanced"] is False


def test_personal_upi_trap_profile(upi):
    card, brief = upi
    wrong = codes(brief, "wrong")
    assert "personal_upi" in wrong and "volume_spike" not in wrong and "claim_failed" not in wrong
    item = next(x for x in brief["wrong"] if x["code"] == "personal_upi")
    assert "@valid" in item["text"] and "1 October 2025" in item["text"]
    bench = next(x for x in brief["right"] if x["code"] == "benchmark")
    after = card["claims"][0]["after_post"]["horizons"]["30"]
    assert pct(after["stock_return"]) in bench["text"] and "+10.0%" in bench["text"]


def test_calm_post_gets_an_honest_balanced_brief(calm):
    card, brief = calm
    assert card["warnings"] == [] and brief["wrong"] == [] and brief["balanced"] is True
    assert brief["intro"].startswith("This post is calm")
    assert "calm tone is not the same as a correct claim" in brief["intro"]  # balance, not reassurance
    assert codes(brief, "right") == ["benchmark", "record", "primary"]


def test_profiles_are_distinct(hype, upi, calm):
    briefs = [b for _, b in (hype, upi, calm)]
    assert len({b["intro"] for b in briefs}) == 3
    assert len({tuple(codes(b, "wrong")) for b in briefs}) == 3
    assert len({tuple(x["text"] for x in b["right"]) for b in briefs}) == 3


def test_flags_quote_the_post_and_raw_view_carries_every_flag(hype):
    card, brief = hype
    by_code = {x["code"]: x for x in brief["wrong"]}
    for w in card["warnings"]:
        assert by_code[w["code"]]["evidence"] == w.get("evidence", [])
        assert any(r["code"] == w["code"] and r.get("flag") for r in brief["raw"])
    assert all(r["provenance"] in ("REAL", "SYNTHETIC") for r in brief["raw"])


def test_weak_record_and_missing_source_are_explained():
    falling = make_df([200.0 - i * 0.3 for i in range(N)], volumes=[2_000_000.0] * N, start=START)
    tips = [Tip(f"t{i}", "demo", "Demo Source", "SBIN", "up", dt.date(2024, 9, 2) + dt.timedelta(days=7 * i),
                provenance="SYNTHETIC") for i in range(12)]
    card = card_for("SBIN breakout, TGT 220", {"SBIN": falling}, ledger_tips=tips, source_key="demo")
    card["detected"] = {"posted_on": POST.isoformat(), "date_origin": "user", "date_how": "test",
                        "source": "Unattributed Forward", "source_origin": "fallback"}
    brief = build_veteran_brief(card)
    tr = card["track_record"]
    weak = next(x for x in brief["wrong"] if x["code"] == "weak_record")
    assert f"{tr['worked']} of {tr['scored']} past tips" in weak["title"]
    assert "no_source" in codes(brief, "wrong")
    record = next(x for x in brief["right"] if x["code"] == "record")
    assert f"{tr['worked']} of {tr['scored']} past tips" in record["text"]


def test_point_in_time_card_does_not_pretend_to_know_the_outcome():
    prices = FakePrices({config.BENCHMARK: make_df([100.0] * N, start=START), "SBIN": frame(50.0, 40.0)})
    card = build_card(text="BUY SBIN TGT 80", ledger=Ledger(prices, tips=[]), prices=prices, posted_on=POST,
                      posted_on_note="t", point_in_time=True)
    brief = build_veteran_brief(card)
    assert "claim_failed" not in codes(brief, "wrong")
    assert "-20.0%" not in json.dumps(brief, ensure_ascii=False)


def test_sample_post_findings_are_labelled_synthetic():
    """Regression: on a made-up demo post, everything read from the post is SYNTHETIC, never REAL;
    market data keeps its REAL label."""
    text = "Join VIP calls, pay ₹999 to rahul.k@ybl. 100% guaranteed! BUY SBIN CMP 50 TGT 80"
    frames = {"SBIN": frame(50.0, 40.0, spike=20_000_000.0)}
    prices = FakePrices({config.BENCHMARK: make_df([100.0] * N, start=START), **frames})
    for prov in ("SYNTHETIC", "REAL"):
        card = build_card(text=text, ledger=Ledger(prices, tips=[]), prices=prices, posted_on=POST, posted_on_note="t",
                          post_provenance=prov)
        card["detected"] = {"posted_on": POST.isoformat(), "date_origin": "extracted", "date_how": "t",
                            "source": "VIP", "source_origin": "extracted"}
        rows = {r["code"]: r for r in build_veteran_brief(card)["raw"]}
        for code in ("sebi", "paid_group", "personal_upi", "guarantee", "detected_date", "detected_source"):
            assert rows[code]["provenance"] == prov, code
        for code in ("spike_ratio", "traded_value", "after_30", "volume_spike", "tech_rsi14"):
            assert rows[code]["provenance"] == "REAL", code


def test_analyze_marks_sample_posts_synthetic(monkeypatch):
    stock = frame(50.0, 40.0)
    prices = FakePrices({config.BENCHMARK: make_df([100.0] * N, start=START), "ITC": stock})
    monkeypatch.setattr(api, "PRICES", prices)
    monkeypatch.setattr(api, "LEDGER", Ledger(prices, tips=[]))
    client = TestClient(api.app)
    body = {"text": "Join our VIP calls, pay to x.y@ybl. BUY ITC CMP 50 TGT 60", "posted_on": POST.isoformat()}
    sample = client.post("/api/analyze", json={**body, "sample": True}).json()
    pasted = client.post("/api/analyze", json=body).json()
    assert sample["post"]["provenance"] == "SYNTHETIC" and pasted["post"]["provenance"] == "REAL"
    flag = lambda card: next(r for r in card["veteran"]["raw"] if r["code"] == "personal_upi")  # noqa: E731
    assert flag(sample)["provenance"] == "SYNTHETIC" and flag(pasted)["provenance"] == "REAL"


def test_raw_view_uses_readable_flag_names(hype):
    card, brief = hype
    flags = [r for r in brief["raw"] if r.get("flag")]
    assert flags and all(r["label"] == FLAG_LABELS[r["code"]] for r in flags)
    assert all("_" not in r["label"] for r in brief["raw"])
    assert FLAG_LABELS["paid_group"] == "Paid VIP group" and FLAG_LABELS["personal_upi"] == "Personal UPI handle"
    assert FLAG_LABELS["volume_spike"] == "Pre-post volume spike"
    assert FLAG_LABELS["education_loophole"] == '"Educational only" loophole'


def test_chart_context_is_point_in_time_and_neutral(hype):
    card, brief = hype
    ctx = brief["context"]
    tech = card["claims"][0]["technicals"]
    assert ctx and ctx["as_of"] == tech["as_of"] < POST.isoformat()
    assert {f["code"] for f in ctx["facts"]} >= {"rsi14", "atr14", "sma20", "vwap20"}
    assert any("Typical daily swing (ATR 14): ±" in f["text"] for f in ctx["facts"])


# ---------------------------------------------------------------- 2. the no-advice guardrail
def test_guard_catches_advice_in_mentor_wording_but_not_quotes(hype, monkeypatch):
    _, brief = hype
    assert veteran_problems(brief) == []
    bad = {**brief, "right": brief["right"] + [{"code": "x", "title": "Good stock", "text": "You should buy it now."}]}
    problems = veteran_problems(bad)
    assert any(p.startswith("'buy'") for p in problems) and any("Good stock" in p for p in problems)
    quoted = {**brief, "wrong": [{"code": "q", "title": "t", "text": "x", "evidence": ["BUY now, sure to double"]}]}
    assert veteran_problems(quoted) == []
    monkeypatch.setattr("finproof.veteran.VOICE", "Time to invest.")
    with pytest.raises(ValueError):
        build_veteran_brief(hype[0])


def js_samples():
    js = (config.ROOT / "dashboard" / "cc.js").read_text(encoding="utf-8")
    block = js[js.index("const SAMPLES"):js.index("];", js.index("const SAMPLES"))]
    return [json.loads(s) for s in re.findall(r'text: ("(?:[^"\\]|\\.)*")', block)]


def real_prices():
    prices = YahooPrices(offline=True)
    if prices.history(config.BENCHMARK).empty:
        pytest.skip("no cached NSE prices")
    return prices


def every_demo_card(prices):
    """Cards for every demo post FinProof ships: the workspace samples, all demo-channel tips and the practice
    posts of the decision study (both full and point-in-time), on cached real NSE prices."""
    ledger = Ledger(prices)
    cards = []
    for text in js_samples():
        cards.append(build_card(text=text, ledger=ledger, prices=prices, posted_on=dt.date(2025, 6, 2),
                                posted_on_note="test"))
    for tip in load_tips():
        text = f"{tip.symbol} {'breakout, target higher' if tip.direction == 'up' else 'breakdown, more downside'}"
        cards.append(build_card(text=text, ledger=ledger, prices=prices, posted_on=tip.posted_on,
                                posted_on_note="test", source_key=tip.source_id))
    test_set = study.load_test_set(prices, "practice")
    for tip in test_set.tips:
        for pit in (False, True):
            cards.append(build_card(text=tip.text, ledger=ledger, prices=prices, posted_on=tip.posted_on,
                                    posted_on_note="test", source_key=tip.source_id or None, point_in_time=pit))
    return cards


@pytest.fixture(scope="module")
def demo_cards():
    return every_demo_card(real_prices())


def test_every_demo_brief_passes_the_no_advice_guard(demo_cards):
    assert len(demo_cards) >= 5 + 30 + 2 * 12
    for card in demo_cards:
        brief = build_veteran_brief(card)
        assert veteran_problems(brief) == []
        assert brief["disclaimer"] == DISCLAIMER and 2 <= len(brief["right"]) <= 3
        for row in brief["raw"]:  # the raw view states facts; it must not slip into advice either
            assert not ADVICE_RE.search(row["label"]) and not EXTRA_RE.search(row["label"])
    assert len({json.dumps(build_veteran_brief(c)["wrong"]) for c in demo_cards}) > 5  # not one canned answer


def test_every_auditor_answer_carries_a_clean_mentor_line(demo_cards):
    for card in demo_cards[:5]:
        for q in auditor.QUICK_PROMPTS + ["What happened after?", "Is the source SEBI registered?", "Which stock?"]:
            mentor = auditor.answer(q, card)["mentor"]
            assert mentor and not ADVICE_RE.search(mentor) and not EXTRA_RE.search(mentor)
    assert auditor.answer("Should I buy?", None)["mentor"]


def test_analyze_api_returns_the_desk_note(monkeypatch):
    prices = real_prices()
    monkeypatch.setattr(api, "PRICES", prices)
    monkeypatch.setattr(api, "LEDGER", Ledger(prices))
    client = TestClient(api.app)
    for text in js_samples():
        card = client.post("/api/analyze", json={"text": text}).json()
        brief = card["veteran"]
        assert veteran_problems(brief) == [] and brief["disclaimer"] == DISCLAIMER
        assert number_problems(brief, {k: v for k, v in card.items() if k != "veteran"}) == []


# ---------------------------------------------------------------- 3. no invented numbers
def card_numbers(value, out=None):
    """Every number in the scan results, in each way the brief may print it."""
    out = set() if out is None else out
    if isinstance(value, dict):
        for v in value.values():
            card_numbers(v, out)
    elif isinstance(value, list):
        out.add(str(len(value)))
        for v in value:
            card_numbers(v, out)
    elif isinstance(value, bool) or value is None:
        pass
    elif isinstance(value, (int, float)):
        v = float(value)
        out |= {str(abs(int(v))) if v == int(v) else f"{abs(v):.1f}", f"{abs(v):.1f}", f"{abs(v):.2f}", f"{abs(v):.3f}",
                f"{abs(round(v * 100, 1)):.1f}", f"{abs(v) / 1e7:.2f}"}
    elif isinstance(value, str):
        out |= {t.replace(",", "") for t in NUM.findall(value)}
    return out


def brief_numbers(brief):
    texts = [brief["intro"]] + [x[k] for part in ("wrong", "right") for x in brief[part] for k in ("title", "text")]
    texts += [r[k] for r in brief["raw"] for k in ("label", "value")]
    if brief.get("context"):
        texts += [f["text"] for f in brief["context"]["facts"]]
    return {t.replace(",", "") for text in texts for t in NUM.findall(text)}


def number_problems(brief, card):
    return sorted(brief_numbers(brief) - card_numbers(card) - TEMPLATE_NUMBERS)


def test_profile_briefs_use_only_numbers_from_the_scan(hype, upi, calm):
    for card, brief in (hype, upi, calm):
        assert number_problems(brief, card) == []


def test_number_check_catches_an_invented_number(hype):
    card, brief = hype
    fake = {**brief, "right": brief["right"] + [{"code": "x", "title": "t", "text": "Up 37.5% in 9 days."}]}
    assert number_problems(fake, card) == ["37.5", "9"]


def test_no_demo_brief_invents_a_number(demo_cards):
    for card in demo_cards:
        assert number_problems(build_veteran_brief(card), card) == [], card["post"]
