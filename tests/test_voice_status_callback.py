from fastapi.testclient import TestClient

from backend.api.main import app
from backend.lib import db

client = TestClient(app)


def test_status_callback_ignores_non_terminal_status(monkeypatch):
    called = {"count": 0}

    def _fake_mark(sid, status):
        called["count"] += 1

    monkeypatch.setattr(db, "mark_call_terminal_if_unset", _fake_mark)
    resp = client.post("/api/voice/status", data={"CallSid": "CA1", "CallStatus": "ringing"})
    assert resp.status_code == 200
    assert called["count"] == 0


def test_status_callback_no_answer_triggers_followup(monkeypatch):
    monkeypatch.setattr(db, "mark_call_terminal_if_unset", lambda sid, status: True)
    monkeypatch.setattr(db, "get_call_by_signalwire_sid", lambda sid: {"id": "call-1", "lead_id": "lead-1"})
    monkeypatch.setattr(db, "mark_followup_sent_if_unset", lambda call_id: True)

    import backend.alerts.followup as followup_module
    captured = {}

    def _fake_followup(lead_id, call_id, disposition):
        captured.update(lead_id=lead_id, call_id=call_id, disposition=disposition)

    monkeypatch.setattr(followup_module, "send_post_call_followup", _fake_followup)

    resp = client.post("/api/voice/status", data={"CallSid": "CA1", "CallStatus": "no-answer"})

    assert resp.status_code == 200
    assert captured["lead_id"] == "lead-1"
    assert captured["disposition"] == "no-answer"


def test_status_callback_already_terminal_skips_followup(monkeypatch):
    monkeypatch.setattr(db, "mark_call_terminal_if_unset", lambda sid, status: False)
    called = {"count": 0}

    def _fake_get(sid):
        called["count"] += 1

    monkeypatch.setattr(db, "get_call_by_signalwire_sid", _fake_get)

    resp = client.post("/api/voice/status", data={"CallSid": "CA1", "CallStatus": "busy"})

    assert resp.status_code == 200
    assert called["count"] == 0


def test_status_callback_voicemail_completion_triggers_followup(monkeypatch):
    monkeypatch.setattr(
        db,
        "get_call_by_signalwire_sid",
        lambda sid: {"id": "call-1", "lead_id": "lead-1", "voicemail_left": True},
    )
    monkeypatch.setattr(db, "mark_followup_sent_if_unset", lambda call_id: True)

    import backend.alerts.followup as followup_module
    captured = {}

    def _fake_followup(lead_id, call_id, disposition):
        captured.update(lead_id=lead_id, disposition=disposition)

    monkeypatch.setattr(followup_module, "send_post_call_followup", _fake_followup)

    resp = client.post("/api/voice/status", data={"CallSid": "CA1", "CallStatus": "completed"})

    assert resp.status_code == 200
    assert captured["disposition"] == "voicemail"


def test_status_callback_duplicate_delivery_sends_one_followup(monkeypatch):
    monkeypatch.setattr(
        db,
        "get_call_by_signalwire_sid",
        lambda sid: {"id": "call-1", "lead_id": "lead-1", "voicemail_left": True},
    )
    guard = {"remaining": 1}

    def _fake_guard(call_id):
        if guard["remaining"] <= 0:
            return False
        guard["remaining"] -= 1
        return True

    monkeypatch.setattr(db, "mark_followup_sent_if_unset", _fake_guard)

    import backend.alerts.followup as followup_module
    sends = {"count": 0}
    monkeypatch.setattr(
        followup_module,
        "send_post_call_followup",
        lambda lead_id, call_id, disposition: sends.update(count=sends["count"] + 1),
    )

    for _ in range(3):
        client.post("/api/voice/status", data={"CallSid": "CA1", "CallStatus": "completed"})

    assert sends["count"] == 1


def test_status_callback_completed_human_call_sends_nothing(monkeypatch):
    monkeypatch.setattr(
        db,
        "get_call_by_signalwire_sid",
        lambda sid: {"id": "call-1", "lead_id": "lead-1", "voicemail_left": False},
    )

    import backend.alerts.followup as followup_module
    sends = {"count": 0}
    monkeypatch.setattr(
        followup_module,
        "send_post_call_followup",
        lambda lead_id, call_id, disposition: sends.update(count=sends["count"] + 1),
    )

    resp = client.post("/api/voice/status", data={"CallSid": "CA1", "CallStatus": "completed"})

    assert resp.status_code == 200
    assert sends["count"] == 0
