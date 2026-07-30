from backend.lib.config import get_settings
from backend.voice.webhook import build_connect_laml, build_stream_url


def test_build_stream_url_converts_https_to_wss(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("PUBLIC_URL", "https://sophia.example.com")
    get_settings.cache_clear()
    try:
        url = build_stream_url()
        assert url == "wss://sophia.example.com/api/voice/stream"
    finally:
        get_settings.cache_clear()


def test_build_connect_laml_includes_stream_and_params(monkeypatch):
    monkeypatch.setenv("PUBLIC_URL", "https://sophia.example.com")
    get_settings.cache_clear()
    try:
        laml = build_connect_laml({"from_number": "+12095551212", "to_number": "+12098814144"})
        assert "<Connect><Stream" in laml
        assert "wss://sophia.example.com/api/voice/stream" in laml
        assert 'name="from_number" value="+12095551212"' in laml
        assert 'name="to_number" value="+12098814144"' in laml
    finally:
        get_settings.cache_clear()


def test_build_connect_laml_omits_empty_params(monkeypatch):
    monkeypatch.setenv("PUBLIC_URL", "https://sophia.example.com")
    get_settings.cache_clear()
    try:
        laml = build_connect_laml({"from_number": "", "lead_id": "lead-1"})
        assert "from_number" not in laml
        assert 'name="lead_id" value="lead-1"' in laml
    finally:
        get_settings.cache_clear()


def test_build_connect_laml_for_outbound_carries_lead_id(monkeypatch):
    monkeypatch.setenv("PUBLIC_URL", "https://sophia.example.com")
    get_settings.cache_clear()
    try:
        laml = build_connect_laml({"lead_id": "lead-42"})
        assert 'name="lead_id" value="lead-42"' in laml
    finally:
        get_settings.cache_clear()
