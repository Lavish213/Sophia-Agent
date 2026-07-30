from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.routes.intake import WebFormLead, build_intake_notes
from backend.lib.config import get_settings
from backend.scout import intake as intake_module

client = TestClient(app)

_PAYLOAD = {
    "name": "Maria Gonzalez",
    "phone": "2095551212",
    "email": "maria@example.com",
    "address": "123 Main St",
    "timeline": "ASAP",
    "condition": "needs work",
}


def _set_secret(monkeypatch, value):
    monkeypatch.setenv("INTAKE_WEBHOOK_SECRET", value)
    get_settings.cache_clear()


def test_web_form_requires_configured_secret(monkeypatch):
    monkeypatch.delenv("INTAKE_WEBHOOK_SECRET", raising=False)
    get_settings.cache_clear()
    try:
        response = client.post("/api/intake/web-form", json=_PAYLOAD)
        assert response.status_code == 503
    finally:
        get_settings.cache_clear()


def test_web_form_rejects_wrong_secret(monkeypatch):
    _set_secret(monkeypatch, "right-secret")
    try:
        response = client.post(
            "/api/intake/web-form", json=_PAYLOAD, headers={"X-Intake-Secret": "wrong-secret"}
        )
        assert response.status_code == 401
    finally:
        get_settings.cache_clear()


def test_web_form_rejects_missing_secret(monkeypatch):
    _set_secret(monkeypatch, "right-secret")
    try:
        response = client.post("/api/intake/web-form", json=_PAYLOAD)
        assert response.status_code == 401
    finally:
        get_settings.cache_clear()


def test_web_form_creates_lead(monkeypatch):
    _set_secret(monkeypatch, "right-secret")
    captured = {}

    def _fake_intake(source, **kwargs):
        captured["source"] = source
        captured.update(kwargs)
        return {"success": True, "reason": "created", "lead_id": "lead-1", "property_id": "p1", "created": True}

    monkeypatch.setattr(intake_module, "intake_lead", _fake_intake)
    import backend.api.routes.intake as route_module

    monkeypatch.setattr(route_module, "intake_lead", _fake_intake)

    try:
        response = client.post(
            "/api/intake/web-form", json=_PAYLOAD, headers={"X-Intake-Secret": "right-secret"}
        )
        assert response.status_code == 200
        assert response.json()["lead_id"] == "lead-1"
        assert captured["source"] == "web_form"
        assert captured["owner_phone"] == "2095551212"
        assert "ASAP" in captured["notes"]
    finally:
        get_settings.cache_clear()


def test_web_form_requires_phone_or_email(monkeypatch):
    _set_secret(monkeypatch, "right-secret")
    try:
        response = client.post(
            "/api/intake/web-form",
            json={"name": "No Contact", "address": "123 Main St"},
            headers={"X-Intake-Secret": "right-secret"},
        )
        assert response.status_code == 422
        assert response.json()["detail"] == "phone_or_email_required"
    finally:
        get_settings.cache_clear()


def test_build_intake_notes_includes_supplied_fields():
    notes = build_intake_notes(
        WebFormLead(timeline="30 days", condition="roof leak", asking_price="$250k", message="call me")
    )
    assert "30 days" in notes
    assert "roof leak" in notes
    assert "$250k" in notes
    assert "call me" in notes
