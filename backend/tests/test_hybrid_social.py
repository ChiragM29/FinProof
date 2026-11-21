"""Hybrid mode (online first, cache fallback), Instagram and X links, and media/impersonation cues.
No test touches the real network: probes and HTTP calls are replaced with fakes."""

import datetime as dt
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import FakePrices, make_df
from finproof import api, auditor, config, media, net, social, veteran, youtube
from finproof.ai import SIGNAL_RE
from finproof.card import ADVICE_RE, build_card, wording_problems
from finproof.ledger import Ledger
from finproof.veteran import EXTRA_RE, build_veteran_brief, veteran_problems

N = 400


@pytest.fixture(autouse=True)
def hybrid_mode(monkeypatch):
    """These tests are about the default hybrid mode, even when the suite runs with FINPROOF_OFFLINE=1."""
    monkeypatch.setattr(config, 'OFFLINE', False)


@pytest.fixture
def client(monkeypatch, tmp_path):
    frame = make_df([100.0 + (i % 11) for i in range(N)], volumes=[2_000_000.0] * N, start="2024-06-03")
    prices = FakePrices({config.BENCHMARK: make_df([100.0] * N, start="2024-06-03"), "ITC": frame, "SBIN": frame,
                         "RELIANCE": frame})
    monkeypatch.setattr(api, "PRICES", prices)
    monkeypatch.setattr(api, "LEDGER", Ledger(prices, tips=[]))
    monkeypatch.setattr(youtube, "YT_CACHE", tmp_path / "yt")
    monkeypatch.setattr(social, "SOCIAL_CACHE", tmp_path / "social")
    return TestClient(api.app)


def online(monkeypatch, up=True):
    monkeypatch.setattr(net, "_probe", lambda: up)
    monkeypatch.setattr(net, "_last", {"at": 0.0, "ok": False})


def clean(texts):
    for t in texts:
        for rx in (ADVICE_RE, EXTRA_RE, SIGNAL_RE):
            assert not rx.search(t), t


# ---------------------------------------------------------------- hybrid status
def test_header_status_is_hybrid_live_or_cache(client, monkeypatch):
    assert client.get("/api/health").json()["network"]["label"] == "HYBRID · CACHE"
    online(monkeypatch)
    net_status = client.get("/api/health").json()["network"]
    assert net_status == {"mode": "hybrid", "live": True, "label": "HYBRID · LIVE", "offline_forced": False}
    monkeypatch.setattr(config, "OFFLINE", True)  # forced offline always means cache
    assert net.status()["label"] == "HYBRID · CACHE" and net.status()["offline_forced"] is True


# ---------------------------------------------------------------- YouTube: online first, cache fallback
VIDEO = {"video_id": "abcdefghijk", "title": "ITC breakout?", "channel": "Market Guru", "channel_id": None,
         "published_on": "2025-06-01", "published_at": "2025-06-01T22:30:00-07:00", "description": "",
         "transcript": "BUY ITC now, target 120", "transcript_language": "en", "transcript_error": None}


def test_youtube_fetches_live_when_online_and_caches_it(client, monkeypatch):
    online(monkeypatch)
    calls = []
    monkeypatch.setattr(youtube, "_fetch_live", lambda vid: calls.append(vid) or dict(VIDEO))
    card = client.post("/api/analyze", json={"url": "https://www.youtube.com/watch?v=abcdefghijk"}).json()
    assert calls == ["abcdefghijk"] and card["post"]["from_cache"] is False
    assert card["detected"]["platform"] == "YouTube" and card["detected"]["tickers"] == ["ITC"]
    assert json.loads((youtube.YT_CACHE / "abcdefghijk.json").read_text(encoding="utf-8"))["title"] == "ITC breakout?"


def test_a_lone_link_typed_in_the_text_box_is_treated_as_a_link(client, monkeypatch):
    online(monkeypatch)
    monkeypatch.setattr(youtube, "_fetch_live", lambda vid: dict(VIDEO))
    card = client.post("/api/analyze", json={"text": "https://youtu.be/abcdefghijk"}).json()
    assert card["post"]["kind"] == "youtube"


