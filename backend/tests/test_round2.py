"""Round 2: the Signal or Noise label, Price History mode, the real SEBI case on BSE, the reply card and the
Signal Map. Every string they show goes through the no-advice check."""

import datetime as dt
import re

import pytest
from fastapi.testclient import TestClient

from conftest import FakePrices, make_df
from finproof import api, auditor, cases, config, history, label, reply, signalmap
from finproof.ai import SIGNAL_RE
from finproof.card import ADVICE_RE, build_card, wording_problems
from finproof.ledger import Ledger, Tip
from finproof.market import YahooPrices
from finproof.veteran import EXTRA_RE

N = 400
POST = dt.date(2025, 6, 2)
ADVICE_EXTRA = re.compile(r"\b(?:entry|safe stock|good stock|target price)\b", re.I)


def clean(texts):
    for t in texts:
        for rx in (ADVICE_RE, EXTRA_RE, SIGNAL_RE, ADVICE_EXTRA):
            assert not rx.search(t), t


def strings(node, skip=("evidence", "url", "disclaimer")):  # the disclaimer states the policy itself
    if isinstance(node, dict):
        for k, v in node.items():
            if k not in skip:
                yield from strings(v, skip)
    elif isinstance(node, list):
        for v in node:
            yield from strings(v, skip)
    elif isinstance(node, str):
        yield node


def card_for(text, closes=None, volumes=None, tips=None, source_key=None):
    closes = closes or [100.0 + (i % 7) for i in range(N)]
    frame = make_df(closes, volumes=volumes or [2_000_000.0] * N, start="2024-06-03")
    prices = FakePrices({config.BENCHMARK: make_df([100.0] * N, start="2024-06-03"), "ITC": frame, "SBIN": frame})
    return build_card(text=text, ledger=Ledger(prices, tips=tips or []), prices=prices, posted_on=POST,
                      posted_on_note="t", source_key=source_key)


# ---------------------------------------------------------------- the Signal or Noise label
def test_label_has_two_separate_questions_and_tags_every_line():
    card = card_for("Join VIP calls, pay to rahul.k@ybl. 100% guaranteed! BUY ITC CMP 100 TGT 130")
    lab = label.build_label(card, "Join VIP calls, pay to rahul.k@ybl. 100% guaranteed! BUY ITC CMP 100 TGT 130")
    assert lab["right_before"]["title"] == "Were they right before?" and lab["fair"]["title"] == "Are they playing fair?"
    keys = [l["key"] for l in lab["fair"]["lines"]]
    assert keys[:5] == ["sebi", "disclosure", "pressure", "payment", "pump"]
    for l in lab["right_before"]["lines"] + lab["fair"]["lines"] + [lab["message_type"]]:
        assert l["provenance"] in ("REAL", "SYNTHETIC") and l["why"]
    assert lab["message_type"]["value"] == "Pressure pitch"
    assert next(l for l in lab["fair"]["lines"] if l["key"] == "payment")["evidence"] == ["rahul.k@ybl"]
    assert wording_problems(lab) == []


def test_label_says_not_enough_history_below_10_calls():
    tips = [Tip(f"t{i}", "demo", "Demo", "SBIN", "up", dt.date(2024, 9, 2) + dt.timedelta(days=7 * i), provenance="SYNTHETIC")
            for i in range(6)]
    lab = label.build_label(card_for("SBIN breakout", tips=tips, source_key="demo"))
    assert lab["right_before"]["lines"][0]["value"].startswith("Not enough history (6 scored calls")
    tips = [Tip(f"t{i}", "demo", "Demo", "SBIN", "up", dt.date(2024, 9, 2) + dt.timedelta(days=7 * i), provenance="SYNTHETIC")
            for i in range(12)]
    rec = label.build_label(card_for("SBIN breakout", tips=tips, source_key="demo"))["right_before"]["lines"][0]
    assert re.match(r"\d+ of 12 calls beat the Nifty 50 at 30 days \(\d{4}-\d\d-\d\d to \d{4}-\d\d-\d\d\)", rec["value"])
    assert rec["provenance"] == "SYNTHETIC"


@pytest.mark.parametrize("text,kind", [
    ("Learn how to read a balance sheet.", "Education"),
    ("SBIN looks bullish to me.", "Opinion"),
    ("SBIN CMP 100 TGT 130", "Unverified tip"),
    ("Join our VIP group! Hurry, last chance. SBIN CMP 100 TGT 130", "Pressure pitch"),
])
def test_message_types(text, kind):
    assert label.message_type(card_for(text))[0] == kind


