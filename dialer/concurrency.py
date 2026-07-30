from __future__ import annotations

from backend.lib import db
from backend.lib.config import get_settings


def has_capacity() -> bool:
    settings = get_settings()
    return db.count_active_calls() < settings.max_concurrent_outbound
