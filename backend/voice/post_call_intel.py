from __future__ import annotations

import json

from loguru import logger

from backend.lib import db
from backend.lib.config import get_settings

_EXTRACTION_TOOL = {
    "name": "record_call_intel",
    "description": "Record structured intelligence extracted from a call transcript.",
    "input_schema": {
        "type": "object",
        "properties": {
            "disposition": {"type": "string", "enum": ["HOT", "WARM", "COLD", "DEAD"]},
            "motivation_level": {"type": "integer", "minimum": 0, "maximum": 10},
            "timeline_urgency": {"type": "string"},
            "price_floor_dollars": {"type": ["integer", "null"]},
            "objections": {"type": "array", "items": {"type": "string"}},
            "call_summary": {"type": "string"},
            "next_best_action": {"type": "string"},
        },
        "required": ["disposition", "motivation_level", "call_summary", "next_best_action"],
    },
}

_SYSTEM_PROMPT = (
    "You extract structured intelligence from a real estate acquisitions call transcript. "
    "Be conservative — only mark HOT if the seller showed clear, genuine interest in selling soon. "
    "Only call record_call_intel once, with your best assessment."
)


def _build_transcript_text(transcript_chunks: list[dict]) -> str:
    lines = [f"{c['speaker']}: {c['text']}" for c in transcript_chunks]
    return "\n".join(lines)


def extract_call_intel(transcript_chunks: list[dict]) -> dict | None:
    if not transcript_chunks:
        return None

    from anthropic import Anthropic

    settings = get_settings()
    client = Anthropic(api_key=settings.anthropic_api_key)

    transcript_text = _build_transcript_text(transcript_chunks)

    response = client.messages.create(
        model=settings.llm_model,
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        tools=[_EXTRACTION_TOOL],
        tool_choice={"type": "tool", "name": "record_call_intel"},
        messages=[{"role": "user", "content": f"Transcript:\n\n{transcript_text}"}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "record_call_intel":
            return block.input

    logger.warning("extract_call_intel_no_tool_use_block")
    return None


def apply_call_intel(call_id: str, lead_id: str | None, intel: dict) -> None:
    call_fields = {
        "call_disposition": intel.get("disposition"),
        "call_summary": intel.get("call_summary"),
        "next_step": intel.get("next_best_action"),
        "objections": json.dumps(intel.get("objections") or []),
    }
    db.update_call_fields(call_id, {k: v for k, v in call_fields.items() if v is not None})

    if not lead_id:
        return

    lead_fields: dict = {
        "call_summary": intel.get("call_summary"),
        "next_best_action": intel.get("next_best_action"),
        "timeline_urgency": intel.get("timeline_urgency"),
    }
    if intel.get("motivation_level") is not None:
        lead_fields["motivation_level"] = intel["motivation_level"]
    if intel.get("price_floor_dollars") is not None:
        lead_fields["price_floor"] = int(intel["price_floor_dollars"]) * 100
    if intel.get("objections"):
        lead_fields["objections"] = intel["objections"]
    if intel.get("disposition") == "HOT":
        lead_fields["is_hot_lead"] = True

    db.update_lead_fields(lead_id, {k: v for k, v in lead_fields.items() if v is not None})
    logger.info(
        "post_call_intel_applied call_id={} lead_id={} disposition={}",
        call_id, lead_id, intel.get("disposition"),
    )


def run_post_call_intel(call_id: str, lead_id: str | None) -> dict | None:
    try:
        chunks = db.get_transcript_chunks(call_id)
        intel = extract_call_intel(chunks)
        if intel:
            apply_call_intel(call_id, lead_id, intel)
        return intel
    except Exception as e:
        logger.exception("run_post_call_intel_failed call_id={} error={}", call_id, str(e))
        return None
