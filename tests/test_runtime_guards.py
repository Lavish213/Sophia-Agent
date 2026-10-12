import base64
import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pipecat.frames.frames import EndWorkerFrame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection

from backend.lib import db
from backend.lib.config import get_settings
from backend.voice.agent import resolve_final_disposition
from backend.voice.opt_out import VoiceOptOutGuard, persist_stop, stop_requested
from backend.voice.security import issue_stream_token, verify_stream_token
from backend.voice.tools import book_appointment, request_owner_callback
from backend.voice.webhook import router


@pytest.fixture(autouse=True)
def settings_isolation():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def signed_client(monkeypatch):
    monkeypatch.setenv("PUBLIC_URL", "https://sophia.example.com")
    application = FastAPI()
    application.include_router(router, prefix="/api")
    return TestClient(application)


def test_unsigned_callback_is_denied(signed_client):
    assert signed_client.post("/api/voice/inbound", data={"CallSid": "call-1"}).status_code == 403


def test_signature_authorizes_only_unchanged_payload(signed_client):
    form = {"CallSid": "call-1", "From": "+12095550100"}
    message = "https://sophia.example.com/api/voice/inbound" + "".join(key + form[key] for key in sorted(form))
    signature = base64.b64encode(
        hmac.new(b"test-signing-key-not-real", message.encode(), hashlib.sha1).digest()
    ).decode()
    headers = {"x-signalwire-signature": signature}
    assert signed_client.post("/api/voice/inbound", data=form, headers=headers).status_code == 200
    changed = signed_client.post("/api/voice/inbound", data={**form, "From": "+12095550999"}, headers=headers)
    assert changed.status_code == 403


def test_missing_signing_configuration_fails_closed(signed_client, monkeypatch):
    monkeypatch.setenv("SIGNALWIRE_SIGNING_KEY", "")
    assert signed_client.post("/api/voice/inbound", data={}).status_code == 503


def test_stream_token_binds_call_and_denies_tampering():
    token = issue_stream_token({"call_sid": "call-1", "lead_id": "lead-1"})
    assert verify_stream_token(token, "call-1")["lead_id"] == "lead-1"
    assert verify_stream_token(token, "call-2") is None
    assert verify_stream_token(token + "x", "call-1") is None


def test_stream_token_expires(monkeypatch):
    from backend.voice import security

    monkeypatch.setattr(security.time, "time", lambda: 1000)
    token = issue_stream_token({"call_sid": "call-1"})
    monkeypatch.setattr(security.time, "time", lambda: 1300)
    assert verify_stream_token(token, "call-1") is None


@pytest.mark.parametrize("token", ["", "...", "not-base64.invalid", "秘密", "x" * 5000])
def test_malformed_stream_tokens_fail_closed(token):
    assert verify_stream_token(token, "call-1") is None


@pytest.mark.parametrize(
    "text", ["Stop calling me", "Take me off your list", "Don't call again", "No me llames", "Stop."]
)
def test_stop_requests(text):
    assert stop_requested(text)


@pytest.mark.parametrize(
    "text", ["What is a stop loss?", "Can we stop by Friday?", "I didn't understand that", "My house needs repairs"]
)
def test_unrelated_words_are_not_opt_outs(text):
    assert not stop_requested(text)


async def test_failed_suppression_does_not_claim_removal(monkeypatch):
    monkeypatch.setattr(db, "suppress_voice_contact", lambda *args: False)
    context = {"lead_id": "lead-1", "lead": {"owner_phone": "+12095550100"}}
    assert "couldn't confirm" in await persist_stop(context)
    assert context["stop_requested"]


async def test_database_outage_ends_sales_conversation(monkeypatch):
    def fail(*args):
        raise RuntimeError("synthetic database outage")

    monkeypatch.setattr(db, "suppress_voice_contact", fail)
    context = {"lead_id": "lead-1", "lead": {"owner_phone": "+12095550100"}}
    dispositions = []
    guard = VoiceOptOutGuard(context, dispositions.append)
    guard.push_frame = AsyncMock()
    guard.worker = type("Worker", (), {"queue_frames": AsyncMock()})()
    await guard.process_frame(TranscriptionFrame("Stop calling me", "seller", "now"), FrameDirection.DOWNSTREAM)
    assert dispositions == ["OPTED_OUT"]
    frames = guard.worker.queue_frames.call_args.args[0]
    assert "couldn't confirm" in frames[0].text
    assert isinstance(frames[-1], EndWorkerFrame)
    guard.push_frame.assert_not_awaited()


def test_post_call_classification_cannot_override_stop():
    assert resolve_final_disposition({"disposition": "HOT"}, "OPTED_OUT", True) == "OPTED_OUT"


def test_past_and_ambiguous_booking_times_never_write(monkeypatch):
    writes = []
    monkeypatch.setattr(db, "update_lead_appointment", lambda *args: writes.append(args))
    assert book_appointment("lead", "2020-01-01T15:00:00Z")["reason"] == "appointment_must_be_in_future"
    assert book_appointment("lead", "2099-01-01T15:00:00")["reason"] == "timezone_required"
    assert writes == []


def test_unacknowledged_action_writes_do_not_claim_success(monkeypatch):
    monkeypatch.setattr(db, "update_lead_appointment", lambda *args: False)
    monkeypatch.setattr(db, "update_lead_fields", lambda *args: False)
    future = (datetime.now(UTC) + timedelta(days=3)).isoformat()
    assert book_appointment("missing", future)["reason"] == "appointment_not_persisted"
    assert request_owner_callback("missing", "human requested")["reason"] == "callback_not_persisted"