def test_volume_alone_is_not_called_a_pump():
    vols = [2_000_000.0] * N
    i = list(make_df([1.0] * N, start="2024-06-03").index.date).index(POST)
    vols[i - 2] = 40_000_000.0
    card = card_for("Join VIP calls, pay to x.y@ybl. BUY ITC CMP 100 TGT 130", volumes=vols)
    assert "volume_spike" in {w["code"] for w in card["warnings"]}
    assert label.message_type(card)[0] == "Pressure pitch"  # big stock, not thin, no run-up: not a pump pattern
    pump = next(l for l in label.build_label(card)["fair"]["lines"] if l["key"] == "pump")
    assert pump["value"].startswith("Partly seen") and pump["tone"] == "warning"


def test_education_rule_is_cited_only_from_1_july_2026():
    text = "For educational purposes only. SBIN CMP 100 target 130"
    old = label.build_label(card_for(text))
    edu = next(l for l in old["fair"]["lines"] if l["key"] == "education")
    assert "30-day" not in edu["value"] and "8 May 2026" not in edu["why"]
    frame = make_df([100.0] * 700, start="2024-06-03")
    prices = FakePrices({config.BENCHMARK: frame, "SBIN": frame})
    new_card = build_card(text=text, ledger=Ledger(prices, tips=[]), prices=prices, posted_on=dt.date(2026, 7, 6), posted_on_note="t")
    new = next(l for l in label.build_label(new_card)["fair"]["lines"] if l["key"] == "education")
    assert "30-day" in new["value"] and "8 May 2026" in new["why"] and "1 July 2026" in new["why"]


# ---------------------------------------------------------------- Price History mode
def test_nifty50_list_has_exactly_50_companies():
    rows = history.nifty50()
    assert len(rows) == 50 and len({r["symbol"] for r in rows}) == 50
    assert {"RELIANCE", "TCS", "HDFCBANK", "BSE"} <= {r["symbol"] for r in rows}
    assert all(r["provenance"] == "REAL" and r["as_of"] for r in rows)


@pytest.mark.parametrize("q,sym", [("RELIANCE", "RELIANCE"), ("tcs", "TCS"), ("HDFC Bank", "HDFCBANK"), ("Infosys", "INFY"),
                                   ("BSE", "BSE"), ("BSE:CRYSTAL", "BSE:CRYSTAL")])
def test_bare_tickers_and_names_resolve(q, sym):
    assert history.resolve(q) == sym


@pytest.mark.parametrize("q", ["BUY ITC", "Bajaj", "hello world", "", "SBIN CMP 100 TGT 130", "x" * 70])
def test_tips_and_unclear_names_are_not_price_history(q):
    assert history.resolve(q) is None


@pytest.fixture
def client(monkeypatch):
    frame = make_df([100.0 + (i % 9) for i in range(N)], volumes=[2_000_000.0] * N, start="2024-06-03")
    prices = FakePrices({config.BENCHMARK: make_df([100.0 + i * 0.01 for i in range(N)], start="2024-06-03"),
                         "RELIANCE": frame, "TCS": frame})
    monkeypatch.setattr(api, "PRICES", prices)
    monkeypatch.setattr(api, "LEDGER", Ledger(prices, tips=[]))
    return TestClient(api.app)


def test_price_history_opens_with_no_flags_and_no_advice(client):
    card = client.get("/api/price-history", params={"q": "RELIANCE"}).json()
    assert card["mode"] == "history" and card["warnings"] == [] and card["history"]["exchange"] == "NSE"
    assert card["history"]["nifty50"] is True and card["claims"][0]["technicals"]
    clean(list(strings(card)))
    a = auditor.answer("Should I buy this?", card)
    assert a["refused"] is True
    for q in auditor.QUICK_PROMPTS[1:] + ["What does RSI mean here?"]:
        ans = auditor.answer(q, card)
        clean([ans["headline"], ans["mentor"]] + [ln["text"] for ln in ans["lines"]])
    assert client.get("/api/price-history", params={"q": "BUY ITC now"}).status_code == 404
    assert client.get("/api/nifty50").json()["count"] == 50


