from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import lru_cache

from loguru import logger

from backend.lib.config import get_settings
from supabase import Client, create_client


@lru_cache(maxsize=1)
def get_client() -> Client:
    settings = get_settings()
    client = create_client(settings.supabase_url, settings.supabase_service_key)
    logger.info("supabase_client_initialized")
    return client


def _now() -> str:
    return datetime.now(UTC).isoformat()


def upsert_property(data: dict) -> str | None:
    client = get_client()
    response = client.table("properties").upsert(data, on_conflict="apn").execute()
    property_id = response.data[0]["id"] if response.data else None
    logger.debug("upsert_property apn={} id={}", data.get("apn"), property_id)
    return property_id


def get_property_by_id(property_id: str) -> dict | None:
    client = get_client()
    response = client.table("properties").select("*").eq("id", property_id).limit(1).execute()
    return response.data[0] if response.data else None


def get_properties_by_score(min_score: int) -> list[dict]:
    client = get_client()
    response = (
        client.table("properties")
        .select("*")
        .gte("distress_score", min_score)
        .order("distress_score", desc=True)
        .execute()
    )
    return response.data


def insert_contact(data: dict) -> None:
    client = get_client()
    client.table("contacts").insert(data).execute()
    logger.debug("insert_contact property_id={}", data.get("property_id"))


def get_contacts_for_property(property_id: str) -> list[dict]:
    client = get_client()
    response = client.table("contacts").select("*").eq("property_id", property_id).execute()
    return response.data


def get_or_create_lead(property_id: str) -> dict:
    client = get_client()
    existing = (
        client.table("leads")
        .select("*")
        .eq("property_id", property_id)
        .limit(1)
        .execute()
    )
    if existing.data:
        return existing.data[0]
    response = client.table("leads").insert({"property_id": property_id, "stage": "new"}).execute()
    lead = response.data[0]
    logger.info("lead_created property_id={} lead_id={}", property_id, lead["id"])
    return lead


def get_lead_by_id(lead_id: str) -> dict | None:
    client = get_client()
    response = client.table("leads").select("*").eq("id", lead_id).limit(1).execute()
    return response.data[0] if response.data else None


def get_lead_with_property(lead_id: str) -> dict | None:
    client = get_client()
    response = (
        client.table("leads")
        .select("*, properties(*)")
        .eq("id", lead_id)
        .limit(1)
        .execute()
    )
    if not response.data:
        return None
    lead = response.data[0]
    if isinstance(lead.get("properties"), list):
        lead["properties"] = lead["properties"][0] if lead["properties"] else {}
    return lead


def get_lead_by_owner_phone(phone: str) -> dict | None:
    client = get_client()
    response = (
        client.table("leads")
        .select("*, properties(*)")
        .eq("owner_phone", phone)
        .limit(1)
        .execute()
    )
    if not response.data:
        return None
    lead = response.data[0]
    if isinstance(lead.get("properties"), list):
        lead["properties"] = lead["properties"][0] if lead["properties"] else {}
    return lead


