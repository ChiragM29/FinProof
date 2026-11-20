"""Reply card for WhatsApp groups: a facts-only reply in English, Kannada and Hindi, filled in from the scan.

Fixed templates, no machine translation at runtime. The Kannada and Hindi templates are marked as needing a
native speaker's check until the team confirms them (set CHECKED below).
"""

from __future__ import annotations

from .label import PRESSURE_CODES, is_pump

CHECKED = {"en": True, "kn": False, "hi": False}
LANGS = {"en": "English", "kn": "ಕನ್ನಡ", "hi": "हिन्दी"}

T = {
    "en": {
        "intro": "Before acting on this tip:",
        "sebi_missing": "the sender is not on FinProof's copy of SEBI's registered list",
        "sebi_none": "the post gives no SEBI registration number",
        "sebi_ok": "the sender's SEBI registration matches",
        "pressure": lambda n: f"the message uses {n} pressure tactic{'s' if n != 1 else ''}",
        "pressure_none": "no pressure tactics found",
        "upi": "payment goes to a personal UPI ID, not an @valid handle",
        "pump": "trading around the post looks like a pump pattern",
        "spike": "trading volume jumped before the post",
        "record": lambda w, s: f"{w} of {s} past calls from this source beat the Nifty 50",
        "record_none": "this source has no checkable track record",
        "case": "SEBI has an order on this stock",
        "outro": "Check registration at sebi.gov.in.",
    },
    "hi": {
        "intro": "इस टिप पर कुछ करने से पहले:",
        "sebi_missing": "भेजने वाला SEBI की पंजीकृत सूची (FinProof की प्रति) में नहीं है",
        "sebi_none": "पोस्ट में SEBI पंजीकरण संख्या नहीं है",
        "sebi_ok": "भेजने वाले का SEBI पंजीकरण मिलता है",
        "pressure": lambda n: f"संदेश में {n} दबाव वाली तरकीब{'ें' if n != 1 else ''} हैं" if n != 1 else "संदेश में 1 दबाव वाली तरकीब है",
        "pressure_none": "कोई दबाव वाली तरकीब नहीं मिली",
        "upi": "भुगतान एक निजी UPI ID पर जाता है, @valid हैंडल पर नहीं",
        "pump": "पोस्ट के आसपास कारोबार में पंप जैसा पैटर्न दिखा",
        "spike": "पोस्ट से पहले कारोबार (वॉल्यूम) अचानक बढ़ा",
        "record": lambda w, s: f"इस स्रोत की पिछली {s} टिप्स में से {w} ने Nifty 50 से बेहतर किया",
        "record_none": "इस स्रोत का कोई जाँचने लायक रिकॉर्ड नहीं है",
        "case": "इस शेयर पर SEBI का आदेश है",
        "outro": "पंजीकरण sebi.gov.in पर जाँचें।",
    },
    "kn": {
        "intro": "ಈ ಸಲಹೆಯ ಮೇಲೆ ಏನಾದರೂ ಮಾಡುವ ಮೊದಲು:",
        "sebi_missing": "ಕಳುಹಿಸಿದವರು SEBI ನೋಂದಾಯಿತ ಪಟ್ಟಿಯಲ್ಲಿ (FinProof ಪ್ರತಿ) ಇಲ್ಲ",
        "sebi_none": "ಪೋಸ್ಟ್‌ನಲ್ಲಿ SEBI ನೋಂದಣಿ ಸಂಖ್ಯೆ ಇಲ್ಲ",
        "sebi_ok": "ಕಳುಹಿಸಿದವರ SEBI ನೋಂದಣಿ ಹೊಂದುತ್ತದೆ",
        "pressure": lambda n: f"ಸಂದೇಶದಲ್ಲಿ {n} ಒತ್ತಡದ ತಂತ್ರ{'ಗಳಿವೆ' if n != 1 else 'ವಿದೆ'}",
        "pressure_none": "ಯಾವುದೇ ಒತ್ತಡದ ತಂತ್ರ ಕಂಡುಬಂದಿಲ್ಲ",
        "upi": "ಹಣ ವೈಯಕ್ತಿಕ UPI ID ಗೆ ಹೋಗುತ್ತದೆ, @valid ಹ್ಯಾಂಡಲ್‌ಗೆ ಅಲ್ಲ",
        "pump": "ಪೋಸ್ಟ್ ಸುತ್ತಮುತ್ತ ವಹಿವಾಟಿನಲ್ಲಿ ಪಂಪ್ ಮಾದರಿ ಕಂಡಿತು",
        "spike": "ಪೋಸ್ಟ್‌ಗೆ ಮೊದಲು ವಹಿವಾಟು (ವಾಲ್ಯೂಮ್) ಇದ್ದಕ್ಕಿದ್ದಂತೆ ಏರಿತು",
        "record": lambda w, s: f"ಈ ಮೂಲದ ಹಿಂದಿನ {s} ಸಲಹೆಗಳಲ್ಲಿ {w} Nifty 50 ಗಿಂತ ಉತ್ತಮವಾಗಿದ್ದವು",
        "record_none": "ಈ ಮೂಲಕ್ಕೆ ಪರಿಶೀಲಿಸಬಹುದಾದ ದಾಖಲೆ ಇಲ್ಲ",
        "case": "ಈ ಷೇರಿನ ಬಗ್ಗೆ SEBI ಆದೇಶವಿದೆ",
        "outro": "ನೋಂದಣಿಯನ್ನು sebi.gov.in ನಲ್ಲಿ ಪರಿಶೀಲಿಸಿ.",
    },
}


def facts(card: dict) -> list[tuple]:
    """The scan's facts, as template keys (with numbers where needed)."""
    codes = {w["code"] for w in card.get("warnings", [])}
    out = []
    if card.get("case"):
        out.append(("case",))
    status = (card.get("sebi") or {}).get("status")
    out.append(("sebi_ok",) if status in ("registered", "name_match") else
               ("sebi_none",) if status == "not_checked" else ("sebi_missing",))
    n = len(codes & set(PRESSURE_CODES))
    out.append(("pressure", n) if n else ("pressure_none",))
    if "personal_upi" in codes:
        out.append(("upi",))
    if is_pump(codes):
        out.append(("pump",))
    elif "volume_spike" in codes:
        out.append(("spike",))
    tr = card.get("track_record") or {}
    out.append(("record", tr["worked"], tr["scored"]) if tr.get("status") == "ok" else ("record_none",))
    return out


def build(card: dict) -> dict:
    items = facts(card)
    texts = {}
    for lang, t in T.items():
        parts = [t[key](*args) if args else t[key] for key, *args in items]
        texts[lang] = f"{t['intro']} " + "; ".join(parts) + f". {t['outro']}"
    return {"texts": texts, "langs": LANGS, "checked": CHECKED,
            "note": "Kannada and Hindi need a native-speaker check before use."}
