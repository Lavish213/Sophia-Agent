from xml.etree import ElementTree

from fastapi.testclient import TestClient

from backend.api.main import app
from backend.lib import db
from backend.lib.config import get_settings
from backend.voice import voicemail

client = TestClient(app)

_LEAD_ID = "11111111-1111-1111-1111-111111111111"


def _configure(monkeypatch):
    monkeypatch.setenv("PUBLIC_URL", "https://sophia.example.com")
    monkeypatch.setenv("BUSINESS_NAME", "San Joaquin House Buyers")
    monkeypatch.setenv("AGENT_NAME", "Sophia")
    monkeypatch.setenv("AGENT_PHONE", "+12095550100")
    get_settings.cache_clear()


def _parse(response):
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/xml")
    return ElementTree.fromstring(response.text)


def _stub_voicemail_writes(monkeypatch):
    monkeypatch.setattr(db, "get_call_by_signalwire_sid", lambda sid: {"id": "call-1"})
    monkeypatch.setattr(db, "update_call_fields", lambda cid, f: None)
    monkeypatch.setattr(db, "insert_call_event", lambda *a, **k: None)
    monkeypatch.setattr(db, "update_lead_call_outcome", lambda lid, o: None)
    monkeypatch.setattr(db, "update_lead_fields", lambda lid, f: None)


def test_inbound_call_returns_parseable_stream_laml(monkeypatch):
    _configure(monkeypatch)
    try:
        response = client.post(
            "/api/voice/inbound",
            data={"From": "+12095551212", "To": "+12095550100", "CallSid": "CA_inbound_1"},
        )
        root = _parse(response)

        stream = root.find("./Connect/Stream")
        assert stream is not None, "SignalWire needs a Connect/Stream to reach the agent"
        assert stream.attrib["url"] == "wss://sophia.example.com/api/voice/stream"

        params = {p.attrib["name"]: p.attrib["value"] for p in stream.findall("Parameter")}
        assert params["from_number"] == "+12095551212"
    finally:
        get_settings.cache_clear()


def test_outbound_human_answer_connects_the_live_agent(monkeypatch):
    _configure(monkeypatch)
    try:
        response = client.post(
            f"/api/voice/outbound/{_LEAD_ID}",
            data={"CallSid": "CA_out_1", "AnsweredBy": "human"},
        )
        root = _parse(response)

        stream = root.find("./Connect/Stream")
        assert stream is not None
        params = {p.attrib["name"]: p.attrib["value"] for p in stream.findall("Parameter")}
        assert params["lead_id"] == _LEAD_ID
        assert root.find("./Say") is None, "a human must never get the recorded voicemail"
    finally:
        get_settings.cache_clear()


def test_outbound_with_no_amd_result_still_connects(monkeypatch):
    _configure(monkeypatch)
    try:
        response = client.post(f"/api/voice/outbound/{_LEAD_ID}", data={"CallSid": "CA_out_2"})
        root = _parse(response)
        assert root.find("./Connect/Stream") is not None
    finally:
        get_settings.cache_clear()


def test_outbound_voicemail_speaks_a_message_then_hangs_up(monkeypatch):
    _configure(monkeypatch)
    try:
        monkeypatch.setattr(
            db,
            "get_lead_with_property",
            lambda lid: {"id": lid, "voicemail_count": 0, "properties": {"owner_name": "Maria Gonzalez"}},
        )
        _stub_voicemail_writes(monkeypatch)

        response = client.post(
            f"/api/voice/outbound/{_LEAD_ID}",
            data={"CallSid": "CA_out_3", "AnsweredBy": "machine_end_beep"},
        )
        root = _parse(response)

        say = root.find("./Say")
        assert say is not None, "voicemail must actually speak something"
        assert "Maria" in say.text
        assert "San Joaquin House Buyers" in say.text
        assert "2 0 9" in say.text, "callback number must be spoken digit by digit"
        assert root.find("./Hangup") is not None
        assert root.find("./Connect") is None, "must not stream audio into a voicemail box"
    finally:
        get_settings.cache_clear()


def test_outbound_machine_start_hangs_up_without_talking_over_the_greeting(monkeypatch):
    _configure(monkeypatch)
    try:
        response = client.post(
            f"/api/voice/outbound/{_LEAD_ID}",
            data={"CallSid": "CA_out_4", "AnsweredBy": "machine_start"},
        )
        root = _parse(response)
        assert root.find("./Hangup") is not None
        assert root.find("./Say") is None
        assert root.find("./Connect") is None
    finally:
        get_settings.cache_clear()


def test_outbound_fax_hangs_up(monkeypatch):
    _configure(monkeypatch)
    try:
        response = client.post(
            f"/api/voice/outbound/{_LEAD_ID}",
            data={"CallSid": "CA_out_5", "AnsweredBy": "fax"},
        )
        root = _parse(response)
        assert root.find("./Hangup") is not None
        assert root.find("./Connect") is None
    finally:
        get_settings.cache_clear()


def test_outbound_stops_leaving_voicemails_once_capped(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setenv("MAX_VOICEMAILS_PER_LEAD", "3")
    get_settings.cache_clear()
    try:
        monkeypatch.setattr(
            db, "get_lead_with_property", lambda lid: {"id": lid, "voicemail_count": 3, "properties": {}}
        )

        def _should_not_record(*args, **kwargs):
            raise AssertionError("recorded a voicemail past the cap")

        monkeypatch.setattr(voicemail, "record_voicemail_left", _should_not_record)

        response = client.post(
            f"/api/voice/outbound/{_LEAD_ID}",
            data={"CallSid": "CA_out_6", "AnsweredBy": "machine_end_beep"},
        )
        root = _parse(response)
        assert root.find("./Hangup") is not None
        assert root.find("./Say") is None
    finally:
        get_settings.cache_clear()


def test_voicemail_script_escapes_a_name_that_would_break_the_xml(monkeypatch):
    _configure(monkeypatch)
    try:
        monkeypatch.setattr(
            db,
            "get_lead_with_property",
            lambda lid: {"id": lid, "voicemail_count": 0, "properties": {"owner_name": "Tom&<Jerry> Smith"}},
        )
        _stub_voicemail_writes(monkeypatch)

        response = client.post(
            f"/api/voice/outbound/{_LEAD_ID}",
            data={"CallSid": "CA_out_7", "AnsweredBy": "machine_end_beep"},
        )
        assert "&amp;" in response.text, "raw ampersand would make SignalWire reject the LaML"
        root = _parse(response)
        assert "Tom&<Jerry>" in root.find("./Say").text
    finally:
        get_settings.cache_clear()


def test_voicemail_message_is_short_enough_to_not_get_cut_off(monkeypatch):
    _configure(monkeypatch)
    try:
        for attempt in (1, 2, 3):
            script = voicemail.build_voicemail_script(None, attempt)
            words = len(script.split())
            assert words < 90, f"attempt {attempt} voicemail is {words} words, too long to hold attention"
    finally:
        get_settings.cache_clear()
