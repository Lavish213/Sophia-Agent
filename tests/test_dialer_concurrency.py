from backend.lib import db
from backend.lib.config import get_settings
from dialer.concurrency import has_capacity


def test_has_capacity_true_when_under_max(monkeypatch):
    monkeypatch.setenv("MAX_CONCURRENT_OUTBOUND", "3")
    get_settings.cache_clear()
    monkeypatch.setattr(db, "count_active_calls", lambda: 1)
    try:
        assert has_capacity() is True
    finally:
        get_settings.cache_clear()


def test_has_capacity_false_when_at_max(monkeypatch):
    monkeypatch.setenv("MAX_CONCURRENT_OUTBOUND", "3")
    get_settings.cache_clear()
    monkeypatch.setattr(db, "count_active_calls", lambda: 3)
    try:
        assert has_capacity() is False
    finally:
        get_settings.cache_clear()


def test_has_capacity_false_when_over_max(monkeypatch):
    monkeypatch.setenv("MAX_CONCURRENT_OUTBOUND", "3")
    get_settings.cache_clear()
    monkeypatch.setattr(db, "count_active_calls", lambda: 5)
    try:
        assert has_capacity() is False
    finally:
        get_settings.cache_clear()
