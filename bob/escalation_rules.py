from __future__ import annotations

_ALWAYS_ESCALATE = [
    "exact offer request",
    "stop calling or DNC request",
    "legal or lawsuit threat",
    "bankruptcy mention",
]

_SITUATION_ESCALATIONS: dict[str, list[str]] = {
    "preforeclosure": ["foreclosure legal question", "auction date question"],
    "pre_foreclosure": ["foreclosure legal question", "auction date question"],
    "probate": ["probate attorney question", "estate complexity"],
    "inherited_property": ["probate attorney question", "estate complexity"],
    "inherited": ["probate attorney question", "estate complexity"],
    "divorce": ["divorce attorney question", "court order question"],
}


def build_escalation_rules(intel_packet: dict, situation_label: str, seller_memory: dict) -> list[str]:
    rules = list(_ALWAYS_ESCALATE)

    sit = (situation_label or "").lower()
    for key, extras in _SITUATION_ESCALATIONS.items():
        if key in sit:
            for e in extras:
                if e not in rules:
                    rules.append(e)

    motivation = seller_memory.get("motivation_level")
    if motivation is not None and int(motivation) >= 8:
        rules.append("high motivation detected — human takeover ready")

    flags = (intel_packet or {}).get("conflict_flags") or []
    if flags:
        rules.append("intel conflict active — escalate before any offer discussion")

    competitors = seller_memory.get("competitor_mentions") or []
    if competitors:
        rules.append("mentions other buyers — flag for Alanzo immediately")

    compliance = (intel_packet or {}).get("compliance_context") or {}
    threshold = compliance.get("requires_human_approval_above")
    if threshold:
        rules.append(f"offer above ${int(threshold):,} requires operator approval")

    return rules