def get_leads_needing_skiptrace(limit: int = 25) -> list[dict]:
    client = get_client()
    response = (
        client.table("leads")
        .select("id, property_id, owner_phone")
        .is_("owner_phone", "null")
        .eq("dnc_blocked", False)
        .eq("opted_out", False)
        .not_.in_("stage", ["closed", "dead"])
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return response.data


def get_lead_by_owner_email(email: str) -> dict | None:
    client = get_client()
    response = (
        client.table("leads")
        .select("*, properties(*)")
        .eq("owner_email", email)
        .limit(1)
        .execute()
    )
    if not response.data:
        return None
    lead = response.data[0]
    if isinstance(lead.get("properties"), list):
        lead["properties"] = lead["properties"][0] if lead["properties"] else {}
    return lead


def list_leads(stage: str | None = None, limit: int = 50) -> list[dict]:
    client = get_client()
    query = client.table("leads").select("*, properties(address, distress_score, estimated_arv, mao)")
    if stage:
        query = query.eq("stage", stage)
    response = query.order("updated_at", desc=True).limit(limit).execute()
    return response.data


def update_lead_stage(lead_id: str, stage: str) -> None:
    client = get_client()
    client.table("leads").update({"stage": stage, "updated_at": _now()}).eq("id", lead_id).execute()
    logger.info("update_lead_stage lead_id={} stage={}", lead_id, stage)


def update_lead_fields(lead_id: str, fields: dict) -> None:
    if not fields:
        return
    client = get_client()
    data = dict(fields)
    data["updated_at"] = _now()
    client.table("leads").update(data).eq("id", lead_id).execute()
    logger.debug("update_lead_fields lead_id={} fields={}", lead_id, list(fields.keys()))


def get_leads_for_outbound(min_score: int = 50, limit: int = 25, reattempt_hours: int = 72) -> list[dict]:
    client = get_client()
    cutoff = (datetime.now(UTC) - timedelta(hours=reattempt_hours)).isoformat()
    response = (
        client.table("leads")
        .select("*, properties(*)")
        .eq("opted_out", False)
        .eq("callable", True)
        .eq("dnc_blocked", False)
        .not_.in_("stage", ["closed", "dead"])
        .not_.is_("owner_phone", "null")
        .or_(f"last_called_at.lte.{cutoff},last_called_at.is.null")
        .order("last_called_at", desc=False, nullsfirst=True)
        .limit(max(limit * 20, 200))
        .execute()
    )
    results = [
        r for r in response.data
        if (r.get("properties") or {}).get("distress_score", 0) >= min_score
        and r.get("owner_phone")
    ]
    results.sort(
        key=lambda r: (
            bool(r.get("waiting_on_human")),
            float(r.get("call_priority") or 0),
            (r.get("properties") or {}).get("distress_score", 0),
        ),
        reverse=True,
    )
    return results[:limit]


def update_lead_call_outcome(lead_id: str, outcome: str) -> None:
    client = get_client()
    current = client.table("leads").select("call_attempts").eq("id", lead_id).limit(1).execute()
    attempts = (current.data[0].get("call_attempts") or 0) + 1 if current.data else 1
    client.table("leads").update({
        "last_called_at": _now(),
        "call_attempts": attempts,
        "last_call_outcome": outcome,
        "updated_at": _now(),
    }).eq("id", lead_id).execute()
    logger.info("update_lead_call_outcome lead_id={} outcome={}", lead_id, outcome)


def update_lead_appointment(lead_id: str, appointment_at: str) -> None:
    client = get_client()
    client.table("leads").update({
        "appointment_at": appointment_at,
        "stage": "walkthrough_booked",
        "updated_at": _now(),
    }).eq("id", lead_id).execute()
    logger.info("update_lead_appointment lead_id={} at={}", lead_id, appointment_at)


def insert_call(data: dict) -> str | None:
    client = get_client()
    response = client.table("calls").insert(data).execute()
    call_id = response.data[0]["id"] if response.data else None
    logger.info("insert_call lead_id={} call_id={}", data.get("lead_id"), call_id)
    return call_id


def update_call_fields(call_id: str, fields: dict) -> None:
    if not fields:
        return
    client = get_client()
    client.table("calls").update(fields).eq("id", call_id).execute()
    logger.debug("update_call_fields call_id={} fields={}", call_id, list(fields.keys()))


def get_call_by_id(call_id: str) -> dict | None:
    client = get_client()
    response = client.table("calls").select("*").eq("id", call_id).limit(1).execute()
    return response.data[0] if response.data else None


def get_call_by_signalwire_sid(signalwire_call_id: str) -> dict | None:
    client = get_client()
    response = (
        client.table("calls")
        .select("*")
        .eq("signalwire_call_id", signalwire_call_id)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def mark_call_terminal_if_unset(signalwire_call_id: str, disposition: str) -> bool:
    client = get_client()
    response = (
        client.table("calls")
        .update({"call_disposition": disposition, "ended_at": _now()})
        .eq("signalwire_call_id", signalwire_call_id)
        .is_("call_disposition", "null")
        .execute()
    )
    updated = bool(response.data)
    if updated:
        logger.info("call_marked_terminal signalwire_call_id={} disposition={}", signalwire_call_id, disposition)
    return updated


def mark_followup_sent_if_unset(call_id: str) -> bool:
    client = get_client()
    response = (
        client.table("calls")
        .update({"followup_sent": True})
        .eq("id", call_id)
        .eq("followup_sent", False)
        .execute()
    )
    return bool(response.data)


def count_active_calls(max_age_minutes: int = 30) -> int:
    client = get_client()
    cutoff = (datetime.now(UTC) - timedelta(minutes=max_age_minutes)).isoformat()
    response = (
        client.table("calls")
        .select("id", count="exact")
        .is_("ended_at", "null")
        .gte("created_at", cutoff)
        .execute()
    )
    return response.count or 0


def get_calls_for_lead(lead_id: str) -> list[dict]:
    client = get_client()
    response = (
        client.table("calls")
        .select("*")
        .eq("lead_id", lead_id)
        .order("created_at", desc=True)
        .execute()
    )
    return response.data


def list_calls(limit: int = 50) -> list[dict]:
    client = get_client()
    response = (
        client.table("calls")
        .select("*, leads(id, owner_phone, properties(address))")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return response.data


def insert_transcript_chunks(call_id: str, lead_id: str | None, chunks: list[dict]) -> None:
    if not chunks:
        return
    client = get_client()
    rows = [
        {
            "call_id": call_id,
            "lead_id": lead_id,
            "speaker": c["speaker"],
            "text": c["text"],
            "chunk_type": c.get("chunk_type", "final"),
            "sequence_order": c["sequence_order"],
            "confidence": c.get("confidence"),
        }
        for c in chunks
    ]
    client.table("transcript_chunks").insert(rows).execute()
    logger.info("insert_transcript_chunks call_id={} count={}", call_id, len(rows))


def get_transcript_chunks(call_id: str) -> list[dict]:
    client = get_client()
    response = (
        client.table("transcript_chunks")
        .select("*")
        .eq("call_id", call_id)
        .order("sequence_order")
        .execute()
    )
    return response.data


def insert_call_event(call_id: str | None, lead_id: str | None, event_type: str, payload: dict | None = None) -> None:
    client = get_client()
    client.table("call_events").insert({
        "call_id": call_id,
        "lead_id": lead_id,
        "event_type": event_type,
        "payload": payload or {},
    }).execute()
    logger.debug("insert_call_event type={} call_id={}", event_type, call_id)


def get_recent_call_events(limit: int = 50) -> list[dict]:
    client = get_client()
    response = (
        client.table("call_events")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return response.data


def insert_comp(data: dict) -> str | None:
    client = get_client()
    response = client.table("comps").insert(data).execute()
    comp_id = response.data[0]["id"] if response.data else None
    logger.debug("insert_comp property_id={} id={}", data.get("subject_property_id"), comp_id)
    return comp_id


def get_comps_by_property(property_id: str) -> list[dict]:
    client = get_client()
    response = (
        client.table("comps")
        .select("*")
        .eq("subject_property_id", property_id)
        .order("sold_date", desc=True)
        .execute()
    )
    return response.data


def update_property_arv(property_id: str, arv: int, mao: int, confidence: str, extra: dict | None = None) -> None:
    client = get_client()
    data = {
        "estimated_arv": arv,
        "mao": mao,
        "arv_confidence": confidence,
        "updated_at": _now(),
    }
    if extra:
        data.update(extra)
    client.table("properties").update(data).eq("id", property_id).execute()
    logger.info("update_property_arv id={} arv={} mao={}", property_id, arv, mao)


def create_offer(
    lead_id: str,
    arv_used: int | None,
    repair_estimate: int = 2500000,
    amount: int | None = None,
    property_id: str | None = None,
    notes: str | None = None,
    created_by: str = "operator",
) -> str | None:
    client = get_client()
    mao_calculated: int | None = None
    if arv_used is not None:
        mao_calculated = int(arv_used * get_settings().mao_multiplier) - repair_estimate
    response = client.table("offers").insert({
        "lead_id": lead_id,
        "property_id": property_id,
        "arv_used": arv_used,
        "repair_estimate": repair_estimate,
        "mao_calculated": mao_calculated,
        "amount": amount if amount is not None else mao_calculated,
        "status": "draft",
        "notes": notes,
        "created_by": created_by,
    }).execute()
    offer_id = response.data[0]["id"] if response.data else None
    logger.info("create_offer lead_id={} mao={} id={}", lead_id, mao_calculated, offer_id)
    return offer_id


def get_offer_by_id(offer_id: str) -> dict | None:
    client = get_client()
    response = client.table("offers").select("*").eq("id", offer_id).limit(1).execute()
    return response.data[0] if response.data else None


def get_offers_for_lead(lead_id: str) -> list[dict]:
    client = get_client()
    response = (
        client.table("offers")
        .select("*")
        .eq("lead_id", lead_id)
        .order("created_at", desc=True)
        .execute()
    )
    return response.data


def update_offer_status(offer_id: str, status: str, notes: str | None = None) -> None:
    client = get_client()
    data: dict = {"status": status, "updated_at": _now()}
    if notes is not None:
        data["notes"] = notes
    client.table("offers").update(data).eq("id", offer_id).execute()
    logger.info("update_offer_status id={} status={}", offer_id, status)


def is_on_dnc_list(phone: str) -> bool:
    if not phone:
        return False
    client = get_client()
    response = client.table("dnc_list").select("id").eq("phone", phone).limit(1).execute()
    return bool(response.data)


def add_to_dnc_list(phone: str, reason: str = "opt_out") -> None:
    client = get_client()
    client.table("dnc_list").upsert({"phone": phone, "reason": reason}, on_conflict="phone").execute()
    logger.info("add_to_dnc_list phone={} reason={}", phone, reason)


def load_intel_packet(lead_id: str) -> dict | None:
    client = get_client()
    response = client.table("lead_intel_packets").select("*").eq("lead_id", lead_id).limit(1).execute()
    return response.data[0] if response.data else None


def save_intel_packet(lead_id: str, packet: dict) -> None:
    client = get_client()
    data = dict(packet)
    data["lead_id"] = lead_id
    data["updated_at"] = _now()
    client.table("lead_intel_packets").upsert(data, on_conflict="lead_id").execute()
    logger.debug("save_intel_packet lead_id={}", lead_id)


def get_seller_memory(lead_id: str) -> dict:
    client = get_client()
    response = client.table("seller_memory").select("*").eq("lead_id", lead_id).limit(1).execute()
    return response.data[0] if response.data else {}


def upsert_seller_memory(lead_id: str, fields: dict) -> None:
    client = get_client()
    data = dict(fields)
    data["lead_id"] = lead_id
    data["updated_at"] = _now()
    client.table("seller_memory").upsert(data, on_conflict="lead_id").execute()
    logger.debug("upsert_seller_memory lead_id={}", lead_id)


def save_decision_record(record: dict) -> None:
    client = get_client()
    client.table("decision_records").insert(record).execute()
    logger.debug("save_decision_record lead_id={} type={}", record.get("lead_id"), record.get("decision_type"))


def brief_is_stale(lead: dict) -> bool:
    if not lead.get("call_brief"):
        return True

    last_called_at = lead.get("last_called_at")
    if not last_called_at:
        return False

    generated_at = lead.get("call_brief_generated_at")
    if not generated_at:
        return True

    return str(generated_at) < str(last_called_at)


def get_leads_needing_brief(batch_size: int = 20) -> list[dict]:
    client = get_client()
    response = (
        client.table("leads")
        .select("*, properties(*)")
        .eq("opted_out", False)
        .eq("dnc_blocked", False)
        .neq("stage", "dead")
        .order("last_called_at", desc=True, nullsfirst=True)
        .limit(max(batch_size * 10, 100))
        .execute()
    )
    rows = response.data
    for r in rows:
        if isinstance(r.get("properties"), list):
            r["properties"] = r["properties"][0] if r["properties"] else {}
    return [r for r in rows if brief_is_stale(r)][:batch_size]


def save_call_brief(lead_id: str, brief: dict) -> None:
    client = get_client()
    client.table("leads").update({
        "call_brief": brief,
        "call_brief_generated_at": _now(),
    }).eq("id", lead_id).execute()
    logger.info("save_call_brief lead_id={}", lead_id)


def now_iso() -> str:
    return _now()


def update_property_fields(property_id: str, fields: dict) -> None:
    if not fields:
        return
    client = get_client()
    data = dict(fields)
    data["updated_at"] = _now()
    client.table("properties").update(data).eq("id", property_id).execute()
    logger.debug("update_property_fields property_id={} fields={}", property_id, list(fields.keys()))


def get_unflagged_stale_listings(min_days: int = 60, limit: int = 50) -> list[dict]:
    client = get_client()
    response = (
        client.table("properties")
        .select("*")
        .gte("days_on_market", min_days)
        .is_("stale_listing_flagged_at", "null")
        .order("days_on_market", desc=True)
        .limit(limit)
        .execute()
    )
    return response.data


def list_active_buyers(limit: int = 500) -> list[dict]:
    client = get_client()
    response = (
        client.table("buyers")
        .select("*")
        .eq("active", True)
        .order("deals_closed", desc=True)
        .limit(limit)
        .execute()
    )
    return response.data


def list_buyers(limit: int = 200) -> list[dict]:
    client = get_client()
    response = (
        client.table("buyers").select("*").order("created_at", desc=True).limit(limit).execute()
    )
    return response.data


def insert_buyer(data: dict) -> str | None:
    client = get_client()
    response = client.table("buyers").insert(data).execute()
    buyer_id = response.data[0]["id"] if response.data else None
    logger.info("insert_buyer name={} id={}", data.get("name"), buyer_id)
    return buyer_id


def get_buyer_by_phone(phone: str) -> dict | None:
    client = get_client()
    response = client.table("buyers").select("*").eq("phone", phone).limit(1).execute()
    return response.data[0] if response.data else None


def update_buyer_fields(buyer_id: str, fields: dict) -> None:
    if not fields:
        return
    client = get_client()
    data = dict(fields)
    data["updated_at"] = _now()
    client.table("buyers").update(data).eq("id", buyer_id).execute()
    logger.info("update_buyer_fields buyer_id={} fields={}", buyer_id, list(fields.keys()))


def deal_already_blasted(property_id: str, buyer_id: str, channel: str) -> bool:
    client = get_client()
    response = (
        client.table("deal_blasts")
        .select("id")
        .eq("property_id", property_id)
        .eq("buyer_id", buyer_id)
        .eq("channel", channel)
        .limit(1)
        .execute()
    )
    return bool(response.data)


def insert_deal_blast(property_id: str, buyer_id: str, channel: str, status: str) -> None:
    client = get_client()
    client.table("deal_blasts").insert({
        "property_id": property_id,
        "buyer_id": buyer_id,
        "channel": channel,
        "status": status,
    }).execute()


def get_blasts_for_property(property_id: str) -> list[dict]:
    client = get_client()
    response = (
        client.table("deal_blasts")
        .select("*, buyers(name, company, phone)")
        .eq("property_id", property_id)
        .order("created_at", desc=True)
        .execute()
    )
    return response.data


def list_decision_records(limit: int = 100, lead_id: str | None = None) -> list[dict]:
    client = get_client()
    query = client.table("decision_records").select("*, leads(id, properties(address))")
    if lead_id:
        query = query.eq("lead_id", lead_id)
    response = query.order("created_at", desc=True).limit(limit).execute()
    return response.data


def start_worker_run(worker: str) -> str | None:
    client = get_client()
    response = client.table("worker_runs").insert({"worker": worker, "status": "running"}).execute()
    return response.data[0]["id"] if response.data else None


def finish_worker_run(
    run_id: str, status: str, results: dict, duration_ms: int, error: str | None
) -> None:
    client = get_client()
    client.table("worker_runs").update({
        "status": status,
        "results": results,
        "duration_ms": duration_ms,
        "error": error,
        "finished_at": _now(),
    }).eq("id", run_id).execute()


def get_latest_worker_runs() -> list[dict]:
    client = get_client()
    response = (
        client.table("worker_runs")
        .select("*")
        .order("started_at", desc=True)
        .limit(200)
        .execute()
    )
    latest: dict[str, dict] = {}
    for row in response.data:
        if row["worker"] not in latest:
            latest[row["worker"]] = row
    return list(latest.values())


def health_check() -> bool:
    client = get_client()
    client.table("leads").select("id").limit(1).execute()
    return True


def insert_sms_message(
    lead_id: str, direction: str, body: str,
    signalwire_message_sid: str | None = None, status: str = "queued",
) -> str | None:
    client = get_client()
    response = client.table("sms_messages").insert({
        "lead_id": lead_id,
        "direction": direction,
        "body": body,
        "signalwire_message_sid": signalwire_message_sid,
        "status": status,
    }).execute()
    sms_id = response.data[0]["id"] if response.data else None
    logger.info("insert_sms_message lead_id={} direction={} id={}", lead_id, direction, sms_id)
    return sms_id


def lead_has_replied_by_sms(lead_id: str) -> bool:
    client = get_client()
    response = (
        client.table("sms_messages")
        .select("id")
        .eq("lead_id", lead_id)
        .eq("direction", "inbound")
        .limit(1)
        .execute()
    )
    return bool(response.data)


def get_sms_messages_for_lead(lead_id: str) -> list[dict]:
    client = get_client()
    response = (
        client.table("sms_messages")
        .select("*")
        .eq("lead_id", lead_id)
        .order("created_at", desc=True)
        .execute()
    )
    return response.data


def insert_email_message(
    lead_id: str, direction: str, subject: str, body: str,
    provider_message_id: str | None = None, status: str = "queued",
) -> str | None:
    client = get_client()
    response = client.table("email_messages").insert({
        "lead_id": lead_id,
        "direction": direction,
        "subject": subject,
        "body": body,
        "provider_message_id": provider_message_id,
        "status": status,
    }).execute()
    email_id = response.data[0]["id"] if response.data else None
    logger.info("insert_email_message lead_id={} direction={} id={}", lead_id, direction, email_id)
    return email_id


def get_reddit_match_by_reddit_id(reddit_id: str) -> dict | None:
    client = get_client()
    response = (
        client.table("reddit_matches")
        .select("id")
        .eq("reddit_id", reddit_id)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def insert_reddit_match(data: dict) -> str | None:
    client = get_client()
    response = client.table("reddit_matches").insert(data).execute()
    match_id = response.data[0]["id"] if response.data else None
    logger.info("insert_reddit_match reddit_id={} id={}", data.get("reddit_id"), match_id)
    return match_id


def list_reddit_matches(status: str | None = None, limit: int = 50) -> list[dict]:
    client = get_client()
    query = client.table("reddit_matches").select("*")
    if status:
        query = query.eq("status", status)
    response = query.order("intent_score", desc=True).order("created_at", desc=True).limit(limit).execute()
    return response.data


def get_reddit_match_by_id(match_id: str) -> dict | None:
    client = get_client()
    response = client.table("reddit_matches").select("*").eq("id", match_id).limit(1).execute()
    return response.data[0] if response.data else None


def link_reddit_match_to_lead(match_id: str, lead_id: str) -> None:
    client = get_client()
    client.table("reddit_matches").update({"status": "converted", "lead_id": lead_id}).eq("id", match_id).execute()
    logger.info("link_reddit_match_to_lead match_id={} lead_id={}", match_id, lead_id)


def dismiss_reddit_match(match_id: str) -> None:
    client = get_client()
    client.table("reddit_matches").update({"status": "dismissed"}).eq("id", match_id).execute()
    logger.info("dismiss_reddit_match match_id={}", match_id)
