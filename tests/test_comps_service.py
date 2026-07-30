import pytest

import backend.lib.db as db
from backend.comps.service import recalculate_arv_for_property


def test_raises_for_missing_property(monkeypatch):
    monkeypatch.setattr(db, "get_property_by_id", lambda pid: None)
    with pytest.raises(ValueError):
        recalculate_arv_for_property("missing")


def test_recalculates_and_saves(monkeypatch):
    saved = {}

    monkeypatch.setattr(db, "get_property_by_id", lambda pid: {"id": pid, "sqft": 1200})
    monkeypatch.setattr(db, "get_comps_by_property", lambda pid: [
        {"sold_price": 15000000, "sqft": 1200, "sold_date": "2026-01-01", "distance_miles": 0.1},
        {"sold_price": 15500000, "sqft": 1200, "sold_date": "2026-02-01", "distance_miles": 0.1},
        {"sold_price": 14800000, "sqft": 1200, "sold_date": "2026-03-01", "distance_miles": 0.1},
    ])

    def _update(property_id, arv, mao, confidence, extra=None):
        saved["property_id"] = property_id
        saved["arv"] = arv
        saved["mao"] = mao
        saved["confidence"] = confidence
        saved["extra"] = extra

    monkeypatch.setattr(db, "update_property_arv", _update)

    result = recalculate_arv_for_property("prop-1")

    assert result["arv"] is not None
    assert saved["property_id"] == "prop-1"
    assert saved["arv"] == result["arv"]
    assert saved["mao"] == result["mao"]


def test_no_comps_skips_save(monkeypatch):
    monkeypatch.setattr(db, "get_property_by_id", lambda pid: {"id": pid, "sqft": 1200})
    monkeypatch.setattr(db, "get_comps_by_property", lambda pid: [])

    called = {"count": 0}
    def _update(*a, **k):
        called["count"] += 1
    monkeypatch.setattr(db, "update_property_arv", _update)

    result = recalculate_arv_for_property("prop-1")

    assert result["arv"] is None
    assert called["count"] == 0
