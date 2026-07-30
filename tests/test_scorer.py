from backend.scout.scorer import calculate_distress_score


def _base_property(**overrides) -> dict:
    prop = {
        "address": "123 Main St",
        "beds": 3,
        "sqft": 1200,
        "estimated_value": 15000000,
        "distress_type": "unknown",
    }
    prop.update(overrides)
    return prop


def test_disqualifies_vacant_land():
    prop = _base_property(property_type="vacant land", beds=0, sqft=0)
    score = calculate_distress_score(prop)
    assert score == 0
    assert prop["deal_viable"] is False
    assert prop["disqualified_reason"].startswith("property_type")


def test_disqualifies_no_beds():
    prop = _base_property(beds=0)
    score = calculate_distress_score(prop)
    assert score == 0
    assert prop["disqualified_reason"] == "no_beds"


def test_disqualifies_value_out_of_range():
    prop = _base_property(estimated_value=50000000)
    score = calculate_distress_score(prop)
    assert score == 0
    assert prop["disqualified_reason"].startswith("value_too_high")


def test_pre_foreclosure_scores_higher_than_unknown():
    baseline = _base_property()
    distressed = _base_property(distress_type="pre_foreclosure")
    baseline_score = calculate_distress_score(baseline)
    distressed_score = calculate_distress_score(distressed)
    assert distressed_score > baseline_score


def test_vacant_absentee_free_clear_stacks_high():
    prop = _base_property(
        distress_type="pre_foreclosure",
        vacant=True,
        absentee_owner=True,
        free_and_clear=True,
        years_owned=20,
    )
    score = calculate_distress_score(prop)
    assert score >= 85
    assert prop["deal_viable"] is True


def test_score_never_exceeds_100():
    prop = _base_property(
        distress_type="pre_foreclosure",
        vacant=True,
        absentee_owner=True,
        free_and_clear=True,
        years_owned=30,
        tax_year=2000,
        lien_amount=5000000,
        auction_date="2026-01-01",
        equity_pct=90,
        price_reduced=True,
        days_on_market=90,
        price_drop_count=5,
    )
    score = calculate_distress_score(prop)
    assert score <= 100


def test_arv_falls_back_to_assessed_value():
    prop = _base_property(estimated_value=None, assessed_total_value=8000000)
    calculate_distress_score(prop)
    assert prop["estimated_arv"] == int(8000000 / 0.80)


def test_mao_formula_matches_documented_default():
    prop = _base_property(estimated_value=20000000)
    calculate_distress_score(prop)
    expected_mao = max(0, int(prop["estimated_arv"] * 0.70) - 2500000)
    assert prop["mao"] == expected_mao
