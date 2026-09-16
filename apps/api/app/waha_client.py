"""Thin client for a self-hosted WAHA (WhatsApp HTTP API) instance.

WAHA session names double as ids — one session per app user.
"""
from uuid import UUID

import httpx

from .config import get_settings

REQUEST_TIMEOUT = 15


def session_name_for(user_id: UUID) -> str:
    return f"u_{user_id.hex}"


def _headers() -> dict[str, str]:
    settings = get_settings()
    if settings.waha_api_key is not None:
        return {"X-Api-Key": settings.waha_api_key.get_secret_value()}
    return {}


def _url(path: str) -> str:
    return f"{get_settings().waha_base_url.rstrip('/')}{path}"


def _webhook_config() -> dict | None:
    settings = get_settings()
    if not settings.waha_webhook_url:
        return None
    webhook: dict = {
        "url": settings.waha_webhook_url,
        "events": ["message", "session.status"],
    }
    if settings.waha_webhook_secret is not None:
        webhook["customHeaders"] = [
            {"name": "X-Webhook-Token", "value": settings.waha_webhook_secret.get_secret_value()}
        ]
    return webhook


def create_session(name: str) -> dict:
    """Create and start a WAHA session. Raises httpx.HTTPStatusError on failure."""
    config: dict = {}
    webhook = _webhook_config()
    if webhook:
        config["webhooks"] = [webhook]
    resp = httpx.post(
        _url("/api/sessions"),
        json={"name": name, "config": config},
        headers=_headers(),
        timeout=REQUEST_TIMEOUT,
    )
    # 422 means the name already exists — start it instead.
    if resp.status_code == 422:
        return start_session(name)
    resp.raise_for_status()
    return resp.json()


def start_session(name: str) -> dict:
    resp = httpx.post(_url(f"/api/sessions/{name}/start"), headers=_headers(), timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def get_session(name: str) -> dict | None:
    """Return the session payload, or None when WAHA has no such session."""
    resp = httpx.get(_url(f"/api/sessions/{name}"), headers=_headers(), timeout=REQUEST_TIMEOUT)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def delete_session(name: str) -> None:
    resp = httpx.delete(_url(f"/api/sessions/{name}"), headers=_headers(), timeout=REQUEST_TIMEOUT)
    if resp.status_code not in (200, 204, 404):
        resp.raise_for_status()


def get_qr(name: str) -> dict:
    """Return {'mimetype': ..., 'data': <base64>} for the current QR code."""
    resp = httpx.get(
        _url(f"/api/{name}/auth/qr"),
        params={"format": "image"},
        headers={**_headers(), "Accept": "application/json"},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def request_pairing_code(name: str, phone_number: str) -> str:
    resp = httpx.post(
        _url(f"/api/{name}/auth/request-code"),
        json={"phoneNumber": phone_number},
        headers=_headers(),
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["code"]


def chats_overview(name: str, limit: int = 100, offset: int = 0) -> list[dict]:
    resp = httpx.get(
        _url(f"/api/{name}/chats/overview"),
        params={"limit": limit, "offset": offset},
        headers=_headers(),
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def get_messages(name: str, chat_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
    resp = httpx.get(
        _url(f"/api/{name}/chats/{chat_id}/messages"),
        params={"limit": limit, "offset": offset, "downloadMedia": "false"},
        headers=_headers(),
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()
