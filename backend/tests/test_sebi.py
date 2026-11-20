import pandas as pd

from finproof.sebi import Registry, check

REG = Registry(
    pd.DataFrame([
        {"name": "Asha Market Research Private Limited", "reg_no": "INH000000001", "category": "RA", "validity": ""},
        {"name": "Ravi Kumar", "reg_no": "INA000000002", "category": "IA", "validity": ""},
    ]),
    saved_on="2026-11-20",
    coverage={"RA": {"saved": 1, "listed": 2404}},
)


def test_registered_number():
    r = check(["inh000000001"], None, REG)
    assert r.status == "registered" and r.category == "Research Analyst"


def test_unknown_number_says_copy_is_incomplete():
    r = check(["INH999999999"], None, REG)
    assert r.status == "number_not_found"
    assert "incomplete" in r.text


def test_similar_name_without_number():
    r = check([], "Asha Market Research", REG)
    assert r.status == "name_match"


def test_nothing_to_check():
    assert check([], None, REG).status == "not_checked"


def test_facts_not_verdicts():
    for r in (check(["INH999999999"], None, REG), check([], "Nobody Here", REG)):
        assert "illegal" not in r.text.lower() and "fraud" not in r.text.lower()
