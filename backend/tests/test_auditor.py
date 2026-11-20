"""Offline Claim Auditor: beginner questions about indicators and market concepts, answered from the
card's own numbers in the cited brief format (headline, tagged facts, mentor's note), never as advice."""

import datetime as dt

import pytest

from conftest import FakePrices, make_df
from finproof import auditor, config
from finproof.ai import SIGNAL_RE
from finproof.card import ADVICE_RE, build_card
from finproof.ledger import Ledger
from finproof.veteran import EXTRA_RE

POST = dt.date(2025, 6, 2)


def card_for(text, closes=None, volumes=None):
    n = 400
    closes = closes or [100 + 8 * ((i % 23) / 23) + i * 0.1 for i in range(n)]
    stock = make_df(closes, volumes=volumes or [3_000_000.0] * n, start="2024-06-03",
                    highs=[c * 1.015 for c in closes], lows=[c * 0.985 for c in closes])
    prices = FakePrices({config.BENCHMARK: make_df([100.0] * n, start="2024-06-03"), "SBIN": stock})
    return build_card(text=text, ledger=Ledger(prices, tips=[]), prices=prices, posted_on=POST, posted_on_note="t")


@pytest.fixture(scope="module")
def card():
    return card_for("Join VIP calls, pay to rahul.k@ybl. BUY SBIN CMP 125 TGT 150, 100% guaranteed!")


BEGINNER = [
    ("What does RSI mean here?", "tech_rsi"),
    ("Explain the MACD", "tech_macd"),
    ("What is VWAP?", "tech_vwap"),
    ("Are the Bollinger Bands wide?", "tech_bollinger"),
    ("What is the EMA 50?", "tech_ema"),
    ("What is a simple moving average?", "tech_sma"),
    ("How volatile is it? What is ATR?", "tech_atr"),
    ("Is it at rock bottom or near its 52-week high?", "tech_levels"),
    ("What do the technical indicators show?", "tech"),
    ("What is a pump and dump?", "concept_pump"),
    ("Why compare with Nifty 50?", "concept_nifty"),
    ("What does SEBI registration mean?", "concept_sebi"),
    ("What is thin liquidity?", "concept_thin"),
    ("Why is a personal UPI risky?", "concept_upi"),
]


@pytest.mark.parametrize("question,intent", BEGINNER)
def test_beginner_questions_get_a_cited_brief(card, question, intent):
    a = auditor.answer(question, card)
    assert a["intent"] == intent and not a["refused"]
    assert a["headline"] and a["mentor"] and a["lines"]
    assert all(ln["cite"] and set(ln["cite"]) <= set(auditor.CITES) for ln in a["lines"])
    for text in [a["headline"], a["mentor"]] + [ln["text"] for ln in a["lines"]]:
        for rx in (ADVICE_RE, EXTRA_RE, SIGNAL_RE):
            assert not rx.search(text), text


def test_indicator_answers_use_the_cards_point_in_time_numbers(card):
    t = card["claims"][0]["technicals"]
    assert t["as_of"] < POST.isoformat()
    rsi = auditor.answer("What does RSI mean here?", card)
    assert f"RSI(14) was {t['rsi14']:.1f}" in rsi["headline"]
    atr = auditor.answer("What is ATR?", card)
    assert f"±{abs(round(t['atr14_pct'] * 100, 1)):.1f}%" in atr["headline"]
    vwap = auditor.answer("What is VWAP?", card)
    assert f"₹{t['vwap20']:,.2f}" in vwap["headline"]
    assert any("The post quotes ₹125.00" in ln["text"] and ln["cite"] == ["Quote", "Tech"] for ln in vwap["lines"])
    lv = auditor.answer("Is it near its 52-week high?", card)
    assert f"₹{t['close']:,.2f}" in lv["headline"] and "52-week high" in lv["headline"]


def test_concept_answers_point_at_this_posts_facts(card):
    upi = auditor.answer("Why is a personal UPI risky?", card)
    assert any(ln["evidence"] == ["rahul.k@ybl"] for ln in upi["lines"])
    pump = auditor.answer("What is a pump and dump?", card)
    m = card["claims"][0]["market"]
    assert any(f"{m['spike_ratio']:.1f}×" in ln["text"] for ln in pump["lines"])
    thin = auditor.answer("What is thin liquidity?", card)
    assert any(f"₹{m['avg_traded_value_20d'] / 1e7:,.2f} crore" in ln["text"] for ln in thin["lines"])


def test_card_without_price_history_still_answers_indicator_questions():
    c = card_for("BUY SBIN now", closes=[100.0] * 400)
    c["claims"][0].pop("technicals", None)
    a = auditor.answer("What does RSI mean here?", c)
    assert a["headline"].startswith("There is no price history") and a["lines"]


def test_quick_prompts_cover_the_guardrail_and_beginner_questions(card):
    assert auditor.QUICK_PROMPTS[0] == "Should I buy this?" and len(auditor.QUICK_PROMPTS) == 4
    for q in auditor.QUICK_PROMPTS:
        a = auditor.answer(q, card)
        assert a["headline"] and a["mentor"]
    assert auditor.answer(auditor.QUICK_PROMPTS[0], card)["refused"] is True


def test_advice_is_still_refused_even_when_phrased_as_a_technical_question(card):
    for q in ("RSI is low, should I buy?", "MACD crossed, time to sell?", "Will it go up after the breakout?",
              "What's the target price from the 52-week high?"):
        a = auditor.answer(q, card)
        assert a["refused"] is True and a["headline"] == auditor.REFUSAL
