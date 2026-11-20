"""Decision test: design, no outcome leaks to participants, answer rules and statistics."""

import datetime as dt
import json

import pytest
from fastapi.testclient import TestClient

from conftest import FakePrices, make_df
from finproof import api, config, study
from finproof.card import build_card
from finproof.ledger import Ledger, Tip

START = "2024-06-03"
BAD = {"T2", "T4"}


def stock(after_jump: float):
    """Flat at 100, then a step to `after_jump` from session 100 onwards."""
    return make_df([100.0] * 100 + [after_jump] * 300, volumes=[2_000_000.0] * 400, start=START)


def write_set(folder, tips):
    (folder / "tips_practice.json").write_text(json.dumps({"practice": True, "tips": tips}), encoding="utf-8")


@pytest.fixture
def env(tmp_path, monkeypatch):
    nifty = make_df([100.0] * 400, start=START)
    prices = FakePrices({config.BENCHMARK: nifty, "SBIN": stock(120), "ITC": stock(80),
                         "INFY": stock(115), "TCS": stock(85)})
    post = nifty.index[95].date().isoformat()
    write_set(tmp_path, [
        {"tip_id": tid, "platform": "telegram", "source_label": "Channel A", "posted_on": post,
         "symbol": sym, "direction": "up", "text": f"BUY {sym} now, sure shot", "provenance": "SYNTHETIC"}
        for tid, sym in (("T1", "SBIN"), ("T2", "ITC"), ("T3", "INFY"), ("T4", "TCS"))])
    monkeypatch.setenv("FINPROOF_STUDY_DIR", str(tmp_path))
    monkeypatch.setenv("FINPROOF_STUDY_SET", "practice")
    monkeypatch.delenv("FINPROOF_STUDY_KEY", raising=False)
    monkeypatch.setattr(api, "PRICES", prices)
    monkeypatch.setattr(api, "LEDGER", Ledger(prices, tips=[]))
    return TestClient(api.app), prices, tmp_path


def log_events(folder):
    path = folder / "responses" / "responses_practice.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def run_person(client, policy):
    plan = client.post("/api/study/start", json={}).json()
    for block in plan["blocks"]:
        for tip in block["tips"]:
            r = client.post("/api/study/answer", json={
                "participant_id": plan["participant_id"], "tip_id": tip["tip_id"],
                "answer": policy(block["condition"], tip["tip_id"]), "confidence": 2, "ms": 3000})
            assert r.status_code == 200
    client.post("/api/study/finish", json={"participant_id": plan["participant_id"]})
    return plan


