from dataclasses import dataclass, field
from typing import Any

from backend.lib import db
from backend.voice.tools import (
    book_appointment,
    build_sophia_tool_schemas,
    format_offer_range,
    mark_call_ended,
    request_owner_callback,
)


def _lead_with_offer():
    return {
        "id": "lead-1",
        "properties": {"estimated_arv": 20000000, "mao": 11500000},
    }


def test_format_offer_range_no_lead(monkeypatch):
    monkeypatch.setattr(db, "get_lead_with_property", lambda lead_id: None)
    result = format_offer_range("missing")
    assert result["available"] is False


def test_format_offer_range_insufficient_data(monkeypatch):
    monkeypatch.setattr(db, "get_lead_with_property", lambda lead_id: {"id": "lead-1", "properties": {}})
    result = format_offer_range("lead-1")
    assert result["available"] is False
    assert result["reason"] == "not_enough_property_detail_yet"


def test_format_offer_range_computes_bounds(monkeypatch):
    monkeypatch.setattr(db, "get_lead_with_property", lambda lead_id: _lead_with_offer())
    result = format_offer_range("lead-1")
    assert result["available"] is True
    assert result["low_dollars"] < result["high_dollars"]
    assert result["low_dollars"] == int(11500000 * 0.9) // 100


def test_book_appointment_rejects_bad_datetime():
    result = book_appointment("lead-1", "not-a-date")
    assert result["success"] is False


def test_book_appointment_success(monkeypatch):
    captured = {}
    monkeypatch.setattr(db, "update_lead_appointment", lambda lead_id, at: captured.setdefault("at", at))
    monkeypatch.setattr(db, "update_lead_fields", lambda lead_id, fields: captured.setdefault("fields", fields))
    result = book_appointment("lead-1", "2026-08-01T15:00:00Z", notes="wants morning callback first")
    assert result["success"] is True
    assert captured["at"] == "2026-08-01T15:00:00Z"
    assert "wants morning" in captured["fields"]["operator_notes"]


def test_request_owner_callback(monkeypatch):
    captured = {}
    monkeypatch.setattr(db, "update_lead_fields", lambda lead_id, fields: captured.update(fields))
    result = request_owner_callback("lead-1", "seller asked about liens")
    assert result["success"] is True
    assert captured["escalated"] is True
    assert captured["priority_callback"] is True


def test_mark_call_ended_hot(monkeypatch):
    captured = {}
    monkeypatch.setattr(db, "update_lead_fields", lambda lead_id, fields: captured.update(fields))
    result = mark_call_ended("lead-1", "HOT")
    assert result["disposition"] == "HOT"
    assert captured["is_hot_lead"] is True


def test_mark_call_ended_invalid_defaults_to_warm():
    result = mark_call_ended("lead-1", "not_a_real_disposition")
    assert result["disposition"] == "WARM"


@dataclass
class _FakeResultCapture:
    value: Any = None

    async def __call__(self, value):
        self.value = value


@dataclass
class _FakeLLM:
    pushed: list = field(default_factory=list)

    async def push_frame(self, frame):
        self.pushed.append(frame)


@dataclass
class _FakeParams:
    arguments: dict
    result_callback: Any
    llm: Any = None


def test_build_sophia_tool_schemas_returns_every_tool():
    schema = build_sophia_tool_schemas(lead_id="lead-1", on_end_call=None)
    names = {t.name for t in schema.standard_tools}
    assert names == {
        "get_offer_range",
        "book_appointment",
        "request_owner_callback",
        "send_details",
        "end_call",
    }


async def test_get_offer_range_handler_reports_no_lead():
    schema = build_sophia_tool_schemas(lead_id=None, on_end_call=None)
    tool = next(t for t in schema.standard_tools if t.name == "get_offer_range")
    capture = _FakeResultCapture()
    params = _FakeParams(arguments={}, result_callback=capture)
    await tool.handler(params)
    assert capture.value == {"available": False, "reason": "no_lead_on_file"}


async def test_end_call_handler_pushes_end_frame_and_calls_back(monkeypatch):
    from pipecat.frames.frames import EndWorkerFrame

    seen_disposition = {}

    def _on_end(disposition):
        seen_disposition["value"] = disposition

    schema = build_sophia_tool_schemas(lead_id="lead-1", on_end_call=_on_end)
    tool = next(t for t in schema.standard_tools if t.name == "end_call")
    capture = _FakeResultCapture()
    llm = _FakeLLM()
    params = _FakeParams(arguments={"disposition": "HOT"}, result_callback=capture, llm=llm)

    await tool.handler(params)

    assert capture.value == {"success": True}
    assert seen_disposition["value"] == "HOT"
    assert len(llm.pushed) == 1
    assert isinstance(llm.pushed[0], EndWorkerFrame)


def test_send_details_texts_the_seller(monkeypatch):
    from backend.voice.tools import send_details

    monkeypatch.setattr(
        db, "get_lead_with_property", lambda lid: {"id": lid, "owner_phone": "+12095551212"}
    )
    sent = {}
    monkeypatch.setattr(
        "backend.alerts.sms.send_sms",
        lambda lid, body: sent.update(body=body) or {"success": True},
    )

    result = send_details("lead-1", "text", "the offer range we discussed")

    assert result["success"] is True
    assert result["sent"] == ["text"]
    assert "offer range we discussed" in sent["body"]
    assert "STOP" in sent["body"]


def test_send_details_without_a_phone_reports_failure(monkeypatch):
    from backend.voice.tools import send_details

    monkeypatch.setattr(db, "get_lead_with_property", lambda lid: {"id": lid, "owner_phone": None})

    result = send_details("lead-1", "text")

    assert result["success"] is False
    assert result["results"]["text"]["reason"] == "no_phone_on_file"


def test_send_details_without_an_email_reports_failure(monkeypatch):
    from backend.voice.tools import send_details

    monkeypatch.setattr(
        db, "get_lead_with_property", lambda lid: {"id": lid, "owner_email": None}
    )

    result = send_details("lead-1", "email")

    assert result["success"] is False
    assert result["results"]["email"]["reason"] == "no_email_on_file"


def test_send_details_both_channels(monkeypatch):
    from backend.voice.tools import send_details

    monkeypatch.setattr(
        db,
        "get_lead_with_property",
        lambda lid: {"id": lid, "owner_phone": "+12095551212", "owner_email": "m@example.com"},
    )
    monkeypatch.setattr("backend.alerts.sms.send_sms", lambda lid, b: {"success": True})
    monkeypatch.setattr("backend.alerts.email.send_email", lambda lid, s, b: {"success": True})

    result = send_details("lead-1", "both")

    assert sorted(result["sent"]) == ["email", "text"]


def test_send_details_missing_lead(monkeypatch):
    from backend.voice.tools import send_details

    monkeypatch.setattr(db, "get_lead_with_property", lambda lid: None)
    assert send_details("missing", "text")["reason"] == "lead_not_found"


def test_sophia_has_a_tool_for_every_promise_the_prompt_makes():
    from backend.voice.agent import load_system_prompt
    from backend.voice.tools import build_sophia_tool_schemas

    tools = build_sophia_tool_schemas(lead_id="lead-1", on_end_call=lambda d: None)
    names = {t.name for t in tools.standard_tools}

    assert "send_details" in names, "the prompt offers to text or email; she needs the tool"
    assert "send details tool" in load_system_prompt()
