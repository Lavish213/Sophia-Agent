from __future__ import annotations

_ALWAYS_AVOID = ["pricing", "legal advice"]

_SITUATION_AVOIDS: dict[str, list[str]] = {
    "preforeclosure": ["foreclosure guidance", "auction timeline details"],
    "pre_foreclosure": ["foreclosure guidance", "auction timeline details"],
    "probate": ["probate advice", "estate tax guidance"],
    "inherited_property": ["probate advice", "estate tax guidance"],
    "inherited": ["probate advice", "estate tax guidance"],
    "divorce": ["legal separation advice"],
}

_CREATIVE_FINANCE_OK = frozenset([
    "pre_foreclosure", "preforeclosure", "free_and_clear", "absentee_owner",
])


def build_avoidances(
    intel_packet: dict,
    situation_label: str,
    call_count: int = 0,
    property_row: dict | None = None,
) -> list[str]:
    avoid = list(_ALWAYS_AVOID)

    sit = (situation_label or "").lower()
    for key, extras in _SITUATION_AVOIDS.items():
        if key in sit:
            for e in extras:
                if e not in avoid:
                    avoid.append(e)

    distress = ""
    profile = (intel_packet or {}).get("property_profile") or {}
    if isinstance(profile.get("distress_type"), dict):
        distress = (profile["distress_type"].get("value") or "").lower()
    elif isinstance(profile.get("distress_type"), str):
        distress = profile["distress_type"].lower()

    row = property_row or {}
    if not distress:
        distress = (row.get("distress_type") or "").lower()

    creative_ok = (
        any(s in distress for s in _CREATIVE_FINANCE_OK)
        or any(s in sit for s in _CREATIVE_FINANCE_OK)
        or bool(row.get("free_and_clear"))
        or bool(row.get("absentee_owner"))
    )
    if not creative_ok:
        avoid.append("creative finance discussion")

    strategy = (intel_packet or {}).get("strategy_context") or {}
    for item in strategy.get("do_not_pitch") or []:
        if item not in avoid:
            avoid.append(item)

    flags = (intel_packet or {}).get("conflict_flags") or []
    if flags:
        avoid.append("offer and strategy discussion")

    return avoid