def all_keys(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from all_keys(v)
    elif isinstance(node, list):
        for v in node:
            yield from all_keys(v)


def test_labels_come_from_prices_and_sets_are_balanced(env):
    _, prices, _ = env
    ts = study.load_test_set(prices)
    assert ts.problems == []
    assert {t.tip_id: t.label for t in ts.tips} == {"T1": "good", "T2": "bad", "T3": "good", "T4": "bad"}
    assert {t.tip_id: t.set for t in ts.tips} == {"T1": "X", "T2": "X", "T3": "Y", "T4": "Y"}


def test_groups_rotate_and_everyone_sees_both_conditions(env):
    client, _, folder = env
    plans = [client.post("/api/study/start", json={"background": {"invests": "sometimes", "name": "Asha"}}).json()
             for _ in range(4)]
    starts = [e for e in log_events(folder) if e["type"] == "start"]
    assert [s["group"] for s in starts] == [0, 1, 2, 3]
    assert [s["card_set"] for s in starts] == ["X", "X", "Y", "Y"]
    assert [s["card_first"] for s in starts] == [True, False, True, False]
    assert all(s["background"] == {"invests": "sometimes"} for s in starts)  # unknown fields are dropped
    for plan in plans:
        assert sorted(b["condition"] for b in plan["blocks"]) == ["card", "no_card"]
        for b in plan["blocks"]:
            assert all(("card" in t) == (b["condition"] == "card") for t in b["tips"])


def test_participants_never_see_outcomes(env):
    client, _, _ = env
    plan = client.post("/api/study/start", json={}).json()
    assert not set(all_keys(plan)) & {"label", "label_basis", "outcome", "after_post", "clear"}
    for block in plan["blocks"]:
        for tip in block["tips"]:
            assert "link" not in tip and "symbol" not in tip
            if "card" in tip:
                card = tip["card"]
                assert card["post"]["point_in_time"] is True
                assert all(c.get("market", {}).get("fall_after") is None for c in card["claims"])
                assert not any(w["code"] == "fell_after" for w in card["warnings"])


def test_point_in_time_track_record_uses_only_known_results(env):
    _, prices, _ = env
    idx = prices.frames[config.BENCHMARK].index
    as_of = idx[300].date()
    old = [Tip(f"o{i}", "s1", "Source 1", "SBIN", "up", idx[10 + i].date()) for i in range(10)]
    mid = [Tip("m0", "s1", "Source 1", "SBIN", "up", as_of - dt.timedelta(days=40))]
    new = [Tip(f"n{i}", "s1", "Source 1", "SBIN", "up", as_of - dt.timedelta(days=3 + i)) for i in range(3)]
    ledger = Ledger(prices, tips=old + mid + new)

    rec, _ = ledger.record("s1", as_of=as_of)
    assert rec.tips_total == 11  # the 3 tips from the last 30 days have no known result yet

    card = build_card(text="BUY SBIN", ledger=ledger, prices=prices, posted_on=as_of, posted_on_note="t",
                      source_key="s1", point_in_time=True)
    assert card["track_record"]["tips_total"] == 11
    assert "after_post" not in card["claims"][0]
    m0 = next(t for t in card["track_record"]["recent"] if t["tip_id"] == "m0")
    assert m0["horizons"]["30"]["status"] == "scored"
    assert m0["horizons"]["90"]["status"] == "pending"  # its 90-day result came after the post


def test_answer_rules(env):
    client, _, _ = env
    plan = client.post("/api/study/start", json={}).json()
    pid, tid = plan["participant_id"], plan["blocks"][0]["tips"][0]["tip_id"]

    def answer(**kw):
        body = {"participant_id": pid, "tip_id": tid, "answer": "yes", "confidence": 2, "ms": 1000, **kw}
        return client.post("/api/study/answer", json=body).status_code

    assert answer(participant_id="p-nobody") == 404
    assert answer(tip_id="T9") == 400
    assert answer(answer="maybe") == 400
    assert answer(confidence=6) == 400 and answer(confidence=0) == 400
    assert answer() == 200
    assert answer() == 409


def test_a_clear_effect_is_reported(env):
    client, _, _ = env
    # Without the card everyone acts on every tip; with it they skip the bad ones.
    for _ in range(8):
        run_person(client, lambda cond, tid: "no" if cond == "card" and tid in BAD else "yes")
    r = client.get("/api/study/results").json()
    assert r["completed"] == 8 and r["groups"] == {"0": 2, "1": 2, "2": 2, "3": 2}
    bad, good = r["metrics"]["bad_yes"], r["metrics"]["good_yes"]
    assert (bad["no_card"], bad["card"], bad["diff"]) == (1.0, 0.0, -1.0)
    assert bad["p"] < 0.01
    assert good["diff"] == 0.0
    assert r["criteria"]["h1"]["met"] is True and r["criteria"]["h2"]["met"] is True
    assert r["metrics"]["correct"]["card"] == 1.0
    assert "Small sample: 8 people" in " ".join(r["warnings"])


def test_no_effect_is_not_called_a_success(env):
    client, _, _ = env
    for _ in range(8):
        run_person(client, lambda cond, tid: "yes")
    r = client.get("/api/study/results").json()
    assert r["metrics"]["bad_yes"]["diff"] == 0.0
    assert r["metrics"]["bad_yes"]["p"] == 1.0
    assert r["criteria"]["h1"]["met"] is False


def test_unfinished_sessions_are_left_out(env):
    client, _, _ = env
    plan = client.post("/api/study/start", json={}).json()
    client.post("/api/study/answer", json={"participant_id": plan["participant_id"],
                                           "tip_id": plan["blocks"][0]["tips"][0]["tip_id"],
                                           "answer": "yes", "confidence": 1, "ms": 500})
    r = client.get("/api/study/results").json()
    assert (r["started"], r["completed"]) == (1, 0)
    assert r["headline"] == "No completed sessions yet."


def test_results_need_the_key_when_one_is_set(env, monkeypatch):
    client, _, _ = env
    monkeypatch.setenv("FINPROOF_STUDY_KEY", "abc")
    assert client.get("/api/study/results").status_code == 401
    assert client.get("/api/study/results", headers={"X-Study-Key": "abc"}).status_code == 200
    run_person(client, lambda cond, tid: "yes")
    csv_text = client.get("/api/study/export.csv", headers={"X-Study-Key": "abc"}).text
    lines = csv_text.strip().splitlines()
    assert lines[0].startswith("participant_id,") and len(lines) == 5  # header + 4 answers


def test_an_unbalanced_set_cannot_start(env):
    client, _, folder = env
    post = "2024-10-14"
    write_set(folder, [{"tip_id": f"T{i}", "symbol": "SBIN", "direction": "up", "posted_on": post,
                        "text": "BUY SBIN", "label": "good"} for i in range(4)])
    assert client.get("/api/study/info").json()["ready"] is False
    assert client.post("/api/study/start", json={}).status_code == 503


def test_permutation_and_bootstrap_basics():
    assert study.sign_flip_p([0.5]) is None
    assert study.sign_flip_p([0.0, 0.0, 0.0]) == 1.0
    assert study.bootstrap_ci([-1.0, -1.0, -1.0]) == [-1.0, -1.0]


def test_calibration_metric_and_preregistration_are_reported(tmp_path, monkeypatch):
    """Brier score of confidence (1-5) vs outcome, and the metrics' fixed-in-advance dates, on the results page."""
    from finproof import study as st
    assert st.CONFIDENCE == (1, 2, 3, 4, 5) and st.SMALL_SAMPLE == 30
    assert len(st.PREREGISTERED) == 3 and all(x["fixed"] for x in st.PREREGISTERED)
    assert "Calibration" in st.PREREGISTERED[2]["metric"]
