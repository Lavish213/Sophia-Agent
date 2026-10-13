from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

from backend.lib.config import get_settings


async def verify_signalwire_request(request: Request) -> None:
    settings = get_settings()
    if not settings.signalwire_signing_key or not settings.public_url:
        raise HTTPException(status_code=503, detail="SignalWire webhook authentication is not configured")
    public = urlsplit(settings.public_url)
    if public.scheme != "https" or not public.netloc or public.query or public.fragment:
        raise HTTPException(status_code=503, detail="A public HTTPS URL is required")
    url = settings.public_url.rstrip("/") + request.url.path
    if request.url.query:
        url += "?" + request.url.query
    form = await request.form()
    message = url + "".join(
        name + value for name in sorted(form) for value in form.getlist(name) if isinstance(value, str)
    )
    expected = base64.b64encode(
        hmac.new(settings.signalwire_signing_key.encode(), message.encode(), hashlib.sha1).digest()
    ).decode()
    provided = request.headers.get("x-signalwire-signature", "")
    if not hmac.compare_digest(expected.encode(), provided.encode()):
        raise HTTPException(status_code=403, detail="Invalid SignalWire signature")


def issue_stream_token(claims: dict) -> str:
    key = get_settings().signalwire_signing_key
    if not key:
        raise HTTPException(status_code=503, detail="Stream authentication is not configured")
    data = {**claims, "purpose": "sophia-stream", "expires": int(time.time()) + 300}
    payload = base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":"), sort_keys=True).encode())
    payload = payload.decode().rstrip("=")
    return payload + "." + hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()


def verify_stream_token(token: str, call_sid: str) -> dict | None:
    key = get_settings().signalwire_signing_key
    if not key or not isinstance(token, str) or len(token) > 4096 or not call_sid:
        return None
    try:
        payload, signature = token.split(".")
        expected = hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        now = int(time.time())
        if claims.get("purpose") != "sophia-stream" or claims.get("call_sid") != call_sid:
            return None
        if not isinstance(claims.get("expires"), int) or not now < claims["expires"] <= now + 300:
            return None
        return claims
    except (ValueError, TypeError, KeyError, UnicodeError, AttributeError):
        return None
