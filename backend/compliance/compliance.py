from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from loguru import logger

import backend.lib.db as db
from backend.lib.config import get_settings


@dataclass
class ComplianceResult:
    allowed: bool
    reason: str


def is_calling_hours(now: datetime | None = None) -> bool:
    import pytz

    settings = get_settings()
    pacific = pytz.timezone("America/Los_Angeles")
    check_time = (now or datetime.now(pacific)).astimezone(pacific)
    return settings.calling_hours_start <= check_time.hour < settings.calling_hours_end


class ComplianceEngine:
    def check_call_allowed(self, lead_id: str) -> ComplianceResult:
        try:
            lead = db.get_lead_with_property(lead_id)
            if not lead:
                return ComplianceResult(allowed=False, reason="lead_not_found")
            if lead.get("opted_out"):
                return ComplianceResult(allowed=False, reason="opted_out")
            if lead.get("dnc_blocked"):
                return ComplianceResult(allowed=False, reason="dnc_blocked")
            if not is_calling_hours():
                return ComplianceResult(allowed=False, reason="outside_hours")

            for phone in (lead.get("owner_phone"), lead.get("owner_phone_2")):
                if phone and db.is_on_dnc_list(phone):
                    logger.info("dnc_match lead_id={} phone={}", lead_id, phone)
                    return ComplianceResult(allowed=False, reason="dnc_list_match")

            return ComplianceResult(allowed=True, reason="ok")
        except Exception as e:
            logger.exception("compliance_check_failed lead_id={} error={}", lead_id, str(e))
            return ComplianceResult(allowed=False, reason="check_failed_blocking")

    def check_sms_allowed(self, lead_id: str) -> ComplianceResult:
        try:
            lead = db.get_lead_with_property(lead_id)
            if not lead:
                return ComplianceResult(allowed=False, reason="lead_not_found")
            if lead.get("opted_out"):
                return ComplianceResult(allowed=False, reason="opted_out")
            if lead.get("dnc_blocked"):
                return ComplianceResult(allowed=False, reason="dnc_blocked")
            return ComplianceResult(allowed=True, reason="ok")
        except Exception as e:
            logger.exception("sms_compliance_check_failed lead_id={} error={}", lead_id, str(e))
            return ComplianceResult(allowed=False, reason="check_failed_blocking")
