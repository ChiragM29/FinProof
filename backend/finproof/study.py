"""Decision test: does the FinProof card help people avoid bad tips without losing trust in good ones?

The design is fixed before any data is collected (see eval/README.md):
- A test set of past tips with known 30-day outcomes, split into sets X and Y that hold the
  same number of good and bad tips.
- Each participant sees one set with the FinProof card and the other set without it.
- Participants are assigned in turn to 4 groups: which set gets the card x whether the card
  block comes first. This balances tip difficulty and practice effects.
- Cards are point-in-time: they only use information available before the tip was posted.
- For each tip: "Would you act on this tip?" (yes/no) and how sure (1-3).

Answers go to an append-only JSON-lines log; every number in the results is recomputed
from that log, so anyone can check it.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import os
import random
import socket
import threading
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import config
from .card import build_card
from .ledger import Tip, score_tip

GROUPS = 4
CONDITIONS = ("no_card", "card")
LABEL_HORIZON = config.MAIN_HORIZON
CLEAR_MARGIN = 0.02      # outcomes this close to the Nifty are flagged as unclear
NON_INFERIORITY = 0.10   # H2: saying yes to good tips may not drop by more than 10 points
MIN_PEOPLE = 20
BACKGROUND_CHOICES = {
    "invests": {"regularly", "sometimes", "not_yet"},
    "sees_tips": {"daily", "weekly", "rarely", "never"},
}


class StudyError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def study_dir() -> Path:
    return Path(os.environ.get("FINPROOF_STUDY_DIR") or (config.ROOT / "eval" / "decision_test"))


def active_set_name() -> str:
    name = os.environ.get("FINPROOF_STUDY_SET")
    if name:
        return name
    return "real" if (study_dir() / "tips_real.json").exists() else "practice"


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


# ------------------------------------------------------------------ the test set

@dataclass
class TestTip:
    tip_id: str
    platform: str
    source_id: str
    source_label: str
    posted_on: dt.date
    symbol: str
    direction: str
    title: str
    text: str
    provenance: str
    link: str = ""
    label: str | None = None        # good | bad
    label_basis: str = ""
    outcome: float | None = None    # stock minus Nifty over 30 days, in the claimed direction
    clear: bool = True
    set: str | None = None          # X | Y

    def public(self) -> dict:
        """Only what a participant may see: no label, outcome, set, symbol field or link."""
        return {"tip_id": self.tip_id, "platform": self.platform, "source_label": self.source_label,
                "posted_on": self.posted_on.isoformat(), "title": self.title, "text": self.text}


@dataclass
class TestSet:
    name: str
    path: Path
    tips: list[TestTip]
    digest: str
    practice: bool
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def tip(self, tip_id: str) -> TestTip | None:
        return next((t for t in self.tips if t.tip_id == tip_id), None)


def load_test_set(prices, name: str | None = None) -> TestSet:
    name = name or active_set_name()
    path = study_dir() / f"tips_{name}.json"
    if not path.exists():
        return TestSet(name, path, [], "", name != "real", [f"Test set file {path.name} was not found."])
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    tips: list[TestTip] = []
    problems: list[str] = []
    notes: list[str] = []
    for row in data.get("tips", []):
        try:
            t = TestTip(
                tip_id=str(row["tip_id"]), platform=str(row.get("platform") or "other").lower(),
                source_id=row.get("source_id") or "", source_label=row.get("source_label") or "Unknown source",
                posted_on=dt.date.fromisoformat(row["posted_on"]), symbol=str(row["symbol"]).upper(),
                direction=str(row["direction"]).lower(), title=row.get("title") or "", text=row["text"],
                provenance=str(row.get("provenance") or "REAL").upper(), link=row.get("link") or "",
                set=row.get("set"),
            )
        except (KeyError, ValueError, TypeError) as exc:
            problems.append(f"Tip {row.get('tip_id', '?')}: a field is missing or wrong ({exc}).")
            continue
        if t.direction not in ("up", "down"):
            problems.append(f"Tip {t.tip_id}: direction must be up or down.")
            continue
        h = score_tip(Tip(t.tip_id, t.source_id or "test", t.source_label, t.symbol, t.direction, t.posted_on),
                      prices).horizons.get(LABEL_HORIZON)
        if h is not None and h.status == "scored":
            t.outcome = h.excess_return if t.direction == "up" else -h.excess_return
            t.clear = abs(h.excess_return) >= CLEAR_MARGIN
        if row.get("label") in ("good", "bad"):
            t.label, t.label_basis = row["label"], row.get("label_basis") or "set by hand"
        elif t.outcome is not None:
            t.label = "good" if t.outcome > 0 else "bad"
            t.label_basis = f"{LABEL_HORIZON}-day result against the Nifty 50, in the claimed direction: {t.outcome:+.1%}"
            if not t.clear:
                notes.append(f"Tip {t.tip_id}: the result is within {CLEAR_MARGIN:.0%} of the Nifty, "
                             "so its label is close to a coin flip. Consider a clearer tip.")
        else:
            problems.append(f"Tip {t.tip_id}: no {LABEL_HORIZON}-day price result, so it has no label.")
        tips.append(t)

    seen: set[str] = set()
    for t in tips:
        if t.tip_id in seen:
            problems.append(f"Tip id {t.tip_id} is used twice.")
        seen.add(t.tip_id)
    _assign_sets(tips, problems)
    return TestSet(name, path, tips, hashlib.sha256(raw).hexdigest()[:12],
                   bool(data.get("practice", name != "real")), problems, notes)


def _assign_sets(tips: list[TestTip], problems: list[str]) -> None:
    """Use the sets given in the file, or split each label alternately into X and Y."""
    if not (tips and all(t.set in ("X", "Y") for t in tips)):
        for label in ("good", "bad"):
            for i, t in enumerate(sorted((t for t in tips if t.label == label), key=lambda t: t.tip_id)):
                t.set = "XY"[i % 2]
    if not any(t.label == "good" for t in tips) or not any(t.label == "bad" for t in tips):
        problems.append("The test needs both good and bad tips.")
    for label in ("good", "bad"):
        x = sum(1 for t in tips if t.set == "X" and t.label == label)
        y = sum(1 for t in tips if t.set == "Y" and t.label == label)
        if x != y:
            problems.append(f"Sets X and Y need the same number of {label} tips (X has {x}, Y has {y}).")


_sets: dict[tuple, TestSet] = {}
_cards: dict[tuple, dict] = {}


def current_set(prices) -> TestSet:
    name = active_set_name()
    path = study_dir() / f"tips_{name}.json"
    key = (str(path), path.stat().st_mtime if path.exists() else 0.0, id(prices))
    if key not in _sets:
        _sets.clear()
        _sets[key] = load_test_set(prices, name)
    return _sets[key]


def card_for(tip: TestTip, test_set: TestSet, ledger, prices) -> dict:
    key = (test_set.digest, tip.tip_id, id(ledger), id(prices))
    if key not in _cards:
        text = "\n".join(x for x in (tip.title, tip.text) if x)
        card = build_card(text=text, ledger=ledger, prices=prices, posted_on=tip.posted_on,
                          posted_on_note="date the tip was posted",
                          kind="youtube" if tip.platform == "youtube" else "text",
                          title=tip.title or None, source_key=tip.source_id or None, point_in_time=True)
        card["sebi"]["registered_name"] = None  # sources stay anonymous in the test
        _cards[key] = card
    return _cards[key]


# ------------------------------------------------------------------ the answer log

class StudyLog:
    _instances: dict[str, "StudyLog"] = {}
    _guard = threading.Lock()

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()

    @classmethod
    def for_set(cls, test_set: TestSet) -> "StudyLog":
        path = study_dir() / "responses" / f"responses_{test_set.name}.jsonl"
        with cls._guard:
            if str(path) not in cls._instances:
                cls._instances[str(path)] = cls(path)
            return cls._instances[str(path)]

    def events(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out

    def append(self, event: dict) -> None:
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")


def start_session(test_set: TestSet, background: dict | None) -> dict:
    if test_set.problems:
        raise StudyError(503, "The test set is not ready: " + " ".join(test_set.problems))
    clean = {k: v for k, v in (background or {}).items()
             if k in BACKGROUND_CHOICES and v in BACKGROUND_CHOICES[k]}
    log = StudyLog.for_set(test_set)
    with log.lock:
        group = sum(1 for e in log.events() if e.get("type") == "start") % GROUPS
        pid = "p-" + uuid.uuid4().hex[:10]
        card_set = "X" if group in (0, 1) else "Y"
        card_first = group in (0, 2)
        rng = random.Random(pid)
        blocks = []
        for cond in (("card", "no_card") if card_first else ("no_card", "card")):
            which = card_set if cond == "card" else ("Y" if card_set == "X" else "X")
            ids = sorted(t.tip_id for t in test_set.tips if t.set == which)
            rng.shuffle(ids)
            blocks.append({"condition": cond, "tip_ids": ids})
        event = {"type": "start", "participant_id": pid, "at": _now(), "set": test_set.name,
                 "set_digest": test_set.digest, "group": group, "card_set": card_set,
                 "card_first": card_first, "blocks": blocks, "background": clean}
        log.append(event)
    return event


def plan_payload(event: dict, test_set: TestSet, ledger, prices) -> dict:
    blocks = []
    for b in event["blocks"]:
        tips = []
        for tid in b["tip_ids"]:
            tip = test_set.tip(tid)
            item = tip.public()
            if b["condition"] == "card":
                item["card"] = card_for(tip, test_set, ledger, prices)
            tips.append(item)
        blocks.append({"condition": b["condition"], "tips": tips})
    return {"participant_id": event["participant_id"], "practice": test_set.practice,
            "total": sum(len(b["tips"]) for b in blocks), "blocks": blocks}


def _start_event(events: list[dict], pid: str) -> dict:
    start = next((e for e in events if e.get("type") == "start" and e.get("participant_id") == pid), None)
    if start is None:
        raise StudyError(404, "Unknown participant.")
    return start


def record_answer(test_set: TestSet, pid: str, tip_id: str, answer: str, confidence: int, ms: int) -> None:
    if answer not in ("yes", "no"):
        raise StudyError(400, "The answer must be yes or no.")
    if confidence not in (1, 2, 3):
        raise StudyError(400, "Confidence must be 1, 2 or 3.")
    log = StudyLog.for_set(test_set)
    with log.lock:
        events = log.events()
        start = _start_event(events, pid)
        where = {tid: (i, b["condition"]) for i, b in enumerate(start["blocks"]) for tid in b["tip_ids"]}
        if tip_id not in where:
            raise StudyError(400, "This tip is not part of your test.")
        if any(e.get("type") == "answer" and e.get("participant_id") == pid and e.get("tip_id") == tip_id
               for e in events):
            raise StudyError(409, "This tip was already answered.")
        block, cond = where[tip_id]
        log.append({"type": "answer", "participant_id": pid, "tip_id": tip_id, "block": block,
                    "condition": cond, "answer": answer, "confidence": confidence,
                    "ms": max(0, min(int(ms), 600_000)), "at": _now()})


def finish_session(test_set: TestSet, pid: str) -> None:
    log = StudyLog.for_set(test_set)
    with log.lock:
        _start_event(log.events(), pid)
        log.append({"type": "finish", "participant_id": pid, "at": _now()})


# ------------------------------------------------------------------ analysis

def _rate(values: list[bool]) -> float | None:
    return sum(values) / len(values) if values else None


def participant_rows(test_set: TestSet, events: list[dict]) -> list[dict]:
    labels = {t.tip_id: t.label for t in test_set.tips}
    starts: dict[str, dict] = {}
    answers: dict[str, dict[str, dict]] = defaultdict(dict)
    for e in events:
        if e.get("type") == "start" and e.get("participant_id") not in starts:
            starts[e["participant_id"]] = e
    for e in events:
        if e.get("type") == "answer" and e.get("participant_id") in starts:
            answers[e["participant_id"]].setdefault(e["tip_id"], e)

    rows = []
    for pid, s in starts.items():
        got = answers[pid]
        planned = [tid for b in s["blocks"] for tid in b["tip_ids"]]
        row = {"participant_id": pid, "group": s["group"], "card_first": s["card_first"],
               "first_condition": s["blocks"][0]["condition"], "complete": all(t in got for t in planned),
               "set_digest": s.get("set_digest"), "background": s.get("background", {})}
        for cond in CONDITIONS:
            ans = [got[t] for b in s["blocks"] if b["condition"] == cond for t in b["tip_ids"] if t in got]
            bad = [a["answer"] == "yes" for a in ans if labels.get(a["tip_id"]) == "bad"]
            good = [a["answer"] == "yes" for a in ans if labels.get(a["tip_id"]) == "good"]
            right = [(a["answer"] == "yes") == (labels[a["tip_id"]] == "good") for a in ans if labels.get(a["tip_id"])]
            row[f"bad_yes_{cond}"] = _rate(bad)
            row[f"good_yes_{cond}"] = _rate(good)
            row[f"correct_{cond}"] = _rate(right)
            g, b_ = row[f"good_yes_{cond}"], row[f"bad_yes_{cond}"]
            row[f"gap_{cond}"] = None if g is None or b_ is None else g - b_
            row[f"ms_{cond}"] = [a["ms"] for a in ans]
        rows.append(row)
    return rows


def bootstrap_ci(values, n_boot: int = 10_000, seed: int = 0) -> list[float] | None:
    arr = np.asarray(values, dtype=float)
    if len(arr) < 2:
        return None
    rng = np.random.default_rng(seed)
    means = arr[rng.integers(0, len(arr), size=(n_boot, len(arr)))].mean(axis=1)
    return [round(float(np.percentile(means, 2.5)), 4), round(float(np.percentile(means, 97.5)), 4)]


def sign_flip_p(diffs, n_perm: int = 20_000, seed: int = 0) -> float | None:
    """Two-sided paired permutation test: flip the sign of each person's difference."""
    arr = np.asarray(diffs, dtype=float)
    n = len(arr)
    if n < 2:
        return None
    observed = abs(arr.mean())
    if n <= 16:
        signs = ((np.arange(2 ** n)[:, None] >> np.arange(n)) & 1) * 2 - 1
    else:
        signs = np.random.default_rng(seed).choice([-1, 1], size=(n_perm, n))
    flipped = np.abs((signs * arr).mean(axis=1))
    return round(float((flipped >= observed - 1e-12).mean()), 4)


