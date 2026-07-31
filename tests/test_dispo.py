from backend.dispo import blast as blast_module
from backend.dispo.blast import build_deal_summary
from backend.dispo.matcher import buyer_matches_property, match_buyers_for_property, rank_buyers
from backend.lib import db


def _buyer(**overrides):
    buyer = {
        "id": "buyer-1",
        "name": "Rick Chen",
        "phone": "+12095551212",
        "min_price": 5000000,
        "max_price": 30000000,
        "cities": ["Stockton", "Lodi"],
        "active": True,
        "opted_out": False,
        "deals_closed": 3,
        "proof_of_funds_on_file": True,
    }
    buyer.update(overrides)
    return buyer


def _prop(**overrides):
    prop = {
        "id": "prop-1",
        "address": "123 Main St",
        "city": "Stockton",
        "beds": 3,
        "baths": 2,
        "sqft": 1400,
        "estimated_arv": 30000000,
    }
    prop.update(overrides)
    return prop


def test_buyer_in_range_and_city_matches():
    ok, reason = buyer_matches_property(_buyer(), _prop(), 20000000)
    assert ok is True
    assert reason == "match"


def test_buyer_above_their_max_price_is_skipped():
    ok, reason = buyer_matches_property(_buyer(max_price=15000000), _prop(), 20000000)
    assert ok is False
    assert reason == "above_max_price"


def test_buyer_below_their_min_price_is_skipped():
    ok, reason = buyer_matches_property(_buyer(min_price=25000000), _prop(), 20000000)
    assert ok is False
    assert reason == "below_min_price"


def test_buyer_who_does_not_buy_in_that_city_is_skipped():
    ok, reason = buyer_matches_property(_buyer(), _prop(city="Fresno"), 20000000)
    assert ok is False
    assert reason == "city_not_matched"


def test_buyer_with_no_city_filter_buys_anywhere():
    ok, _ = buyer_matches_property(_buyer(cities=[]), _prop(city="Fresno"), 20000000)
    assert ok is True


def test_opted_out_buyer_never_matches():
    ok, reason = buyer_matches_property(_buyer(opted_out=True), _prop(), 20000000)
    assert ok is False
    assert reason == "opted_out"


def test_inactive_buyer_never_matches():
    ok, reason = buyer_matches_property(_buyer(active=False), _prop(), 20000000)
    assert ok is False
    assert reason == "inactive"


def test_beds_and_sqft_minimums_are_respected():
    assert buyer_matches_property(_buyer(min_beds=4), _prop(), 20000000)[1] == "below_min_beds"
    assert buyer_matches_property(_buyer(min_sqft=2000), _prop(), 20000000)[1] == "below_min_sqft"


def test_unknown_asking_price_does_not_filter_on_price():
    ok, _ = buyer_matches_property(_buyer(min_price=25000000), _prop(), None)
    assert ok is True


def test_ranking_puts_proven_buyers_first():
    buyers = [
        _buyer(id="b1", name="New Guy", deals_closed=0, proof_of_funds_on_file=False),
        _buyer(id="b2", name="Closer", deals_closed=9),
        _buyer(id="b3", name="Some Buyer", deals_closed=2),
    ]
    ranked = rank_buyers(buyers)
    assert [b["id"] for b in ranked] == ["b2", "b3", "b1"]


def test_match_buyers_filters_and_ranks_together():
    buyers = [
        _buyer(id="b1", deals_closed=1),
        _buyer(id="b2", deals_closed=5),
        _buyer(id="b3", opted_out=True),
    ]
    matched = match_buyers_for_property(buyers, _prop(), 20000000)
    assert [b["id"] for b in matched] == ["b2", "b1"]


def test_deal_summary_reads_like_a_real_blast():
    summary = build_deal_summary(_prop(), 20000000)
    assert "123 Main St" in summary
    assert "Stockton" in summary
    assert "3bd" in summary
    assert "$200,000" in summary
    assert "Reply" in summary


def test_deal_summary_survives_a_sparse_property():
    summary = build_deal_summary({"address": "456 Oak Ave"}, None)
    assert "456 Oak Ave" in summary
    assert "TBD" in summary


def test_blast_stops_when_the_property_is_missing(monkeypatch):
    monkeypatch.setattr(db, "get_property_by_id", lambda pid: None)
    result = blast_module.blast_deal("missing")
    assert result["success"] is False
    assert result["reason"] == "property_not_found"


def test_blast_reports_cleanly_when_no_buyer_matches(monkeypatch):
    monkeypatch.setattr(db, "get_property_by_id", lambda pid: _prop())
    monkeypatch.setattr(db, "list_active_buyers", lambda: [])
    result = blast_module.blast_deal("prop-1", 20000000)
    assert result["sent"] == 0
    assert result["reason"] == "no_matching_buyers"


def test_blast_sends_to_matched_buyers_and_records_each(monkeypatch):
    monkeypatch.setattr(db, "get_property_by_id", lambda pid: _prop())
    monkeypatch.setattr(db, "list_active_buyers", lambda: [_buyer(id="b1"), _buyer(id="b2")])
    monkeypatch.setattr(db, "deal_already_blasted", lambda p, b, c: False)
    recorded = []
    monkeypatch.setattr(
        db, "insert_deal_blast", lambda p, b, c, s: recorded.append((b, s))
    )
    monkeypatch.setattr(blast_module, "_send_to_buyer", lambda buyer, body, ch: {"success": True})

    result = blast_module.blast_deal("prop-1", 20000000)

    assert result["sent"] == 2
    assert {r[0] for r in recorded} == {"b1", "b2"}


def test_blast_never_sends_the_same_deal_to_a_buyer_twice(monkeypatch):
    monkeypatch.setattr(db, "get_property_by_id", lambda pid: _prop())
    monkeypatch.setattr(db, "list_active_buyers", lambda: [_buyer(id="b1")])
    monkeypatch.setattr(db, "deal_already_blasted", lambda p, b, c: True)

    def _should_not_send(*args, **kwargs):
        raise AssertionError("blasted the same buyer twice for one property")

    monkeypatch.setattr(blast_module, "_send_to_buyer", _should_not_send)

    result = blast_module.blast_deal("prop-1", 20000000)

    assert result["sent"] == 0
    assert result["skipped"] == 1


def test_a_failed_send_is_recorded_and_does_not_stop_the_blast(monkeypatch):
    monkeypatch.setattr(db, "get_property_by_id", lambda pid: _prop())
    monkeypatch.setattr(db, "list_active_buyers", lambda: [_buyer(id="b1"), _buyer(id="b2")])
    monkeypatch.setattr(db, "deal_already_blasted", lambda p, b, c: False)
    recorded = []
    monkeypatch.setattr(db, "insert_deal_blast", lambda p, b, c, s: recorded.append((b, s)))

    def _flaky(buyer, body, channel):
        return {"success": buyer["id"] != "b1", "reason": "carrier rejected"}

    monkeypatch.setattr(blast_module, "_send_to_buyer", _flaky)

    result = blast_module.blast_deal("prop-1", 20000000)

    assert result["sent"] == 1
    assert ("b1", "failed") in recorded
