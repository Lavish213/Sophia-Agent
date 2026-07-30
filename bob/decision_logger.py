from __future__ import annotations

from datetime import UTC, datetime

from loguru import logger

from backend.lib import db


def log_decision(
    lead_id: str,
    decision_type: str,
    inputs: dict,
    output: dict,
    reason_codes: list[str],
    confidence: float,
    version: str = "1.0",
) -> None:
    record = {
        "lead_id": lead_id,
        "decision_type": decision_type,
        "inputs_used": inputs,
        "output": output,
        "reason_codes": reason_codes,
        "confidence": confidence,
        "version": version,
        "created_at": datetime.now(UTC).isoformat(),
    }
    try:
        db.save_decision_record(record)
        logger.debug("decision_logged lead_id={} type={}", lead_id, decision_type)
    except Exception as e:
        logger.warning("decision_logger_failed lead_id={} type={} error={}", lead_id, decision_type, str(e))