def _paired(rows: list[dict], metric: str) -> dict:
    pairs = [(r[f"{metric}_no_card"], r[f"{metric}_card"]) for r in rows
             if r[f"{metric}_no_card"] is not None and r[f"{metric}_card"] is not None]
    if not pairs:
        return {"n": 0, "no_card": None, "card": None, "diff": None, "ci": None, "p": None}
    a = np.asarray(pairs, dtype=float)
    diffs = a[:, 1] - a[:, 0]
    return {"n": len(pairs), "no_card": round(float(a[:, 0].mean()), 4), "card": round(float(a[:, 1].mean()), 4),
            "diff": round(float(diffs.mean()), 4), "ci": bootstrap_ci(diffs), "p": sign_flip_p(diffs)}


def _between(rows: list[dict], metric: str, n_boot: int = 10_000, seed: int = 0) -> dict:
    """First block only: people who saw cards first vs people who saw no cards first."""
    no = np.asarray([r[f"{metric}_no_card"] for r in rows
                     if r["first_condition"] == "no_card" and r[f"{metric}_no_card"] is not None], dtype=float)
    yes = np.asarray([r[f"{metric}_card"] for r in rows
                      if r["first_condition"] == "card" and r[f"{metric}_card"] is not None], dtype=float)
    out = {"n_no_card": len(no), "n_card": len(yes), "no_card": None, "card": None, "diff": None, "ci": None, "p": None}
    if len(no):
        out["no_card"] = round(float(no.mean()), 4)
    if len(yes):
        out["card"] = round(float(yes.mean()), 4)
    if len(no) == 0 or len(yes) == 0:
        return out
    out["diff"] = round(float(yes.mean() - no.mean()), 4)
    if len(no) >= 2 and len(yes) >= 2:
        rng = np.random.default_rng(seed)
        boot = (yes[rng.integers(0, len(yes), size=(n_boot, len(yes)))].mean(axis=1)
                - no[rng.integers(0, len(no), size=(n_boot, len(no)))].mean(axis=1))
        out["ci"] = [round(float(np.percentile(boot, 2.5)), 4), round(float(np.percentile(boot, 97.5)), 4)]
        pooled = np.concatenate([yes, no])
        observed = abs(out["diff"])
        perm = np.array([rng.permutation(pooled) for _ in range(5000)])
        perm_diff = np.abs(perm[:, :len(yes)].mean(axis=1) - perm[:, len(yes):].mean(axis=1))
        out["p"] = round(float((perm_diff >= observed - 1e-12).mean()), 4)
    return out


