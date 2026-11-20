"""Media & impersonation cues: patterns common in fake-video and social-media stock scams.

Deterministic and non-advisory. These are observed cues in the post's own words, never proof that a
clip is fake: FinProof does not analyse the video file itself and says so.
"""

from __future__ import annotations

import re

# Famous people and regulators whose names are borrowed by scam clips ("leaked interview", fake endorsements).
IMPERSONATION = [
    r"(?:mukesh|anil)\s+ambani", r"\bambani\b", r"ratan\s+tata", r"gautam\s+adani", r"narayana\s+murthy",
    r"nirmala\s+sitharaman", r"elon\s+musk", r"(?:rakesh\s+)?jhunjhunwala", r"nithin\s+kamath", r"radhakishan\s+damani",
    r"sebi\s+(?:chair\w*|chief|head|official)", r"rbi\s+(?:governor|approved|certified|backed)", r"sebi\s+(?:approved|certified|backed)",
    r"(?:nse|bse)\s+(?:approved|certified)", r"leaked\s+(?:interview|video|audio|call|clip)",
    r"(?:ai|auto)[\s-]*(?:auto[\s-]*)?trading\s+(?:bot|robot|software|app)", r"\bai\s+(?:bot|robot)\b",
]
# Pushes off the platform to a private channel, or scripted "fixed profit" lines.
FUNNEL = [
    r"link\s+in\s+(?:the\s+)?bio", r"\bdm\s+(?:me|us|now|for)\b", r"\bdm\b[^.\n]{0,20}\bcalls?\b",
    r"free\s+(?:whatsapp|telegram|vip)\s+(?:vip\s+)?(?:group|channel)", r"join\s+(?:our\s+|my\s+)?(?:free\s+)?(?:whatsapp|telegram)",
    r"100\s*%\s*accura\w*", r"(?:daily|weekly|monthly)\s+fixed\s+(?:profit|income|returns?)",
    r"fixed\s+(?:daily|weekly|monthly)\s+(?:profit|income|returns?)", r"guaranteed\s+(?:daily|weekly|monthly)",
]
DOWNSIDE = re.compile(r"\b(?:risk\w*|downside|stop[\s-]*loss|sl|could\s+fall|may\s+fall|loss(?:es)?|not\s+guaranteed)\b", re.I)
IMPERSONATION_RE = re.compile("|".join(f"(?:{p})" for p in IMPERSONATION), re.I)
FUNNEL_RE = re.compile("|".join(f"(?:{p})" for p in FUNNEL), re.I)

VIDEO_KINDS = {"youtube", "instagram", "x"}
# Warning codes shown together as "Media & Impersonation Flags".
MEDIA_CODES = ("impersonation", "funnel", "personal_upi", "missing_context", "volume_spike")
TITLE = "Media & Impersonation Flags"
NOTE = "Observed cues only, not proof a clip is fake."

TEXT = {
    "impersonation": "Uses a famous name, a regulator or an AI-bot story, a pattern common in fake videos and "
                     "impersonation scams. FinProof cannot verify the clip itself.",
    "funnel": "Pushes readers to a private channel or a fixed-profit promise, away from public view.",
    "missing_context": "A stock call on a video or social post with no SEBI registration number and no mention of risk.",
}


def _found(rx: re.Pattern, text: str) -> list[str]:
    return sorted({re.sub(r"\s+", " ", m.group(0).strip().lower()) for m in rx.finditer(text or "")})[:4]


def flags(text: str, kind: str, *, sebi_numbers: list[str], priced_call: bool) -> list[dict]:
    """Warnings for impersonation bait, scam funnels and (on video/social posts) a call with no context."""
    out = []
    imp = _found(IMPERSONATION_RE, text)
    if imp:
        out.append({"code": "impersonation", "text": TEXT["impersonation"], "evidence": imp})
    fun = _found(FUNNEL_RE, text)
    if fun:
        out.append({"code": "funnel", "text": TEXT["funnel"], "evidence": fun})
    if kind in VIDEO_KINDS and priced_call and not sebi_numbers and not DOWNSIDE.search(text or ""):
        out.append({"code": "missing_context", "text": TEXT["missing_context"]})
    return out


def audit(card: dict) -> dict:
    """The card's media section: which media and impersonation cues were observed."""
    codes = [w["code"] for w in card.get("warnings", []) if w["code"] in MEDIA_CODES]
    return {"title": TITLE, "note": NOTE, "platform": card.get("post", {}).get("kind"), "codes": codes}
