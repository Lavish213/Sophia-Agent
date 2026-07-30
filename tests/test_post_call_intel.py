from dataclasses import dataclass, field
from typing import Any

import anthropic

from backend.lib import db
from backend.voice.post_call_intel import apply_call_intel, extract_call_intel, run_post_call_intel


@dataclass
class _FakeBlock:
    type: str
    name: str
    input: dict


@dataclass
class _FakeResponse:
    content: list


@dataclass
class _FakeMessages:
    response: Any

    def create(self, **kwargs):
        return self.response


@dataclass
class _FakeAnthropicClient:
    response: Any
    messages: Any = field(init=False)

    def __init__(self, api_key, response):
        self.messages = _FakeMessages(response)


def _sample_transcript():
    return [
        {"speaker": "sophia", "text": "Hey, is this Maria?"},
        {"speaker": "seller", "text": "Yeah this is Maria."},
        {"speaker": "sophia", "text": "Would you be open to selling the property on Main Street?"},
        {"speaker": "seller", "text": "Actually yeah, we're behind on payments and need to move fast."},
    ]


def test_extract_call_intel_returns_none_for_empty_transcript():
    assert extract_call_intel([]) is None


def test_extract_call_intel_parses_tool_use_block(monkeypatch):
    intel = {
        "disposition": "HOT",
        "motivation_level": 9,
        "timeline_urgency": "asap",
        "price_floor_dollars": 150000,
        "objections": [],
        "call_summary": "Behind on payments, wants to sell fast.",
        "next_best_action": "book_walkthrough",
    }
    fake_response = _FakeResponse(content=[_FakeBlock(type="tool_use", name="record_call_intel", input=intel)])

    def _fake_client(api_key):
        return _FakeAnthropicClient(api_key, fake_response)

    monkeypatch.setattr(anthropic, "Anthropic", _fake_client)

    result = extract_call_intel(_sample_transcript())
    assert result["disposition"] == "HOT"
    assert result["motivation_level"] == 9


def test_apply_call_intel_writes_call_and_lead_fields(monkeypatch):
    call_updates = {}
    lead_updates = {}
    monkeypatch.setattr(db, "update_call_fields", lambda call_id, fields: call_updates.update(fields))
    monkeypatch.setattr(db, "update_lead_fields", lambda lead_id, fields: lead_updates.update(fields))

    intel = {
        "disposition": "HOT",
        "motivation_level": 9,
        "timeline_urgency": "asap",
        "price_floor_dollars": 150000,
        "objections": ["wants to think about it"],
        "call_summary": "Behind on payments.",
        "next_best_action": "book_walkthrough",
    }

    apply_call_intel("call-1", "lead-1", intel)

    assert call_updates["call_disposition"] == "HOT"
    assert lead_updates["motivation_level"] == 9
    assert lead_updates["price_floor"] == 15000000
    assert lead_updates["is_hot_lead"] is True


def test_apply_call_intel_skips_lead_write_without_lead_id(monkeypatch):
    called = {"count": 0}

    def _bump(lead_id, fields):
        called["count"] += 1

    monkeypatch.setattr(db, "update_call_fields", lambda call_id, fields: None)
    monkeypatch.setattr(db, "update_lead_fields", _bump)

    intel = {
        "disposition": "COLD",
        "motivation_level": 2,
        "call_summary": "not interested",
        "next_best_action": "drip",
    }
    apply_call_intel("call-1", None, intel)

    assert called["count"] == 0


def test_run_post_call_intel_handles_errors_without_raising(monkeypatch):
    monkeypatch.setattr(db, "get_transcript_chunks", lambda call_id: (_ for _ in ()).throw(RuntimeError("db down")))
    run_post_call_intel("call-1", "lead-1")
