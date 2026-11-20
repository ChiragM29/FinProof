from finproof.extract import extract


def claims(text):
    return {c.symbol: c for c in extract(text).claims if c.symbol}


def test_typical_telegram_tip():
    c = claims("BUY SBIN CMP 780 TGT 820/850 SL 760")["SBIN"]
    assert c.direction == "up"
    assert c.expected_prices == [820.0, 850.0]
    assert c.stop_loss == 760.0 and c.price_at_post == 780.0


def test_old_symbol_maps_to_todays_symbol():
    c = claims("BUY TATAMOTORS CMP 650 TGT 700")["TMPV"]
    assert c.renamed_from == "TATAMOTORS"


def test_company_name_in_lower_case_transcript():
    assert "RELIANCE" in claims("guys reliance is looking very bullish this week")


def test_group_names_are_ambiguous():
    ex = extract("Adani stocks are falling")
    assert ex.claims[0].ambiguous and "ADANIENT" in ex.claims[0].candidates


def test_everyday_nicknames():
    assert {"SBIN", "LT", "BHARTIARTL"} <= set(claims("sbi, l&t and airtel look strong"))


def test_tata_alone_is_ambiguous():
    ex = extract("Tata looks strong")
    assert ex.claims and ex.claims[0].ambiguous and ex.claims[0].symbol is None
    assert len(ex.claims[0].candidates) > 1


def test_negation_makes_direction_unclear():
    c = claims("Don't buy ITC right now")["ITC"]
    assert c.direction == "unclear"


def test_fall_direction():
    assert claims("Sell HDFCBANK below 1600")["HDFCBANK"].direction == "down"


def test_prices_do_not_leak_between_lines():
    text = "BUY SBIN TGT 900\nReliance looks bullish."
    assert claims(text)["RELIANCE"].expected_prices == []


def test_pressure_phrases_and_promises():
    ex = extract("100% guaranteed profit! Join our VIP group before 3 pm. 50% returns in 2 weeks. Insider news coming")
    assert {"guarantee", "urgency", "paid_group", "insider"} <= set(ex.pressure)
    assert 50 in ex.percent_promises


def test_sebi_number_and_claim():
    ex = extract("SEBI registered RA INH000012345 here")
    assert ex.sebi_numbers == ["INH000012345"]
    assert ex.claims_sebi_registration


def test_ordinary_market_talk_finds_no_stock():
    assert extract("the market will open high today and the index may fall later").claims == []


def test_capitalised_common_words_are_not_stocks():
    # "Music" and "West" each start exactly one company name (Music Broadcast, West Coast Paper).
    assert extract("Music video. West side story. Never gonna give you up").claims == []


def test_hinglish_filler_words_are_not_stocks():
    # "pakka" is also a listed company (Pakka Ltd), but here it means "for sure".
    found = claims("Bhai SBIN abhi le lo, paisa double pakka, jaldi karo")
    assert set(found) == {"SBIN"}
    assert found["SBIN"].direction == "up"
