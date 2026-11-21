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
