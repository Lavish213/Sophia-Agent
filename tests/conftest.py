import os

import pytest

os.environ["SUPABASE_URL"] = "http://127.0.0.1:1"
os.environ["SUPABASE_SERVICE_KEY"] = "test-service-key"
os.environ["ANTHROPIC_API_KEY"] = "test-anthropic-key"
os.environ["DEEPGRAM_API_KEY"] = "test-deepgram-key"
os.environ["SIGNALWIRE_SIGNING_KEY"] = "test-signing-key-not-real"


@pytest.fixture(autouse=True)
def prevent_live_database_access(monkeypatch):
    from backend.lib import db

    def deny():
        raise RuntimeError("Unit tests must mock database access; live Supabase access is disabled")

    monkeypatch.setattr(db, "get_client", deny)


@pytest.fixture(autouse=True)
def legacy_webhook_unit_tests_use_explicit_auth_override():
    from backend.api.main import app
    from backend.voice.security import verify_signalwire_request

    app.dependency_overrides[verify_signalwire_request] = lambda: None
    yield
    app.dependency_overrides.pop(verify_signalwire_request, None)
