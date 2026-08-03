from __future__ import annotations

from datetime import UTC, datetime

BASE_WEIGHT = 1.0
MAX_PRIORITY = 100.0


def _hours_since(timestamp: str | None, now: datetime) -> float | None:
    if not timestamp:
        return None
    try:
        parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (now - parsed).total_seconds() / 3600.0


def waiting_on_a_human(lead: dict, now: datetime | None = None) -> bool:
    if lead.get("priority_callback") or lead.get("escalated"):
        return True

    reference = now or datetime.now(UTC)
    due_in = _hours_since(lead.get("callback_scheduled_at"), reference)
    return due_in is not None and due_in >= 0


def score_lead(lead: dict, now: datetime | None = None) -> tuple[float, list[str]]:
    reference = now or datetime.now(UTC)
    prop = lead.get("properties") or {}

    score = float(prop.get("distress_score") or 0)
    reasons = [f"distress {int(score)}"]

    if lead.get("priority_callback") or lead.get("escalated"):
        score += 40
        reasons.append("they asked for a callback")

    if lead.get("appointment_at"):
        score += 10
        reasons.append("walkthrough booked")

    motivation = lead.get("motivation_level")
    if motivation is not None:
        bonus = float(motivation) * 3
        score += bonus
        reasons.append(f"motivation {motivation}/10")

    if lead.get("is_hot_lead"):
        score += 20
        reasons.append("marked hot")

    timeline = (lead.get("timeline_urgency") or "").lower()
    if timeline and any(word in timeline for word in ("asap", "immediate", "urgent", "30 day")):
        score += 15
        reasons.append("urgent timeline")

    attempts = lead.get("call_attempts") or 0
    if attempts == 0:
        score += 10
        reasons.append("never tried")
    elif attempts >= 5:
        score -= 20
        reasons.append(f"{attempts} attempts already")
    elif attempts >= 3:
        score -= 8
        reasons.append(f"{attempts} attempts already")

    voicemails = lead.get("voicemail_count") or 0
    if voicemails >= 3:
        score -= 15
        reasons.append("voicemail cap reached")

    confidence = prop.get("data_confidence")
    if confidence is not None and float(confidence) < 0.6:
        score -= 10
        reasons.append("list data looks unreliable")

    hours = _hours_since(lead.get("last_called_at"), reference)
    if hours is not None and hours > 168:
        score += 5
        reasons.append("gone cold, worth another try")

    if lead.get("callback_scheduled_at"):
        due_in = _hours_since(lead.get("callback_scheduled_at"), reference)
        if due_in is not None and due_in >= 0:
            score += 30
            reasons.append("callback is due")

    score = max(0.0, min(MAX_PRIORITY, score))
    return round(score, 1), reasons


def rank_leads(leads: list[dict], now: datetime | None = None) -> list[dict]:
    scored = []
    for lead in leads:
        score, reasons = score_lead(lead, now)
        enriched = dict(lead)
        enriched["call_priority"] = score
        enriched["priority_reasons"] = reasons
        enriched["waiting_on_human"] = waiting_on_a_human(lead, now)
        scored.append(enriched)

    scored.sort(
        key=lambda entry: (entry["waiting_on_human"], entry["call_priority"]),
        reverse=True,
    )
    return scored
