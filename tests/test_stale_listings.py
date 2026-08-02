from backend.lib import db
from backend.scout import stale_listings
from backend.scout.stale_listings import (
    build_stale_note,
    contact_target,
    is_stale,
    process_stale_listing,
)


def _prop(**overrides):
    prop = {
        "id": "prop-1",
        "address": "123 Main St",
        "city": "Stockton",
        "days_on_market": 80,
        "listing_status": "expired",
        "listing_source": "MLS",
        "owner_phone": "2095551212",
        "owner_name": "Maria Gonzalez",
    }
    prop.update(overrides)
    return prop


def test_listing_under_the_threshold_is_not_stale():
    assert is_stale(_prop(days_on_market=30), 65) is False


def test_listing_at_the_threshold_is_stale():
    assert is_stale(_prop(days_on_market=65), 65) is True


def test_listing_with_unknown_days_is_not_stale():
    assert is_stale(_prop(days_on_market=None), 65) is False


def test_active_listing_routes_to_the_agent_not_the_owner():
    for status in ("active", "listed", "for_sale", "pending"):
        assert contact_target(_prop(listing_status=status)) == "listing_agent"


def test_expired_listing_routes_to_the_owner():
    for status in ("expired", "withdrawn", "cancelled", "off_market"):
        assert contact_target(_prop(listing_status=status)) == "owner"


def test_unknown_listing_status_is_held_for_review():
    assert contact_target(_prop(listing_status="unknown")) == "review"
    assert contact_target(_prop(listing_status=None)) == "review"


def test_note_warns_about_interference_for_an_active_listing():
    note = build_stale_note(_prop(listing_status="active"))
    assert "listing agent, not the owner" in note
    assert "tortious interference" in note


def test_note_clears_direct_contact_once_expired():
    note = build_stale_note(_prop(listing_status="expired"))
    assert "owner can be approached directly" in note


def test_note_includes_days_and_price_cuts():
    note = build_stale_note(_prop(days_on_market=92, price_drop_count=3))
    assert "92 days" in note
    assert "3 time(s)" in note


def test_unknown_status_is_flagged_but_never_contacted(monkeypatch):
    flagged = {}
    monkeypatch.setattr(db, "update_property_fields", lambda pid, f: flagged.update(f))
    monkeypatch.setattr(db, "now_iso", lambda: "2026-07-31T00:00:00Z")

    def _should_not_run(*args, **kwargs):
        raise AssertionError("created a lead for a listing whose status is unknown")

    monkeypatch.setattr(stale_listings, "intake_lead", _should_not_run)

    result = process_stale_listing(_prop(listing_status="unknown"))

    assert result["success"] is False
    assert result["reason"] == "status_unknown"
    assert flagged["stale_listing_flagged_at"]


def test_active_listing_creates_a_lead_for_the_agent(monkeypatch):
    monkeypatch.setattr(db, "update_property_fields", lambda pid, f: None)
    monkeypatch.setattr(db, "now_iso", lambda: "2026-07-31T00:00:00Z")
    captured = {}

    def _fake_intake(source, **kwargs):
        captured.update(source=source, **kwargs)
        return {"success": True, "lead_id": "lead-1"}

    monkeypatch.setattr(stale_listings, "intake_lead", _fake_intake)

    prop = _prop(
        listing_status="active",
        listing_agent_name="Dana Reyes",
        listing_agent_phone="2095559999",
    )
    result = process_stale_listing(prop)

    assert result["target"] == "listing_agent"
    assert captured["owner_phone"] == "2095559999"
    assert captured["owner_name"] == "Dana Reyes"
    assert captured["distress_type"] == "stale_listing"


def test_active_listing_without_an_agent_phone_is_skipped(monkeypatch):
    monkeypatch.setattr(db, "update_property_fields", lambda pid, f: None)
    monkeypatch.setattr(db, "now_iso", lambda: "2026-07-31T00:00:00Z")

    def _should_not_run(*args, **kwargs):
        raise AssertionError("fell back to the owner on an actively listed property")

    monkeypatch.setattr(stale_listings, "intake_lead", _should_not_run)

    result = process_stale_listing(_prop(listing_status="active", listing_agent_phone=None))

    assert result["success"] is False
    assert result["reason"] == "no_agent_phone"


def test_expired_listing_creates_a_lead_for_the_owner(monkeypatch):
    monkeypatch.setattr(db, "update_property_fields", lambda pid, f: None)
    monkeypatch.setattr(db, "now_iso", lambda: "2026-07-31T00:00:00Z")
    captured = {}

    def _fake_intake(source, **kwargs):
        captured.update(source=source, **kwargs)
        return {"success": True, "lead_id": "lead-1"}

    monkeypatch.setattr(stale_listings, "intake_lead", _fake_intake)

    result = process_stale_listing(_prop(listing_status="expired"))

    assert result["target"] == "owner"
    assert captured["owner_phone"] == "2095551212"
    assert captured["distress_type"] == "expired_listing"


def test_pass_counts_agent_and_owner_routes(monkeypatch):
    props = [
        _prop(id="p1", listing_status="expired"),
        _prop(id="p2", listing_status="active", listing_agent_phone="2095559999"),
        _prop(id="p3", listing_status="unknown"),
    ]
    monkeypatch.setattr(db, "get_unflagged_stale_listings", lambda min_days, limit: props)
    monkeypatch.setattr(db, "update_property_fields", lambda pid, f: None)
    monkeypatch.setattr(db, "now_iso", lambda: "2026-07-31T00:00:00Z")
    monkeypatch.setattr(
        stale_listings, "intake_lead", lambda source, **kw: {"success": True, "lead_id": "l"}
    )

    results = stale_listings.run_stale_listing_pass()

    assert results["checked"] == 3
    assert results["to_owner"] == 1
    assert results["to_agent"] == 1
    assert results["skipped"] == 1


def test_pass_survives_one_bad_property(monkeypatch):
    props = [_prop(id="p1"), _prop(id="p2")]
    monkeypatch.setattr(db, "get_unflagged_stale_listings", lambda min_days, limit: props)
    monkeypatch.setattr(db, "update_property_fields", lambda pid, f: None)
    monkeypatch.setattr(db, "now_iso", lambda: "2026-07-31T00:00:00Z")

    def _flaky(source, **kwargs):
        if kwargs.get("address") and props[0]["id"] == "p1":
            props[0]["id"] = "done"
            raise RuntimeError("intake blew up")
        return {"success": True, "lead_id": "l"}

    monkeypatch.setattr(stale_listings, "intake_lead", _flaky)

    results = stale_listings.run_stale_listing_pass()

    assert results["checked"] == 2
