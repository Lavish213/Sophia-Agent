from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from backend.lib import db
from backend.lib.config import get_settings
from backend.scout.intake import normalize_phone

_BASE_V1 = "https://api.batchdata.com/api/v1"
_BASE_V3 = "https://api.batchdata.com/api/v3"
_TIMEOUT = 30

_MOBILE_TYPES = {"mobile", "cell", "wireless"}


def is_configured() -> bool:
    return bool(get_settings().batchdata_api_key)


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {get_settings().batchdata_api_key}",
        "Content-Type": "application/json",
    }


def _post(url: str, body: dict[str, Any]) -> dict[str, Any]:
    with httpx.Client(timeout=_TIMEOUT) as client:
        response = client.post(url, json=body, headers=_headers())
        response.raise_for_status()
        return response.json()


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _collect_people(result: dict[str, Any]) -> list[dict]:
    for key in ("persons", "person", "people", "contacts"):
        people = _as_list(result.get(key))
        if people:
            return [p for p in people if isinstance(p, dict)]
    return [result]


def _phone_entries(person: dict) -> list[dict]:
    for key in ("phoneNumbers", "phones", "phone_numbers"):
        entries = _as_list(person.get(key))
        if entries:
            return [{"number": e} if isinstance(e, str) else e for e in entries]
    return []


def _email_entries(person: dict) -> list[str]:
    for key in ("emails", "emailAddresses", "email_addresses"):
        entries = _as_list(person.get(key))
        if entries:
            out = []
            for entry in entries:
                if isinstance(entry, str):
                    out.append(entry)
                elif isinstance(entry, dict):
                    value = entry.get("email") or entry.get("address") or entry.get("value")
                    if value:
                        out.append(value)
            return out
    single = person.get("email")
    return [single] if isinstance(single, str) else []


def _person_name(person: dict) -> str | None:
    name = person.get("name")
    if isinstance(name, str):
        return name
    if isinstance(name, dict):
        parts = [name.get("first"), name.get("last")]
        joined = " ".join(p for p in parts if p)
        return joined or None
    first = person.get("firstName") or person.get("first_name")
    last = person.get("lastName") or person.get("last_name")
    joined = " ".join(p for p in [first, last] if p)
    return joined or None


def extract_contacts(result: dict[str, Any] | None) -> dict:
    if not result:
        return {"phones": [], "emails": [], "name": None}

    phones: list[dict] = []
    emails: list[str] = []
    name: str | None = None

    for person in _collect_people(result):
        if not name:
            name = _person_name(person)
        for entry in _phone_entries(person):
            raw = entry.get("number") or entry.get("phone") or entry.get("value")
            normalized = normalize_phone(raw if isinstance(raw, str) else None)
            if not normalized:
                continue
            if any(p["phone"] == normalized for p in phones):
                continue
            line_type = str(entry.get("type") or entry.get("lineType") or "").lower()
            phones.append({
                "phone": normalized,
                "is_mobile": line_type in _MOBILE_TYPES,
                "dnc": bool(entry.get("dnc", False)),
                "reachable": bool(entry.get("reachable", True)),
            })
        for email in _email_entries(person):
            cleaned = email.strip().lower()
            if cleaned and cleaned not in emails:
                emails.append(cleaned)

    phones.sort(key=lambda p: (p["dnc"], not p["is_mobile"]))
    return {"phones": phones, "emails": emails, "name": name}


def skip_trace_address(address: str, city: str | None, state: str, zip_code: str | None) -> dict[str, Any]:
    if not is_configured():
        logger.warning("skip_trace_not_configured")
        return {}

    body = {
        "requests": [
            {
                "propertyAddress": {
                    "street": address,
                    "city": city or "",
                    "state": state,
                    "zip": zip_code or "",
                }
            }
        ],
    }

    try:
        data = _post(f"{_BASE_V3}/property/skip-trace", body)
        results = (data.get("result") or {}).get("data") or data.get("results") or []
        results = _as_list(results)
        if not results:
            logger.info("skip_trace_no_result address={}", address)
            return {}
        return results[0] if isinstance(results[0], dict) else {}
    except Exception as e:
        logger.error("skip_trace_failed address={} error={}", address, str(e))
        return {}


def is_phone_blocked(phone: str) -> bool:
    if not is_configured():
        return False
    for endpoint, field in (("phone/dnc", "dnc"), ("phone/tcpa", "tcpa")):
        try:
            response = _post(f"{_BASE_V1}/{endpoint}", {"requests": [phone]})
            rows = (response.get("results") or {}).get("phoneNumbers") or []
            if rows and bool(rows[0].get(field, False)):
                logger.info("skiptrace_phone_blocked phone={} reason={}", phone, field)
                return True
        except Exception as e:
            logger.warning("skiptrace_scrub_failed phone={} endpoint={} error={}", phone, endpoint, str(e))
            return True
    return False


def enrich_lead(lead_id: str) -> dict:
    if not is_configured():
        return {"success": False, "reason": "not_configured"}

    lead = db.get_lead_with_property(lead_id)
    if not lead:
        return {"success": False, "reason": "lead_not_found"}

    if lead.get("owner_phone"):
        return {"success": False, "reason": "already_has_phone"}

    prop = lead.get("properties") or {}
    address = prop.get("address")
    if not address or address.startswith("Address needed"):
        return {"success": False, "reason": "no_usable_address"}

    result = skip_trace_address(address, prop.get("city"), prop.get("state") or "CA", prop.get("zip"))
    contacts = extract_contacts(result)

    usable = [p for p in contacts["phones"] if not p["dnc"]]
    if not usable:
        logger.info("enrich_lead_no_usable_phone lead_id={}", lead_id)
        return {"success": False, "reason": "no_usable_phone"}

    chosen = usable[0]["phone"]
    if is_phone_blocked(chosen):
        db.add_to_dnc_list(chosen, "batchdata dnc/tcpa scrub")
        return {"success": False, "reason": "phone_blocked"}

    updates: dict = {"owner_phone": chosen}
    if contacts["emails"] and not lead.get("owner_email"):
        updates["owner_email"] = contacts["emails"][0]
    db.update_lead_fields(lead_id, updates)

    db.insert_contact({
        "property_id": lead.get("property_id"),
        "name": contacts["name"],
        "phone": chosen,
        "email": contacts["emails"][0] if contacts["emails"] else None,
        "source": "skiptrace",
    })

    logger.info("enrich_lead_success lead_id={} phone={}", lead_id, chosen)
    return {"success": True, "reason": "enriched", "phone": chosen, "email": updates.get("owner_email")}
