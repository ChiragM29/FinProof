"""FinProof AI chat: natural answers from Claude, grounded only in the FinProof card.

Safety layers, in order:
1. Questions asking what to buy/sell/hold or where a price will go never reach the model:
   the offline Claim Auditor refuses them, every time, word for word.
2. The model sees only a fact sheet built from the card and a system prompt that forbids
   advice and anything not in the fact sheet.
3. Every model answer goes through the same no-advice check as the cards (plus signal words
   such as "bullish" or "overbought"). If it fails, or the model is unavailable (no key, no
   internet, a 3-second timeout, quota, refusal), the offline Claim Auditor answers instead.
4. After a network failure the model is skipped for a short cool-down, so with no Wi-Fi every
   later answer comes straight from the offline engine, in well under a second.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time

from . import auditor, config
from .card import ADVICE_RE

MODEL = os.environ.get("FINPROOF_AI_MODEL", "claude-opus-5-5")
TIMEOUT_SECONDS = float(os.environ.get("FINPROOF_AI_TIMEOUT", "3"))
COOLDOWN_SECONDS = 60  # after a network failure, answer offline without trying the API again for this long
MAX_HISTORY = 6
CITE_TAGS = ("SEBI", "NSE 30D", "Volume", "Quote", "Tech")

SYSTEM_PROMPT = """You are the assistant inside FinProof, an app that helps retail investors in India judge stock tips they see on YouTube, Telegram and WhatsApp. FinProof checks the source and the information quality of a post. It is not investment advice.

Each user message contains a <fact_sheet> JSON object built by FinProof from one post and real NSE price data, followed by the user's question.

