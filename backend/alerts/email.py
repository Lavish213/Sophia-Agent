from __future__ import annotations

from loguru import logger

from backend.lib import db
from backend.lib.config import get_settings


def send_email(lead_id: str, subject: str, body: str) -> dict:
    lead = db.get_lead_by_id(lead_id)
    if not lead:
        return {"success": False, "reason": "lead_not_found"}

    if not lead.get("owner_email"):
        return {"success": False, "reason": "no_email_on_file"}

    if lead.get("opted_out") or lead.get("email_opted_out"):
        logger.info("email_blocked lead_id={} reason=opted_out", lead_id)
        return {"success": False, "reason": "opted_out"}

    settings = get_settings()

    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail

    message = Mail(
        from_email=settings.from_email,
        to_emails=lead["owner_email"],
        subject=subject,
        plain_text_content=body,
    )

    client = SendGridAPIClient(settings.sendgrid_api_key)
    response = client.send(message)
    provider_message_id = response.headers.get("X-Message-Id") if response.headers else None

    db.insert_email_message(lead_id, "outbound", subject, body, provider_message_id=provider_message_id, status="sent")
    logger.info("email_sent lead_id={} status_code={}", lead_id, response.status_code)
    return {"success": True, "message_id": provider_message_id}
