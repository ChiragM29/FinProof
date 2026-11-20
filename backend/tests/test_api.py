import datetime as dt

import pytest
from fastapi.testclient import TestClient

from conftest import FakePrices, make_df
from finproof import api, config
from finproof.ledger import Ledger, Tip


@pytest.fixture
def client(monkeypatch):
    nifty = make_df([100.0] * 400, start="2024-06-03")
    stock = make_df([100.0 + i * 0.1 for i in range(400)], volumes=[2_000_000.0] * 400, start="2024-06-03")
    prices = FakePrices({config.BENCHMARK: nifty, "SBIN": stock})
    tips = [Tip(f"t{i}", "demo", "Demo Source", "SBIN", "up", dt.date(2024, 9, 2) + dt.timedelta(days=7 * i),
                provenance="SYNTHETIC") for i in range(12)]
    monkeypatch.setattr(api, "PRICES", prices)
    monkeypatch.setattr(api, "LEDGER", Ledger(prices, tips=tips))
    return TestClient(api.app)


def test_health(client):
    assert client.get("/api/health").json()["ok"] is True


def test_analyze_text(client):
    r = client.post("/api/analyze", json={"text": "BUY SBIN TGT 200, sure shot", "posted_on": "2024-10-01",
                                          "source": "Demo Source"})
    assert r.status_code == 200
    card = r.json()
    assert card["claims"][0]["symbol"] == "SBIN"
    assert card["track_record"]["status"] == "ok"
    assert card["track_record"]["provenance"] == "SYNTHETIC"
    assert any(p["provenance"] == "SYNTHETIC" for p in card["data_provenance"])


def test_empty_request_is_rejected(client):
    assert client.post("/api/analyze", json={}).status_code == 400


def test_sources(client):
    rows = client.get("/api/sources").json()
    assert rows[0]["source_id"] == "demo" and rows[0]["enough_history"] is True
    detail = client.get("/api/sources/demo").json()
    assert len(detail["tips"]) == 12
