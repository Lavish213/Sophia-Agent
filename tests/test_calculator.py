from backend.comps.calculator import calculate_arv


def _comp(sold_price_dollars, sqft, days_ago=30, distance_miles=0.2):
    from datetime import datetime, timedelta, timezone
    sold_date = (datetime.now(timezone.utc) - timedelta(days=days_ago)).date().isoformat()
    return {
        "sold_price": sold_price_dollars * 100,
        "sqft": sqft,
        "sold_date": sold_date,
        "distance_miles": distance_miles,
    }


def test_no_comps_returns_none():
    result = calculate_arv([], 1200)
    assert result["arv"] is None
    assert result["confidence"] == "low"


def test_arv_uses_weighted_price_per_sqft():
    comps = [_comp(150000, 1200), _comp(160000, 1200), _comp(155000, 1200)]
    result = calculate_arv(comps, 1200)
    assert result["arv"] is not None
    assert 15000000 <= result["arv"] <= 16000000


def test_mao_formula_default():
    comps = [_comp(200000, 1000), _comp(200000, 1000), _comp(200000, 1000)]
    result = calculate_arv(comps, 1000)
    expected_mao = max(int(result["arv"] * 0.70) - 2500000, 0)
    assert result["mao"] == expected_mao


def test_confidence_low_with_few_comps():
    comps = [_comp(150000, 1200)]
    result = calculate_arv(comps, 1200)
    assert result["confidence"] == "low"


def test_confidence_high_with_many_consistent_comps():
    comps = [_comp(150000, 1200) for _ in range(6)]
    result = calculate_arv(comps, 1200)
    assert result["confidence"] == "high"
    assert result["comp_strength"] == "strong"


def test_stale_comps_get_lower_weight():
    fresh = [_comp(200000, 1000, days_ago=10) for _ in range(3)]
    stale = [_comp(100000, 1000, days_ago=400) for _ in range(3)]
    result_fresh = calculate_arv(fresh, 1000)
    result_mixed = calculate_arv(fresh + stale, 1000)
    assert result_mixed["arv"] < result_fresh["arv"]


def test_mao_never_negative():
    comps = [_comp(1000, 2000)]
    result = calculate_arv(comps, 2000)
    assert result["mao"] >= 0