def test_youtube_falls_back_to_the_cache_when_the_network_drops(client, monkeypatch):
    youtube.YT_CACHE.mkdir(parents=True)
    (youtube.YT_CACHE / "abcdefghijk.json").write_text(json.dumps(VIDEO), encoding="utf-8")
    online(monkeypatch)

    def down(_):
        raise httpx.ConnectError("no route")
    monkeypatch.setattr(youtube, "_fetch_live", down)
    card = client.post("/api/analyze", json={"url": "https://youtu.be/abcdefghijk"}).json()
    assert card["post"]["from_cache"] is True and card["detected"]["source"] == "Market Guru"
    assert net.status()["label"] == "HYBRID · CACHE"  # the failure switched the header to cache


def test_unreachable_uncached_video_asks_for_the_text_instead_of_failing(client, monkeypatch):
    monkeypatch.setattr(config, "OFFLINE", True)
    r = client.post("/api/analyze", json={"url": "https://youtu.be/zzzzzzzzzzz"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "restricted" and body["platform"] == "youtube" and "paste" in body["message"]
    card = client.post("/api/analyze", json={"url": "https://youtu.be/zzzzzzzzzzz", "text": "BUY SBIN CMP 100 TGT 130"}).json()
    assert card["post"]["kind"] == "youtube" and card["post"]["link"].endswith("zzzzzzzzzzz")


def test_forced_offline_never_calls_the_network(monkeypatch, tmp_path):
    monkeypatch.setattr(youtube, "YT_CACHE", tmp_path)
    online(monkeypatch)
    monkeypatch.setattr(youtube, "_fetch_live", lambda vid: pytest.fail("network used in offline mode"))
    with pytest.raises(youtube.VideoUnavailable):
        youtube.fetch_video("abcdefghijk", offline=True)


# ---------------------------------------------------------------- Instagram and X links
@pytest.mark.parametrize("url,platform,pid,handle", [
    ("https://x.com/StockGuru/status/1931000000000000123", "x", "1931000000000000123", "StockGuru"),
    ("https://twitter.com/StockGuru/status/1931000000000000123?s=20", "x", "1931000000000000123", "StockGuru"),
    ("https://mobile.twitter.com/a_b/statuses/12345678", "x", "12345678", "a_b"),
    ("https://www.instagram.com/p/C8xYz12AbCd/", "instagram", "C8xYz12AbCd", None),
    ("https://www.instagram.com/reel/C8xYz12AbCd/?igsh=abc", "instagram", "C8xYz12AbCd", None),
    ("https://instagram.com/trading.guru/reel/C8xYz12AbCd", "instagram", "C8xYz12AbCd", "trading.guru"),
    ("https://youtu.be/abcdefghijk", "youtube", None, None),
    ("https://example.com/tips/123", "web", None, None),
])
def test_links_are_tagged_with_their_platform(url, platform, pid, handle):
    link = social.detect(url)
    assert (link["platform"], link["id"], link["handle"]) == (platform, pid, handle)


def test_plain_text_is_not_a_link():
    assert social.detect("BUY ITC https://x.com/a/status/12345678 now") is None and social.detect(None) is None


def fake_get(status=200, text="", url="https://x.com", payload=None):
    def get(u, **_):
        return SimpleNamespace(status_code=status, text=text, url=url, json=lambda: payload)
    return get


OEMBED = {"author_name": "Fin Hype Calls", "author_url": "https://twitter.com/FinHypeCalls",
          "html": '<blockquote class="twitter-tweet"><p lang="en" dir="ltr">BUY ITC CMP 100 TGT 130 &amp; join free '
                  'Telegram VIP group, link in bio <a href="https://t.co/x">pic.twitter.com/x</a></p>&mdash; Fin Hype '
                  'Calls (@FinHypeCalls) <a href="https://twitter.com/FinHypeCalls/status/1?ref_src=x">June 2, 2025</a>'
                  '</blockquote>'}


def test_x_post_is_fetched_online_through_oembed(client, monkeypatch):
    online(monkeypatch)
    monkeypatch.setattr(social, "_get", fake_get(payload=OEMBED))
    card = client.post("/api/analyze", json={"url": "https://x.com/FinHypeCalls/status/1931000000000000123"}).json()
    d = card["detected"]
    assert d["platform"] == "X (Twitter)" and d["posted_on"] == "2025-06-02" and d["tickers"] == ["ITC"]
    assert d["source"] == "Fin Hype Calls (@FinHypeCalls)" and card["post"]["kind"] == "x"
    assert {"funnel", "missing_context"} <= {w["code"] for w in card["warnings"]}
    assert card["post"]["provenance"] == "REAL"


@pytest.mark.parametrize("fake", [
    fake_get(status=200, text="<html>login</html>", url="https://www.instagram.com/accounts/login/?next=/p/x"),
    fake_get(status=429, text=""),
    fake_get(status=200, text="<html><head></head></html>", url="https://www.instagram.com/p/C8xYz12AbCd/"),
])
def test_instagram_login_wall_gives_a_paste_prompt_not_an_error(client, monkeypatch, fake):
    online(monkeypatch)
    monkeypatch.setattr(social, "_get", fake)
    r = client.post("/api/analyze", json={"url": "https://www.instagram.com/reel/C8xYz12AbCd/"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "restricted" and body["platform"] == "instagram" and body["platform_label"] == "Instagram"
    assert body["message"] == "Instagram needs a login to read this post; paste the caption"
    assert body["url"] == "https://www.instagram.com/reel/C8xYz12AbCd/"


def test_timeouts_also_fall_back_quietly(client, monkeypatch):
    online(monkeypatch)

    def slow(*_, **__):
        raise httpx.ConnectTimeout("4 s")
    monkeypatch.setattr(social, "_get", slow)
    body = client.post("/api/analyze", json={"url": "https://x.com/a/status/12345678"}).json()
    assert body["status"] == "restricted" and "ConnectTimeout" in body["reason"]
    assert net.status()["live"] is False


def test_pasted_caption_audits_the_post_with_the_platform_kept(client):
    card = client.post("/api/analyze", json={"url": "https://www.instagram.com/trading.guru/reel/C8xYz12AbCd/",
                                             "text": "SBIN CMP 790 target 900. Link in bio."}).json()
    assert card["post"]["kind"] == "instagram" and card["detected"]["platform"] == "Instagram"
    assert card["detected"]["source"] == "@trading.guru" and card["post"]["link"].endswith("C8xYz12AbCd/")


def test_unsupported_links_ask_for_the_post_text(client):
    body = client.post("/api/analyze", json={"url": "https://example.com/tip"}).json()
    assert body["status"] == "restricted" and body["platform"] == "web"


def test_demo_posts_work_with_no_network(client):
    for post in social.DEMO_POSTS.values():
        card = client.post("/api/analyze", json={"url": post["url"]}).json()
        assert card["post"]["provenance"] == "SYNTHETIC" and card["post"]["from_cache"] is True
        codes = {w["code"] for w in card["warnings"]}
        assert {"impersonation", "funnel"} <= codes, codes
        assert card["media"]["title"] == "Media & Impersonation Flags"
        rows = {r["code"]: r["provenance"] for r in card["veteran"]["raw"]}
        assert rows["impersonation"] == rows["funnel"] == "SYNTHETIC"


def test_warm_cache_writes_both_demo_posts(monkeypatch, tmp_path):
    monkeypatch.setattr(social, "SOCIAL_CACHE", tmp_path)
    urls = social.write_demo_cache()
    assert len(urls) == 2 and len(list(tmp_path.glob("*.json"))) == 2
    assert all(json.loads(p.read_text(encoding="utf-8"))["provenance"] == "SYNTHETIC" for p in tmp_path.glob("*.json"))


# ---------------------------------------------------------------- media & impersonation cues
def card_for(text, kind="text"):
    frame = make_df([100.0] * N, volumes=[2_000_000.0] * N, start="2024-06-03")
    prices = FakePrices({config.BENCHMARK: frame, "SBIN": frame, "RELIANCE": frame, "ITC": frame})
    return build_card(text=text, ledger=Ledger(prices, tips=[]), prices=prices, posted_on=dt.date(2025, 6, 2),
                      posted_on_note="t", kind=kind)


@pytest.mark.parametrize("text,cue", [
    ("Leaked interview: Mukesh Ambani backs RELIANCE", "mukesh ambani"),
    ("Ratan Tata's secret pick: ITC", "ratan tata"),
    ("SEBI chairman confirms this SBIN call", "sebi chairman"),
    ("RBI approved trading plan for SBIN", "rbi approved"),
    ("Our AI auto-trading bot picked ITC", "ai auto-trading bot"),
])
def test_impersonation_cues(text, cue):
    card = card_for(text)
    w = next(w for w in card["warnings"] if w["code"] == "impersonation")
    assert cue in w["evidence"] and "cannot verify the clip" in w["text"]


def test_group_names_alone_are_not_impersonation():
    assert "impersonation" not in {w["code"] for w in card_for("Adani stocks are falling, Tata group too")["warnings"]}


@pytest.mark.parametrize("text", ["ITC call, link in bio", "DM for guaranteed calls on SBIN", "Join our free Telegram VIP group",
                                  "100% accuracy, daily fixed profit"])
def test_funnel_cues(text):
    assert "funnel" in {w["code"] for w in card_for(text)["warnings"]}


def test_missing_context_only_on_video_and_social_calls():
    call = "SBIN CMP 100 target 130"
    assert "missing_context" in {w["code"] for w in card_for(call, "instagram")["warnings"]}
    assert "missing_context" in {w["code"] for w in card_for(call, "youtube")["warnings"]}
    assert "missing_context" not in {w["code"] for w in card_for(call, "text")["warnings"]}             # a forward
    assert "missing_context" not in {w["code"] for w in card_for(call + ", stop loss 92", "x")["warnings"]}  # risk named
    assert "missing_context" not in {w["code"] for w in card_for(call + " INH000012345", "x")["warnings"]}  # reg. number


def test_media_cues_reach_the_desk_note_and_the_auditor():
    card = card_for(social.DEMO_POSTS["x_1931000000000000001"]["text"], "x")
    brief = build_veteran_brief(card)
    titles = {x["code"]: x["title"] for x in brief["wrong"]}
    assert titles["impersonation"] == "A famous name used as bait" and "funnel" in titles
    assert brief["media"]["codes"] and veteran_problems(brief) == []
    a = auditor.answer("Is this a fake video?", card)
    assert a["intent"] == "media" and a["headline"].startswith(f"{len(brief['media']['codes'])} media")
    assert any("not proof a clip is fake" in ln["text"] for ln in a["lines"])


def test_every_new_string_is_free_of_advice():
    texts = list(media.TEXT.values()) + [media.TITLE, media.NOTE, social.RESTRICTED_MESSAGE] + list(social.PLATFORM_NAMES.values())
    texts += [veteran.FLAG_LABELS[c] for c in ("impersonation", "funnel", "missing_context")]
    texts += [auditor.MENTOR["check"], auditor.MENTOR["media"]] + auditor.QUICK_PROMPTS[1:]
    for post in social.DEMO_POSTS.values():
        card = card_for(post["text"], post["platform"])
        assert wording_problems(card) == []
        brief = build_veteran_brief(card)
        texts += [x["text"] for x in brief["wrong"]] + [x["title"] for x in brief["wrong"]]
        for q in auditor.QUICK_PROMPTS[1:] + ["Is this a fake video?"]:
            a = auditor.answer(q, card)
            texts += [a["headline"], a["mentor"]] + [ln["text"] for ln in a["lines"]]
    clean(texts)
    assert auditor.answer(auditor.QUICK_PROMPTS[0], card_for("BUY ITC"))["refused"] is True


def test_volume_and_chart_check_combines_both(client):
    card = card_for("BUY SBIN CMP 100 TGT 130")
    a = auditor.answer("Volume & chart check", card)
    assert a["intent"] == "check" and {"Volume", "Tech"} <= {c for ln in a["lines"] for c in ln["cite"]}
