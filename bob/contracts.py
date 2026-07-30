from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

PHASE_TO_STAGE: dict[str, str] = {
    "VERIFY": "STAGE_1_QUALIFY",
    "LIGHT_DISCOVERY": "STAGE_2_DISCOVER",
    "QUALIFY": "STAGE_3_PRECLOSE",
    "NEXT_STEP": "STAGE_4_CLOSE",
    "WRAP": "STAGE_5_WRAP",
}

CHECKBOX_PRIORITY = [
    "right_person",
    "property_confirmed",
    "occupancy",
    "condition",
    "timeline",
    "motivation",
    "next_step",
]


@dataclass
class CallBrief:
    lead_id: str
    phase: str
    objective: str
    missing_box: str
    mood: str
    avoid: list[str] = field(default_factory=list)
    escalation_rules: list[str] = field(default_factory=list)
    opener_hint: str | None = None
    confidence: float = 0.65
    source: str = "system"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return {
            "lead_id": self.lead_id,
            "phase": self.phase,
            "objective": self.objective,
            "missing_box": self.missing_box,
            "mood": self.mood,
            "avoid": self.avoid,
            "escalation_rules": self.escalation_rules,
            "opener_hint": self.opener_hint,
            "confidence": self.confidence,
            "source": self.source,
            "created_at": self.created_at,
        }
