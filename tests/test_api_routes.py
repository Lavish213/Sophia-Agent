import io

from fastapi.testclient import TestClient

from backend.api.main import app
from backend.lib import db

client = TestClient(app)


def test_voice_inbound_returns_laml(monkeypatch):
    from backend.lib.config import get_settings
    monkeypatch.setenv("PUBLIC_URL", "https://sophia.example.com")
    get_settings.cache_clear()
    try:
        resp = client.post("/api/voice/inbound", data={"From": "+12095551212", "To": "+12098814144", "CallSid": "CA1"})
        assert resp.status_code == 200
        assert "<Connect><Stream" in resp.text
        assert "wss://sophia.example.com/api/voice/stream" in resp.text
    finally:
        get_settings.cache_clear()


def test_trigger_outbound_call_route(monkeypatch):
    import backend.api.routes.calls as calls_route
    monkeypatch.setattr(calls_route, "place_outbound_call", lambda lead_id: {"success": True, "call_sid": "CA1"})
    resp = client.post("/api/leads/lead-1/call")
    assert resp.status_code == 200
    assert resp.json()["call_sid"] == "CA1"


def test_trigger_outbound_call_route_failure(monkeypatch):
    import backend.api.routes.calls as calls_route
    failure = {"success": False, "reason": "no_phone_on_file"}
    monkeypatch.setattr(calls_route, "place_outbound_call", lambda lead_id: failure)
    resp = client.post("/api/leads/lead-1/call")
    assert resp.status_code == 422


def test_health_ok(monkeypatch):
    monkeypatch.setattr(db, "health_check", lambda: True)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["checks"]["supabase"] == "ok"


def test_health_degraded_when_supabase_down(monkeypatch):
    def _raise():
        raise RuntimeError("down")
    monkeypatch.setattr(db, "health_check", _raise)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "degraded"


def test_upload_rejects_non_csv():
    resp = client.post(
        "/api/properties/upload",
        files={"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert resp.status_code == 400


def test_upload_processes_valid_csv(monkeypatch):
    monkeypatch.setattr(db, "upsert_property", lambda data: "prop-1")
    monkeypatch.setattr(db, "insert_contact", lambda data: None)
    fake_lead = {"id": "lead-1", "owner_phone": None, "owner_phone_2": None, "owner_email": None}
    monkeypatch.setattr(db, "get_or_create_lead", lambda pid: fake_lead)
    monkeypatch.setattr(db, "update_lead_fields", lambda lead_id, fields: None)

    csv_content = b"Property Address,Owner Phone,Beds,Sqft\n123 Main St,2095551212,3,1200\n"
    resp = client.post(
        "/api/properties/upload",
        files={"file": ("leads.csv", io.BytesIO(csv_content), "text/csv")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["processed"] == 1
    assert body["leads_created"] == 1
    assert body["errors"] == 0


def test_get_property_404(monkeypatch):
    monkeypatch.setattr(db, "get_property_by_id", lambda pid: None)
    resp = client.get("/api/properties/missing")
    assert resp.status_code == 404


def test_get_property_success(monkeypatch):
    monkeypatch.setattr(db, "get_property_by_id", lambda pid: {"id": pid, "address": "123 Main St"})
    resp = client.get("/api/properties/prop-1")
    assert resp.status_code == 200
    assert resp.json()["address"] == "123 Main St"


def test_get_lead_404(monkeypatch):
    monkeypatch.setattr(db, "get_lead_with_property", lambda lead_id: None)
    resp = client.get("/api/leads/missing")
    assert resp.status_code == 404


def test_get_lead_success(monkeypatch):
    monkeypatch.setattr(db, "get_lead_with_property", lambda lead_id: {"id": lead_id, "properties": {}})
    monkeypatch.setattr(db, "get_calls_for_lead", lambda lead_id: [])
    monkeypatch.setattr(db, "get_offers_for_lead", lambda lead_id: [])
    resp = client.get("/api/leads/lead-1")
    assert resp.status_code == 200
    assert resp.json()["calls"] == []


def test_update_lead_stage(monkeypatch):
    monkeypatch.setattr(db, "get_lead_by_id", lambda lead_id: {"id": lead_id, "stage": "new"})
    calls = {}
    monkeypatch.setattr(db, "update_lead_stage", lambda lead_id, stage: calls.setdefault("stage", stage))
    resp = client.patch("/api/leads/lead-1", json={"stage": "contacted"})
    assert resp.status_code == 200
    assert calls["stage"] == "contacted"


def test_add_comp_triggers_recalculation(monkeypatch):
    monkeypatch.setattr(db, "get_property_by_id", lambda pid: {"id": pid, "sqft": 1200})
    monkeypatch.setattr(db, "insert_comp", lambda data: "comp-1")
    monkeypatch.setattr(db, "get_comps_by_property", lambda pid: [
        {"sold_price": 15000000, "sqft": 1200, "sold_date": "2026-01-01", "distance_miles": 0.1},
        {"sold_price": 15200000, "sqft": 1200, "sold_date": "2026-01-01", "distance_miles": 0.1},
        {"sold_price": 14900000, "sqft": 1200, "sold_date": "2026-01-01", "distance_miles": 0.1},
    ])
    monkeypatch.setattr(db, "update_property_arv", lambda *a, **k: None)

    resp = client.post("/api/properties/prop-1/comps", json={"sold_price": 15000000, "sqft": 1200})
    assert resp.status_code == 200
    assert resp.json()["arv"] is not None


def test_create_offer_uses_property_arv_by_default(monkeypatch):
    fake_lead = {"id": "lead-1", "properties": {"id": "prop-1", "estimated_arv": 20000000}}
    monkeypatch.setattr(db, "get_lead_with_property", lambda lead_id: fake_lead)
    captured = {}

    def _create_offer(**kwargs):
        captured.update(kwargs)
        return "offer-1"
    monkeypatch.setattr(db, "create_offer", _create_offer)
    monkeypatch.setattr(db, "get_offer_by_id", lambda offer_id: {"id": offer_id, "status": "draft"})

    resp = client.post("/api/leads/lead-1/offers", json={})
    assert resp.status_code == 200
    assert captured["arv_used"] == 20000000


def test_update_offer_rejects_invalid_status(monkeypatch):
    resp = client.patch("/api/offers/offer-1", json={"status": "not_a_real_status"})
    assert resp.status_code == 400


def test_update_offer_status_success(monkeypatch):
    monkeypatch.setattr(db, "get_offer_by_id", lambda offer_id: {"id": offer_id, "status": "sent"})
    called = {}
    monkeypatch.setattr(db, "update_offer_status", lambda offer_id, status, notes: called.setdefault("status", status))
    resp = client.patch("/api/offers/offer-1", json={"status": "sent"})
    assert resp.status_code == 200
    assert called["status"] == "sent"


def test_get_call_with_transcript(monkeypatch):
    monkeypatch.setattr(db, "get_call_by_id", lambda call_id: {"id": call_id})
    monkeypatch.setattr(db, "get_transcript_chunks", lambda call_id: [{"speaker": "sophia", "text": "hey there"}])
    resp = client.get("/api/calls/call-1")
    assert resp.status_code == 200
    assert len(resp.json()["transcript_chunks"]) == 1
