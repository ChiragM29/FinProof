"""Pull the tip out of a message or a video transcript.

Rule-based on purpose: it is fast, works offline, and every decision can be
explained to a judge. Known weak spots are listed in eval/README.md.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from functools import lru_cache

from .market import company_name, current_symbol, nse_companies, symbol_changes

# NSE symbols that are also ordinary words in tip messages.
SYMBOL_BLOCKLIST = {"BSE", "AVG", "PAR", "DEN", "TRU"}
# "BSE:CRYSTAL", "BSE: 540821", "bse-crystal": a listing on BSE. A bare "BSE" in prose is the exchange, so it
# counts as the company BSE Ltd only when tagged (#BSE, $BSE) or written "BSE Ltd" / "BSE Limited" / "BSE share(s)".
BSE_PREFIX_RE = re.compile(r"(?<![A-Za-z0-9])BSE\s*[:\-]\s*([A-Za-z][A-Za-z0-9&\-]{1,19}|\d{6})(?![A-Za-z0-9])", re.I)
BSE_COMPANY_RE = re.compile(r"\s*(?:ltd|limited|shares?|stock)\b", re.I)

# Words that should never count as a company name on their own.
COMMON_WORDS = set("""
a an and the of for in on at to by with from into over under up down out off is are was were be been being
this that these those it its it's i we you he she they my our your his her their me us them who what which
buy sell hold long short target stop loss profit gain return returns price prices stock stocks share shares
market markets trade trading invest investment investor investors money cash fund funds bank banks power
energy india indian international global national new next best good top big great sure safe high low
open close today week month year day days time now just only very more most less all any some every
call calls put option options future futures nifty sensex index chart level zone support resistance
breakout breakdown rally jump fall crash bull bull's bear trend entry exit growth value capital finance
financial services service industries industry company limited ltd products product systems system solutions
technologies technology tech digital media infra infrastructure housing home life health care pharma
metal metals steel cement cements auto motors chemicals chemical textiles textile foods food sugar paper
oil gas petroleum refinery mining minerals realty estate properties projects engineering electric electricals
global ventures enterprises corporation corp holdings group trust asset assets wealth securities insurance
credit agro green solar wind water hotels hotel resorts travel logistics shipping ports airlines aviation
bhai bro sir ji abhi aaj kal paisa paise pakka pukka jaldi accha acha sahi bas dekho dekh lo le lena karo
kar raha rahe hai hain tha thi nahi nahin mat bilkul sab kuch bahut zyada kam bada chota mast jabardast
guru dost yaar saar anna akka madi maadi beda beku sakkat chennagide swalpa jasti bega illi alli namma nimma
""".split())

# Everyday names people use for a few very common stocks (checked against the NSE list).
NICKNAMES = {
    "reliance": "RELIANCE", "ril": "RELIANCE", "sbi": "SBIN", "l&t": "LT", "larsen": "LT", "airtel": "BHARTIARTL",
    "zomato": "ETERNAL", "hul": "HINDUNILVR", "m&m": "M&M", "infosys": "INFY", "infy": "INFY", "tcs": "TCS",
    "itc": "ITC", "maruti": "MARUTI", "vedanta": "VEDL",
}
# Everyday multi-word names that differ from NSE's full company name.
ALIASES = {
    "mazagon dock": "MAZDOCK", "cochin shipyard": "COCHINSHIP", "garden reach": "GRSE", "hindustan aeronautics": "HAL",
    "bharat electronics": "BEL", "coal india": "COALINDIA", "yes bank": "YESBANK", "tata power": "TATAPOWER",
    "tata steel": "TATASTEEL", "motherson sumi": "MOTHERSON", "adani ports": "ADANIPORTS", "adani green": "ADANIGREEN",
    "adani power": "ADANIPOWER", "adani enterprises": "ADANIENT",
}
# Stock names as they are written in Hindi video titles and posts (Devanagari). Group names (टाटा, अदानी) are left out.
HINDI_NAMES = {
    "रिलायंस": "RELIANCE", "इंफोसिस": "INFY", "इन्फोसिस": "INFY", "टीसीएस": "TCS", "आईटीसी": "ITC", "एसबीआई": "SBIN",
    "एचडीएफसी बैंक": "HDFCBANK", "आईसीआईसीआई बैंक": "ICICIBANK", "एयरटेल": "BHARTIARTL", "मारुति": "MARUTI",
    "विप्रो": "WIPRO", "एलआईसी": "LICI", "पेटीएम": "PAYTM", "यस बैंक": "YESBANK", "आईआरएफसी": "IRFC", "बीईएल": "BEL",
    "एचएएल": "HAL", "ओएनजीसी": "ONGC", "कोल इंडिया": "COALINDIA", "एनटीपीसी": "NTPC", "सुजलॉन": "SUZLON",
    "वेदांता": "VEDL", "ज़ोमैटो": "ETERNAL", "जोमैटो": "ETERNAL", "टाटा मोटर्स": "TMPV", "टाटा स्टील": "TATASTEEL",
    "टाटा पावर": "TATAPOWER", "अदानी पोर्ट्स": "ADANIPORTS", "आईआरईडीए": "IREDA", "बजाज फाइनेंस": "BAJFINANCE",
}
DEVA = "\u0900-\u097F"
HINDI_RE = re.compile("(?<![" + DEVA + "])(" + "|".join(sorted(map(re.escape, HINDI_NAMES), key=len, reverse=True)) + ")(?![" + DEVA + "])")
# A single ordinary-looking word ("Yogi", "Rites", "Modi") is a stock only when the sentence is about stocks.
STOCK_CONTEXT_RE = re.compile(
    r"\b(?:shares?|stocks?|ltd|limited|target|tgt|cmp|ltp|sl|stop\s*loss|price|results?|q[1-4]|ipo|buy|sell|hold|nse|bse|"
    r"portfolio|picks?|invest\w*|breakout|multibagger|rally|crash|bullish|bearish|dividend|earnings|order|orders|strong|weak)\b"
    r"|₹|%|शेयर|स्टॉक|तेजी|गिरावट|उछाल",
    re.I)
NICKNAME_KEYS = {re.sub(r"[^a-z0-9]", "", k.replace("&", "and")): v for k, v in NICKNAMES.items()}

NAME_SUFFIXES = {"limited", "ltd", "pvt", "private", "the", "company", "co", "corporation", "corp", "inc"}
GENERIC_TAIL = {"industries", "india", "of", "and", "enterprises", "corporation", "company", "co"}


def _simplify(name: str) -> str:
    words = re.sub(r"[^a-z0-9 ]", " ", name.lower().replace("&", " and ")).split()
    words = [w for w in words if w not in NAME_SUFFIXES]
    return " ".join(words)


@lru_cache(maxsize=1)
def _name_index() -> tuple[dict[str, set[str]], dict[str, set[str]], set[str]]:
    """(name key -> symbols, first word -> symbols, symbol set)."""
    df = nse_companies()
    keys: dict[str, set[str]] = {}
    first: dict[str, set[str]] = {}
    for sym, name in zip(df["SYMBOL"], df["NAME"]):
        simple = _simplify(name)
        if not simple:
            continue
        words = simple.split()
        candidates = {simple}
        while words and words[-1] in GENERIC_TAIL:
            words = words[:-1]
            if words:
                candidates.add(" ".join(words))
        for k in candidates:
            if len(k) >= 4 and k not in COMMON_WORDS:
                keys.setdefault(k, set()).add(sym)
        fw = simple.split()[0]
        if len(fw) >= 4 and fw not in COMMON_WORDS:
            first.setdefault(fw, set()).add(sym)
    listed = set(df["SYMBOL"])
    for alias, alias_sym in ALIASES.items():
        if alias_sym in listed:
            keys[alias] = {alias_sym}
    return keys, first, listed


# ---------------------------------------------------------------- patterns

UP_WORDS = [
    r"buy", r"buying", r"long", r"bullish", r"accumulate", r"upside", r"breakout", r"multibagger",
    r"rocket", r"to the moon", r"go(?:es|ing)? up", r"will rise", r"rally", r"kharid\w*", r"le lo",
    r"upar ja\w*", r"chadhega", r"badhega", r"togoli", r"tagoli",
]
DOWN_WORDS = [
    r"sell", r"selling", r"short", r"bearish", r"breakdown", r"downside", r"avoid", r"exit",
    r"crash", r"will fall", r"go(?:es|ing)? down", r"bech\w*", r"gir\w*ga", r"neeche ja\w*", r"maari",
]
NEGATIONS = r"(?:don'?t|do not|never|not|no need to|mat|nahi|nahin|beda)"

UP_RE = re.compile(r"\b(?:" + "|".join(UP_WORDS) + r")\b", re.I)
DOWN_RE = re.compile(r"\b(?:" + "|".join(DOWN_WORDS) + r")\b", re.I)
ANY_NEG_RE = re.compile(r"\b(?:don'?t|do not|never|not|no need to|mat|nahi|nahin|beda|stay away|avoid)\b", re.I)
NEG_RE = re.compile(r"\b" + NEGATIONS + r"\s+(?:\w+\s+){0,2}?(?:" + "|".join(UP_WORDS + DOWN_WORDS) + r")\b", re.I)

NUM = r"(?:rs\.?|inr|₹)?\s*(\d{1,6}(?:\.\d{1,2})?)"
EXPECTED_RE = re.compile(r"\b(?:tgt|target|targets|tp|t1|t2|t3)\s*[:\-=]?\s*" + NUM + r"((?:\s*[/,\-&]\s*\d{1,6}(?:\.\d{1,2})?)*)", re.I)
STOP_RE = re.compile(r"\b(?:sl|stop\s*loss|stoploss)\s*[:\-=]?\s*" + NUM, re.I)
CMP_RE = re.compile(r"\b(?:cmp|ltp|current price)\s*[:\-=]?\s*" + NUM, re.I)
PCT_RE = re.compile(r"(\d{1,4})\s*%\s*(?:return|returns|upside|gain|gains|profit)", re.I)
REGNO_RE = re.compile(r"\bIN[AH]\d{9}\b", re.I)
SEBI_CLAIM_RE = re.compile(r"\bsebi[\s\-]*(?:registered|regd|reg\.?|registration|certified|approved)\b", re.I)

PRESSURE = {
    "guarantee": [r"guarantee\w*", r"100\s*%\s*(?:sure|safe|accurate|profit)", r"sure[\s\-]?shot", r"pakka",
                  r"risk[\s\-]?free", r"no risk", r"zero risk", r"fixed return\w*", r"can'?t lose"],
    "urgency": [r"buy now", r"right now", r"before \d{1,2}\s*(?:am|pm)", r"last chance", r"today only",
                r"hurry", r"jaldi", r"don'?t miss", r"limited time", r"before it'?s too late", r"immediately"],
    "big_promise": [r"multibagger", r"\d{1,3}\s*x\b(?:\s*(?:return|returns|stock))?", r"double your money",
                    r"paisa double", r"rocket", r"to the moon", r"jackpot", r"life[\s\-]?changing"],
    "insider": [r"insider", r"inside (?:news|info\w*|tip)", r"operator", r"big news coming", r"secret",
                r"news (?:is )?coming", r"management (?:told|said) us"],
    "paid_group": [r"premium group", r"vip group", r"paid group", r"vip calls?", r"vip channel", r"premium calls?",
                   r"join (?:our|my)? ?(?:telegram|whatsapp)",
                   r"t\.me/", r"chat\.whatsapp\.com", r"subscription", r"paid call\w*"],
}
PRESSURE_RE = {k: re.compile(r"\b(?:" + "|".join(v) + r")", re.I) for k, v in PRESSURE.items()}

# UPI IDs (name@psp). An email has a dot after the @-part, so it never matches.
UPI_RE = re.compile(r"(?<![\w.@-])([a-z0-9][a-z0-9._-]{1,63}@[a-z][a-z0-9]{1,30})(?![\w@-]|\.\w)", re.I)
KNOWN_PSPS = {
    "ybl", "ibl", "axl", "apl", "yapl", "upi", "paytm", "okaxis", "okhdfcbank", "okicici", "oksbi", "ptyes",
    "ptaxis", "pthdfc", "ptsbi", "axisbank", "hdfcbank", "icici", "sbi", "kotak", "idfcbank", "freecharge",
    "jupiteraxis", "naviaxis", "slc", "superyes", "fam", "airtel", "jio", "barodampay", "pnb", "yesbank",
    "waicici", "wahdfcbank", "wasbi", "waaxis", "indus", "federal", "rbl", "abfspay", "postbank", "kbl",
}
PAYMENT_WORDS_RE = re.compile(r"\b(?:upi|gpay|google pay|phonepe|phone pe|paytm|pay|payment|fees?|subscribe|"
                              r"subscription|join|vip|premium)\b", re.I)

# "Only education" style disclaimers, used to spot the loophole of naming a stock with price levels anyway.
DISCLAIMER_RE = re.compile(
    r"\b(?:for\s+)?(?:educational|education|study|learning)\s+(?:purposes?\s+)?only\b"
    r"|\b(?:for\s+)?educational\s+purposes?\b"
    r"|\bjust\s+(?:for\s+)?education\b"
    r"|\bnot\s+(?:a\s+)?sebi[\s-]*(?:registered|regd)\b"
    r"|\bnot\s+(?:a\s+)?(?:financial|investment)\s+advi[cs]e\b"
    r"|\bnot\s+a\s+recommendation\b"
    r"|\bdo\s+your\s+own\s+research\b|\bdyor\b", re.I)
NOT_REGISTERED_RE = re.compile(r"\bnot\s+(?:a\s+)?sebi[\s-]*(?:registered|regd)\b", re.I)


def _upi_ids(text: str) -> list[dict]:
    found: dict[str, dict] = {}
    pay_context = bool(PAYMENT_WORDS_RE.search(text))
    for m in UPI_RE.finditer(text):
        upi = m.group(1)
        psp = upi.rsplit("@", 1)[1].lower()
        validated = psp.startswith("valid")
        if validated or psp in KNOWN_PSPS or psp.startswith(("ok", "pt", "wa")) or pay_context:
            found.setdefault(upi.lower(), {"id": upi, "validated_format": validated})
    return list(found.values())


def _claims_registration(text: str) -> bool:
    """True if the post says it IS SEBI registered (not 'not SEBI registered')."""
    for m in SEBI_CLAIM_RE.finditer(text):
        before = text[max(0, m.start() - 12):m.start()].lower()
        if not re.search(r"\b(?:not|non|un)\W*(?:a\s+)?$", before):
            return True
    return False


# ---------------------------------------------------------------- results

@dataclass
class StockClaim:
    symbol: str | None
    company: str | None
    mentions: int
    direction: str  # up | down | mixed | unclear
    expected_prices: list[float] = field(default_factory=list)
    stop_loss: float | None = None
    price_at_post: float | None = None
    ambiguous: bool = False
    candidates: list[str] = field(default_factory=list)
    matched_text: str = ""
    renamed_from: str | None = None
    negated: bool = False


@dataclass
class Extraction:
    claims: list[StockClaim]
    pressure: dict[str, list[str]]
    percent_promises: list[int]
    sebi_numbers: list[str]
    claims_sebi_registration: bool
    negation_found: bool
    words: int
    upi_ids: list[dict] = field(default_factory=list)
    disclaimers: list[str] = field(default_factory=list)
    says_not_registered: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- matching

def _tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9&'\-\.₹%/]+", text)


def find_stocks(text: str) -> list[tuple[int, int, str | None, list[str], str]]:
    """Return (start, end, symbol, candidates, matched) spans for every stock mention.

    symbol is None when the mention is ambiguous (e.g. "Tata" alone).
    """
    keys, first, symbols = _name_index()
    known = symbols | set(symbol_changes())
    found: list[tuple[int, int, str | None, list[str], str]] = []
    taken: list[tuple[int, int]] = []

    def free(a: int, b: int) -> bool:
        return all(b <= x or a >= y for x, y in taken)

    # 0. Exchange prefix: "BSE:CRYSTAL" (or BSE: 540821) names a BSE listing, whether or not NSE lists it.
    for m in BSE_PREFIX_RE.finditer(text):
        sym = f"BSE:{m.group(1).upper()}"
        found.append((m.start(), m.end(), sym, [sym], m.group(0)))
        taken.append((m.start(), m.end()))

    # 1. Exact NSE symbols written in capitals, or tagged with # or $.
    for m in re.finditer(r"(?<![A-Za-z0-9])[#$]?([A-Z][A-Z0-9&\-]{1,19})(?![A-Za-z0-9])", text):
        sym = m.group(1)
        tagged = m.group(0)[0] in "#$"
        if not free(m.start(), m.end()):
            continue
        if sym == "BSE" and (tagged or BSE_COMPANY_RE.match(text, m.end())):
            found.append((m.start(), m.end(), "BSE", ["BSE"], m.group(0)))  # the company BSE Ltd (a Nifty 50 stock)
            taken.append((m.start(), m.end()))
            continue
        if sym in known and sym not in SYMBOL_BLOCKLIST and (len(sym) >= 3 or tagged):
            sym = current_symbol(sym)
            found.append((m.start(), m.end(), sym, [sym], m.group(0)))
            taken.append((m.start(), m.end()))
    for m in re.finditer(r"[#$]([A-Za-z][A-Za-z0-9&\-]{1,19})", text):
        sym = m.group(1).upper()
        if sym in known and free(m.start(), m.end()):
            sym = current_symbol(sym)
            found.append((m.start(), m.end(), sym, [sym], m.group(0)))
            taken.append((m.start(), m.end()))

    # 1b. Stock names written in Hindi (Devanagari).
    for m in HINDI_RE.finditer(text):
        sym = HINDI_NAMES[m.group(1)]
        if sym in symbols and free(m.start(), m.end()):
            found.append((m.start(), m.end(), sym, [sym], m.group(0)))
            taken.append((m.start(), m.end()))

    # 2. Company names, longest match first (up to 5 words).
    words = list(re.finditer(r"[A-Za-z0-9&]+", text))
    lowered = [re.sub(r"[^a-z0-9]", "", w.group(0).lower().replace("&", "and")) for w in words]
    for size in range(5, 0, -1):
        for i in range(len(words) - size + 1):
            a, b = words[i].start(), words[i + size - 1].end()
            if not free(a, b):
                continue
            key = " ".join(lowered[i:i + size])
            if size == 1 and key in NICKNAME_KEYS and NICKNAME_KEYS[key] in symbols:
                sym = NICKNAME_KEYS[key]
                found.append((a, b, sym, [sym], text[a:b]))
                taken.append((a, b))
            elif size == 1 and key in keys and len(first.get(key, ())) >= 2:
                # e.g. "Adani": one company's short name, but also a group with several listed companies.
                syms = sorted(keys[key]) + sorted(first[key] - keys[key])
                found.append((a, b, None, syms[:8], text[a:b]))
                taken.append((a, b))
            elif key in keys:
                syms = sorted(keys[key])
                sym = syms[0] if len(syms) == 1 else None
                found.append((a, b, sym, syms, text[a:b]))
                taken.append((a, b))
            elif size == 1 and len(first.get(key, ())) >= 2 and words[i].group(0)[0].isupper():
                # A group name such as "Tata" or "Adani": several companies, so flag it, don't guess.
                found.append((a, b, None, sorted(first[key])[:8], text[a:b]))
                taken.append((a, b))
    # A one-word name that is not in capitals ("Yogi Adityanath", "Last Rites", "PM Modi") counts only when its sentence
    # is about stocks or names another stock; otherwise it is an ordinary word, not a stock mention.
    strong = [(a, b) for a, b, sym, _c, m in found if sym and (" " in m.strip() or m.isupper() or m[:1] in "#$" or
                                                                 re.sub(r"[^a-z0-9]", "", m.lower()) in NICKNAME_KEYS or
                                                                 any("\u0900" <= ch <= "\u097f" for ch in m))]

    def keep(span) -> bool:
        a, b, sym, _cands, m = span
        if " " in m.strip() or m.isupper() or m[:1] in "#$" or (a, b) in strong:
            return True
        seg = _window(text, a, b, words=14)
        if STOCK_CONTEXT_RE.search(seg) or UP_RE.search(seg) or DOWN_RE.search(seg):
            return True
        return any(x != a and abs(x - a) < 120 for x, _y in strong)
    return sorted(s for s in found if keep(s))


SEGMENT_BREAK = re.compile(r"\n|(?<!\d)[.!?](?!\d)")


def _window(text: str, start: int, end: int, words: int = 14) -> str:
    """Words around a mention, without crossing into the previous or next line/sentence."""
    seg_start = max((m.end() for m in SEGMENT_BREAK.finditer(text, 0, start)), default=0)
    nxt = SEGMENT_BREAK.search(text, end)
    seg_end = nxt.start() if nxt else len(text)
    left = text[seg_start:start].split()[-words:]
    right = text[end:seg_end].split()[:words]
    return " ".join(left + [text[start:end]] + right)


def _direction(snippet: str) -> tuple[str, bool]:
    negated = bool(NEG_RE.search(snippet))
    cleaned = NEG_RE.sub(" ", snippet)
    up = bool(UP_RE.search(cleaned))
    down = bool(DOWN_RE.search(cleaned))
    if negated and not (up or down):
        return "unclear", True
    if up and down:
        return "mixed", negated
    if up:
        return "up", negated
    if down:
        return "down", negated
    return "unclear", negated


def _numbers(pattern: re.Pattern, snippet: str) -> list[float]:
    out: list[float] = []
    for m in pattern.finditer(snippet):
        out.append(float(m.group(1)))
        if m.lastindex and m.lastindex >= 2 and m.group(2):
            out.extend(float(x) for x in re.findall(r"\d{1,6}(?:\.\d{1,2})?", m.group(2)))
    return out


def extract(text: str) -> Extraction:
    text = text or ""
    spans = find_stocks(text)
    by_symbol: dict[str, StockClaim] = {}
    negation_any = False
    for start, end, sym, cands, matched in spans:
        snippet = _window(text, start, end)
        direction, negated = _direction(snippet)
        negation_any |= negated
        key = sym or "?" + "|".join(cands)
        claim = by_symbol.get(key)
        if claim is None:
            original = matched.lstrip("#$").upper()
            claim = StockClaim(
                symbol=sym, company=company_name(sym.removeprefix("BSE:")) if sym else None, mentions=0,
                direction=direction, ambiguous=sym is None, candidates=cands, matched_text=matched,
                renamed_from=original if sym and original != sym and original in symbol_changes() else None,
            )
            by_symbol[key] = claim
        claim.mentions += 1
        claim.negated |= negated or bool(ANY_NEG_RE.search(snippet))
        if claim.direction != direction:
            pair = {claim.direction, direction} - {"unclear"}
            claim.direction = pair.pop() if len(pair) == 1 else ("mixed" if pair else "unclear")
        for p in _numbers(EXPECTED_RE, snippet):
            if p not in claim.expected_prices:
                claim.expected_prices.append(p)
        if claim.stop_loss is None:
            sl = _numbers(STOP_RE, snippet)
            claim.stop_loss = sl[0] if sl else None
        if claim.price_at_post is None:
            cmp_ = _numbers(CMP_RE, snippet)
            claim.price_at_post = cmp_[0] if cmp_ else None

    claims = sorted(by_symbol.values(), key=lambda c: (c.ambiguous, -c.mentions))
    pressure = {k: sorted({m.group(0).strip().lower() for m in r.finditer(text)}) for k, r in PRESSURE_RE.items()}
    pressure = {k: v for k, v in pressure.items() if v}
    return Extraction(
        claims=claims,
        pressure=pressure,
        percent_promises=sorted({int(m.group(1)) for m in PCT_RE.finditer(text)}),
        sebi_numbers=sorted({m.group(0).upper() for m in REGNO_RE.finditer(text)}),
        claims_sebi_registration=_claims_registration(text),
        negation_found=negation_any,
        words=len(text.split()),
        upi_ids=_upi_ids(text),
        disclaimers=sorted({re.sub(r"\s+", " ", m.group(0).strip().lower()) for m in DISCLAIMER_RE.finditer(text)}),
        says_not_registered=bool(NOT_REGISTERED_RE.search(text)),
    )