Rules:
- Answer only from the fact sheet. If it does not contain the answer, say what FinProof checked and that it can't tell from this post. Never add facts, prices, news or opinions of your own. You may explain general terms (pump-and-dump, SEBI registration, a UPI ID, the Nifty 50) in one plain sentence.
- Never say whether to buy, sell, hold, accumulate, exit or invest in any stock, never give a target or predicted price, and never call a stock good, safe, cheap or risky. If asked, reply that FinProof doesn't answer that, then point to the relevant facts.
- Don't call anyone a scammer or anything illegal. Describe warning signs as facts ("the post asks for payment to a personal UPI ID").
- When you use the post's own words, put them in quotation marks exactly as they appear in the fact sheet.
- If a fact comes from SYNTHETIC demo data, say so.
- Speak like a calm, experienced Indian market mentor teaching a first-time investor: explain why a fact matters in everyday words, critique the information and the process, never the stock. Don't claim personal experience or years in the market.
- Never describe an indicator as a signal (no "bullish", "bearish", "overbought", "oversold", "crossover means"). Describe what it measured, e.g. "RSI(14) at 76.2: a rapid recent climb".
- Format: first line, one plain-English takeaway sentence (no bullet). Then 2 to 4 lines starting with "- ", each one fact from the fact sheet ending with its evidence tag: [SEBI], [NSE 30D], [Volume], [Quote] or [Tech]. Nothing else: no headings, no bold, no closing remarks.
- Use plain, simple English; if the user writes in Hinglish or Kannada, you may reply in the same style."""

_state = {"last_error": None, "down_until": 0.0}
_lock = threading.Lock()
_client = None

# Policy phrases that may mention buying or selling without being advice.
_POLICY_RE = re.compile(r"\b(?:what|whether|when|which)\s+(?:stocks?\s+)?to\s+(?:buy|sell|hold)(?:\s*(?:,|or|and)\s*(?:to\s+)?(?:buy|sell|hold))*"
                        r"|\b(?:buy|sell)(?:/| or )(?:buy|sell|hold)\s+(?:advice|calls?|recommendations?|questions?)", re.I)
_QUOTED_RE = re.compile(r"“[^”]*”|\"[^\"]*\"|‘[^’]*’")
# Trading-signal words the model must not use about a stock (on top of the card's advice words).
SIGNAL_RE = re.compile(r"\b(?:bullish|bearish|overbought|oversold|avoid (?:this|the) stock|good stock|bad stock|"
                       r"will (?:rise|fall|go up|go down)|sure to|crossover means)\b", re.I)
_TAG_RE = re.compile(r"\s*\[(SEBI|NSE 30D|Volume|Quote|Tech)\]", re.I)
_BULLET_RE = re.compile(r"^(?:[-•*]|\d+[.)])\s+")


class AIUnreachable(RuntimeError):
    """The network, a timeout, quota or the API itself failed: worth a cool-down before trying again."""


def enabled() -> bool:
    return os.environ.get("FINPROOF_AI", "on").lower() != "off" and not config.OFFLINE


def status() -> dict:
    return {"enabled": enabled(), "model": MODEL, "key_found": bool(os.environ.get("ANTHROPIC_API_KEY")
                                                                      or os.environ.get("ANTHROPIC_AUTH_TOKEN")),
            "last_error": _state["last_error"]}


def advice_in(text: str) -> list[str]:
    """Advice wording in an AI answer, ignoring quoted post text and statements of the policy itself."""
    cleaned = _POLICY_RE.sub(" ", _QUOTED_RE.sub(" ", text))
    return [m.group(0) for rx in (ADVICE_RE, SIGNAL_RE) for m in rx.finditer(cleaned)]


def structure(text: str) -> tuple[str, list[dict]]:
    """Split a model answer into a headline and fact lines with their evidence tags."""
    head, lines = "", []
    for raw in text.splitlines():
        t = raw.strip().replace("**", "")
        if not t or t.startswith("#"):
            continue
        bullet = bool(_BULLET_RE.match(t))
        t = _BULLET_RE.sub("", t)
        cites = []
        for m in _TAG_RE.finditer(t):
            tag = next(c for c in CITE_TAGS if c.lower() == m.group(1).lower())
            if tag not in cites:
                cites.append(tag)
        t = _TAG_RE.sub("", t).strip()
        if not t:
            continue
        if not head and not bullet:
            head = t
        else:
            lines.append({"text": t, "evidence": [], "cite": cites})
    if not head and lines:
        head = lines.pop(0)["text"]
    return head, lines


def fact_sheet(card: dict) -> dict:
    """The only facts the model may use: a compact view of the card."""
    def claim_view(c: dict) -> dict:
        view = {k: c.get(k) for k in ("symbol", "company", "direction_text", "expected_prices", "stop_loss",
                                       "price_at_post", "renamed_from", "note", "price_scale_note")}
        t = c.get("technicals") or {}
        if t:  # point-in-time indicator readings, as of the last session before the post
            view["technicals_before_post"] = {"as_of": t.get("as_of"), "facts": [f["text"] for f in t.get("facts", [])]}
        m = c.get("market") or {}
        if m:
            view["market_before_post"] = {k: m.get(k) for k in ("status", "spike_ratio", "spike_date",
                                                                 "avg_traded_value_20d", "run_up_20d", "flags")}
        after = ((c.get("after_post") or {}).get("horizons") or {})
        if after:
            view["after_post"] = {d: {k: h.get(k) for k in ("status", "stock_return", "nifty_return", "excess_return",
                                                            "worked")} for d, h in after.items()}
        return {k: v for k, v in view.items() if v not in (None, [], {})}

    tr = card.get("track_record") or {}
    return {
        "post": {k: (card.get("post") or {}).get(k) for k in ("kind", "title", "channel", "posted_on", "posted_on_note",
                                                               "point_in_time")},
        "summary": (card.get("summary") or {}).get("text"),
        "warnings": [{"text": w["text"], "quotes": w.get("evidence", [])} for w in card.get("warnings", [])],
        "claims": [claim_view(c) for c in card.get("claims", [])],
        "track_record": {"text": tr.get("text"), "provenance": tr.get("provenance"),
                         "recent_tips": [{"posted_on": t.get("posted_on"), "symbol": t.get("symbol"),
                                          "direction": t.get("direction"),
                                          "after_30_days": (t.get("horizons") or {}).get("30")}
                                         for t in (tr.get("recent") or [])[-6:]]},
        "sebi": {"text": (card.get("sebi") or {}).get("text"), "coverage": (card.get("sebi") or {}).get("coverage_text")},
        "payments": card.get("payments"),
        "data": card.get("data_provenance"),
        "disclaimer": card.get("disclaimer"),
    }


def _get_client():
    global _client
    with _lock:
        if _client is None:
            import anthropic  # imported lazily so offline installs still work

            _client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY (from the env or finproof/.env)
        return _client


def _ask_claude(question: str, card: dict, history: list[dict]) -> str:
    import anthropic

    content = (f"<fact_sheet>\n{json.dumps(fact_sheet(card), ensure_ascii=False, sort_keys=True)}\n</fact_sheet>\n\n"
               f"Question: {question}")
    try:
        response = _get_client().with_options(timeout=TIMEOUT_SECONDS, max_retries=0).beta.messages.create(
            model=MODEL,
            max_tokens=2000,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=SYSTEM_PROMPT,
            messages=[*history, {"role": "user", "content": content}],
        )
    except anthropic.AuthenticationError as exc:
        raise RuntimeError("no valid Claude API key") from exc
    except anthropic.RateLimitError as exc:
        raise AIUnreachable("Claude API rate limit") from exc
    except anthropic.APIStatusError as exc:
        raise AIUnreachable(f"Claude API error {exc.status_code}") from exc
    except anthropic.APITimeoutError as exc:
        raise AIUnreachable(f"no answer within {TIMEOUT_SECONDS:g} seconds") from exc
    except anthropic.APIConnectionError as exc:
        raise AIUnreachable("no connection to the Claude API") from exc
    except anthropic.AnthropicError as exc:  # e.g. no credentials configured
        raise RuntimeError("Claude API not configured") from exc
    if response.stop_reason == "refusal":
        raise RuntimeError("the model declined")
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if not text:
        raise RuntimeError("empty answer")
    return text


def _clean_history(history: list[dict] | None) -> list[dict]:
    out = []
    for turn in (history or [])[-MAX_HISTORY:]:
        role, text = turn.get("role"), turn.get("content")
        if role in ("user", "assistant") and isinstance(text, str) and text.strip():
            out.append({"role": role, "content": text[:2000]})
    while out and out[0]["role"] != "user":
        out.pop(0)
    while out and out[-1]["role"] != "assistant":  # the new question is added after the history
        out.pop()
    return out


def chat(question: str, card: dict | None, history: list[dict] | None = None, ask=None) -> dict:
    """Answer one chat message. `ask` replaces the Claude call in tests."""
    question = (question or "").strip()[:500]
    offline = auditor.answer(question, card)
    if offline["refused"] or not card:
        return {**offline, "engine": "offline", "reason": "refusal" if offline["refused"] else "no card"}
    if not enabled():
        return {**offline, "engine": "offline", "reason": "AI is turned off (offline mode)"}
    if ask is None and not status()["key_found"]:
        return {**offline, "engine": "offline", "reason": "no Claude API key yet (add ANTHROPIC_API_KEY to finproof/.env)"}
    if time.monotonic() < _state["down_until"]:
        return {**offline, "engine": "offline", "reason": "AI offline (answered locally)"}
    try:
        text = (ask or _ask_claude)(question, card, _clean_history(history))
    except AIUnreachable as exc:  # Wi-Fi down, timeout, quota: stop trying for a while
        _state["last_error"] = str(exc)
        _state["down_until"] = time.monotonic() + COOLDOWN_SECONDS
        return {**offline, "engine": "offline", "reason": f"AI unavailable: {exc}"}
    except Exception as exc:  # never let the AI path break the chat
        _state["last_error"] = str(exc)
        return {**offline, "engine": "offline", "reason": f"AI unavailable: {exc}"}
    bad = advice_in(text)
    if bad:
        _state["last_error"] = "an AI answer failed the no-advice check"
        return {**offline, "engine": "offline", "reason": "the AI answer was replaced because it failed the no-advice check"}
    headline, lines = structure(text)
    if not headline:
        return {**offline, "engine": "offline", "reason": "the AI answer was empty"}
    _state["last_error"] = None
    return {"question": question, "engine": "ai", "model": MODEL, "refused": False, "refusal": None,
            "intent": offline["intent"], "text": text, "headline": headline, "lines": lines,
            "mentor": offline["mentor"]}