# ---------------------------------------------------------------- the real SEBI case on BSE
def case_prices():
    n = 140
    idx = make_df([1.0] * n, start="2022-05-02").index
    start = list(idx.date).index(dt.date(2022, 7, 18))
    closes = [10.0] * start + [10.0 + 2 * k for k in range(12)] + [32.0 - k for k in range(n - start - 12)]
    vols = [100_000.0] * start + [1_200_000.0] * 10 + [150_000.0] * (n - start - 10)
    return FakePrices({"BSE:CRYSTAL": make_df(closes, volumes=vols, start="2022-05-02"),
                       config.BENCHMARK: make_df([100.0] * n, start="2022-05-02")})


def test_case_facts_are_computed_from_prices():
    f = cases.facts(cases.CASES[0], case_prices())
    assert f["pin"] == "2022-07-18" and f["volume_ratio"] == 12.0 and f["peak"] == 32.0 and f["before"] == 10.0
    assert "12.0× that average" in f["lines"][1] and "+220.0%" in f["lines"][1]
    assert cases.facts(cases.CASES[0], FakePrices({})) is None  # no data: no numbers


def test_case_card_label_desk_and_reply():
    prices = case_prices()
    text = "18 Jul 2022 · SEBI case: BSE:CRYSTAL (scrip 540821)"
    card = build_card(text=text, ledger=Ledger(prices, tips=[]), prices=prices, posted_on=dt.date(2022, 7, 18), posted_on_note="t")
    cases.attach(card, prices)
    assert card["case"]["order"] == "SEBI interim order, 2 March 2023" and card["case"]["provenance"] == "REAL"
    lab = label.build_label(card, text)
    assert lab["message_type"]["value"] == "Pump pattern (SEBI case)"
    assert [l["key"] for l in lab["fair"]["lines"]] == ["order", "listing", "pump"]
    assert all(l["provenance"] == "REAL" for l in lab["fair"]["lines"])
    r = reply.build(card)
    assert r["texts"]["en"].startswith("Before acting on this tip: SEBI has an order on this stock")


@pytest.mark.skipif(not (config.CACHE / "prices" / "CRYSTAL_BO.csv").exists(), reason="BSE case not cached")
def test_real_case_loads_from_the_bse_cache():
    f = cases.facts(cases.CASES[0], YahooPrices(offline=True))
    assert f is not None and f["exchange"] == "BSE" and f["volume_ratio"] > 2.5


# ---------------------------------------------------------------- reply card and Signal Map
def test_reply_card_is_facts_only_in_three_languages():
    card = card_for("Join VIP calls, pay to rahul.k@ybl. 100% guaranteed! BUY ITC CMP 100 TGT 130")
    r = reply.build(card)
    assert set(r["texts"]) == {"en", "kn", "hi"} and r["checked"] == {"en": True, "kn": False, "hi": False}
    en = r["texts"]["en"]
    assert en.startswith("Before acting on this tip:") and en.endswith("Check registration at sebi.gov.in.")
    assert "personal UPI ID" in en and "pressure tactic" in en
    clean([en])
    for lang in ("kn", "hi"):
        assert "sebi.gov.in" in r["texts"][lang] and "UPI" in r["texts"][lang]
        for word in ("खरीद", "बेच", "ಖರೀದಿ", "ಮಾರಾಟ"):  # buy / sell
            assert word not in r["texts"][lang]


def test_signal_map_keeps_the_two_axes_separate():
    frame = make_df([100.0 + i * 0.1 for i in range(N)], volumes=[2_000_000.0] * N, start="2024-06-03")
    prices = FakePrices({config.BENCHMARK: make_df([100.0] * N, start="2024-06-03"), "SBIN": frame})
    tips = [Tip(f"a{i}", "a", "Source A (synthetic)", "SBIN", "up", dt.date(2024, 9, 2) + dt.timedelta(days=7 * i),
                provenance="SYNTHETIC") for i in range(12)]
    tips += [Tip(f"b{i}", "b", "Source B (synthetic)", "SBIN", "up", dt.date(2024, 9, 2) + dt.timedelta(days=7 * i),
                 provenance="SYNTHETIC") for i in range(4)]
    m = signalmap.build(Ledger(prices, tips=tips), prices)
    assert [r["source_label"] for r in m["plotted"]] == ["Source A (synthetic)"]
    a = m["plotted"][0]
    assert a["right"] == 1.0 and a["fair"] == 1.0 and a["provenance"] == "SYNTHETIC"
    assert [r["source_label"] for r in m["not_enough_history"]] == ["Source B (synthetic)"]
    clean([m["note"]] + list(m["axes"].values()))