def _pct(x: float | None) -> str:
    return "–" if x is None else f"{x * 100:.0f}%"


def _pts(x: float) -> str:
    return f"{x * 100:+.0f}"


def results(test_set: TestSet) -> dict:
    events = StudyLog.for_set(test_set).events()
    rows = participant_rows(test_set, events)
    done = [r for r in rows if r["complete"]]
    metrics = {m: _paired(done, m) for m in ("bad_yes", "good_yes", "correct", "gap")}
    bad, good = metrics["bad_yes"], metrics["good_yes"]

    h1 = None if bad["ci"] is None else bool(bad["ci"][1] < 0)
    h2 = None if good["ci"] is None else bool(good["ci"][0] > -NON_INFERIORITY)
    if not done:
        headline = "No completed sessions yet."
    else:
        headline = (f"With the FinProof card, people said they would act on {_pct(bad['card'])} of bad tips, "
                    f"compared with {_pct(bad['no_card'])} without it")
        if bad["ci"]:
            headline += (f" ({_pts(bad['diff'])} points, 95% CI {_pts(bad['ci'][0])} to {_pts(bad['ci'][1])})")
        headline += (f". For good tips: {_pct(good['card'])} with the card, {_pct(good['no_card'])} without. "
                     f"{len(done)} {'person' if len(done) == 1 else 'people'} finished the test.")

    done_ids = {r["participant_id"] for r in done}
    first_answer: dict[tuple[str, str], dict] = {}
    for e in events:
        if e.get("type") == "answer" and e.get("participant_id") in done_ids:
            first_answer.setdefault((e["participant_id"], e["tip_id"]), e)
    per_tip = []
    for t in test_set.tips:
        cell = {"card": [], "no_card": []}
        for (pid, tid), e in first_answer.items():
            if tid == t.tip_id:
                cell[e["condition"]].append(e["answer"] == "yes")
        per_tip.append({"tip_id": t.tip_id, "set": t.set, "label": t.label, "outcome": t.outcome,
                        "clear": t.clear, "yes_card": _rate(cell["card"]), "n_card": len(cell["card"]),
                        "yes_no_card": _rate(cell["no_card"]), "n_no_card": len(cell["no_card"])})

    def median_seconds(cond: str) -> float | None:
        ms = [m for r in done for m in r[f"ms_{cond}"]]
        return round(float(np.median(ms)) / 1000, 1) if ms else None

    warnings = list(test_set.problems)
    if test_set.practice:
        warnings.append("Practice set with made-up tips: these answers are not evidence.")
    if 0 < len(done) < MIN_PEOPLE:
        who = "person" if len(done) == 1 else "people"
        warnings.append(f"Only {len(done)} {who} so far; we planned at least {MIN_PEOPLE}. Treat this as a pilot.")
    if any(r["set_digest"] != test_set.digest for r in rows):
        warnings.append("Some sessions were run with a different version of the tip set.")

    groups = {str(g): sum(1 for r in done if r["group"] == g) for g in range(GROUPS)}
    log_path = StudyLog.for_set(test_set).path
    return {
        "set": test_set.name, "practice": test_set.practice, "digest": test_set.digest,
        "log_file": str(log_path.relative_to(config.ROOT)) if log_path.is_relative_to(config.ROOT) else str(log_path),
        "started": len(rows), "completed": len(done), "groups": groups,
        "headline": headline, "metrics": metrics,
        "first_block": {m: _between(done, m) for m in ("bad_yes", "good_yes")},
        "criteria": {
            "h1": {"met": h1, "text": "With the card, people act on fewer bad tips "
                                      "(the 95% CI of the difference is below zero)."},
            "h2": {"met": h2, "text": f"With the card, saying yes to good tips does not drop by more than "
                                      f"{NON_INFERIORITY * 100:.0f} points (lower end of the 95% CI above "
                                      f"-{NON_INFERIORITY * 100:.0f})."},
        },
        "seconds_per_tip": {c: median_seconds(c) for c in CONDITIONS},
        "per_tip": per_tip, "warnings": warnings, "notes": test_set.notes,
    }


def export_csv(test_set: TestSet) -> str:
    events = StudyLog.for_set(test_set).events()
    rows = {r["participant_id"]: r for r in participant_rows(test_set, events)}
    labels = {t.tip_id: t.label for t in test_set.tips}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["participant_id", "group", "card_first", "complete", "invests", "sees_tips", "block",
                "condition", "tip_id", "label", "answer", "confidence", "ms", "at"])
    for e in events:
        if e.get("type") != "answer" or e.get("participant_id") not in rows:
            continue
        r = rows[e["participant_id"]]
        w.writerow([e["participant_id"], r["group"], r["card_first"], r["complete"],
                    r["background"].get("invests", ""), r["background"].get("sees_tips", ""),
                    e["block"], e["condition"], e["tip_id"], labels.get(e["tip_id"], ""),
                    e["answer"], e["confidence"], e["ms"], e["at"]])
    return buf.getvalue()


def lan_urls(port: int) -> list[str]:
    """Addresses phones on the same Wi-Fi can open (the server must listen on 0.0.0.0)."""
    ips: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    try:  # finds the address of the main network card; a UDP connect sends no packets
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    return [f"http://{ip}:{port}/study.html" for ip in sorted(ips) if not ip.startswith(("127.", "169.254."))]
