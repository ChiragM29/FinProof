"""Step 2: who is this (YouTube channel profile), description facts, Instagram handles, offline fallback."""

import json

from finproof import profile, social

PAGE = ('..."channelMetadataRenderer":{"title":"Stock Market INDIA","description":"Thanks for visiting.\\n\\n'
        'I am not a SEBI registered.\\nFor business enquiry"...'
        '"canonicalBaseUrl":"/@StockMarketINDIA"..."subscriberCountText":"8.64\\u00a0lakh subscribers",'
        '"videoCountText":"2,992 videos"..."channelId":"UCCLu5B_Ctsw4N20DJvDykOA"')


def test_profile_parsing_from_a_saved_channel_page():
    p = profile.parse_channel_page(PAGE)
    assert p["channel"] == "Stock Market INDIA" and p["handle"] == "@StockMarketINDIA"
    assert p["subscribers"] == "8.64 lakh subscribers" and p["videos"] == "2,992 videos"
    assert p["url"] == "https://www.youtube.com/@StockMarketINDIA" and p["channel_id"] == "UCCLu5B_Ctsw4N20DJvDykOA"
    assert profile.about_lines(p["about"]) == ["Thanks for visiting.", "I am not a SEBI registered."]


def test_missing_values_are_left_out_not_guessed():
    p = profile.parse_channel_page('"channelMetadataRenderer":{"title":"Only A Name"}')
    assert p == {"channel": "Only A Name"}


def test_offline_uses_the_cached_profile_and_never_the_network(tmp_path, monkeypatch):
    monkeypatch.setattr(profile, "CH_CACHE", tmp_path)
    assert profile.channel_profile("UCxxxxxxxxxxxxxxxxxxxxxx", offline=True) is None
    (tmp_path / "UCxxxxxxxxxxxxxxxxxxxxxx.json").write_text(json.dumps({"channel": "Saved", "fetched_on": "2026-11-21"}))
    p = profile.channel_profile("UCxxxxxxxxxxxxxxxxxxxxxx", offline=True)
    assert p["channel"] == "Saved" and p["from_cache"] is True and p["provenance"] == "REAL"


def test_description_facts_are_facts_only():
    d = ("Join our Telegram: https://t.me/stockcalls_vip\nPremium course: https://graphy.com/stockpro\n"
         "WhatsApp group chat.whatsapp.com/AbCdEf123\nDisclaimer: for educational purposes only.")
    f = profile.description_facts(d)
    assert f["group_links"] == ["chat.whatsapp.com/AbCdEf123", "https://t.me/stockcalls_vip"]
    assert f["paid_links"] == ["https://graphy.com/stockpro"]
    assert f["disclaimer"].startswith("Disclaimer") and f["provenance"] == "REAL"
    none = profile.description_facts("Market news today.")
    assert none["group_links"] == [] and none["paid_links"] == [] and none["disclaimer"] is None


def test_instagram_handle_from_post_reel_and_profile_urls():
    assert social.detect("https://www.instagram.com/p/ABC12345/")["handle"] is None  # a bare /p/ link names no account
    assert social.detect("https://www.instagram.com/trading.guru/p/ABC12345/")["handle"] == "trading.guru"
    assert social.detect("https://www.instagram.com/trading.guru/reel/XYZ98765/")["handle"] == "trading.guru"
    prof = social.detect("https://www.instagram.com/trading.guru/")
    assert prof["handle"] == "trading.guru" and prof["kind"] == "profile"
    assert social.detect("https://www.instagram.com/reel/FPdemoReel01/")["kind"] == "post"


def test_instagram_embed_url_from_the_three_link_formats():
    assert social.embed_url("https://www.instagram.com/p/C8xYz12AbCd/") == "https://www.instagram.com/p/C8xYz12AbCd/embed/captioned/"
    assert social.embed_url("https://www.instagram.com/reel/C8xYz12AbCd/") == "https://www.instagram.com/reel/C8xYz12AbCd/embed/captioned/"
    assert social.embed_url("https://www.instagram.com/trading.guru/p/C8xYz12AbCd/") == \
        "https://www.instagram.com/p/C8xYz12AbCd/embed/captioned/"


def test_instagram_embed_rejects_bad_shortcodes_and_other_links():
    assert social.embed_url("https://www.instagram.com/p/ABCDEFGHIJKLMNOPQRSTUVWXYZ/") is None  # 26 characters: too long
    assert social.embed_url("https://www.instagram.com/trading.guru/") is None                 # a profile, not a post
    assert social.embed_url("https://evil.example.com/p/C8xYz12AbCd/") is None


def test_journal_logs_a_stock_named_without_a_direction():
    from conftest import FakePrices, make_df
    from finproof import config, journal
    prices = FakePrices({config.BENCHMARK: make_df([100.0] * 400, start="2024-06-03"), "SBIN": make_df([50.0] * 400, start="2024-06-03")})
    out = journal.summarize([{"symbol": "SBIN", "direction": "none", "posted_on": "2024-09-02", "decision": "skipped"}], prices)
    row = out["rows"][0]
    assert row["direction"] == "none" and row["status"] == "scored" and not out.get("problems")
    assert all("in the direction the tip claimed" not in g["text"] for g in out["groups"].values())  # kept out of the averages
