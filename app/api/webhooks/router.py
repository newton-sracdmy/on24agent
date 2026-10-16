"""Webhook master router handling incoming payloads from Meta WhatsApp, Telegram, Stripe, etc."""

import asyncio

import hashlib
import hmac
import json
import logging
from typing import Awaitable, Callable, Iterable, Optional, Set

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from app.config import settings

webhooks_router = APIRouter()
logger = logging.getLogger("webhooks")

# Strong references so background processing tasks are not garbage-collected mid-flight
_background_tasks: Set[asyncio.Task] = set()


def _signature_valid(body: bytes, header: Optional[str], secrets: Iterable[str]) -> bool:
    if not header or not header.startswith("sha256="):
        return False
    received = header.split("=", 1)[1]
    return any(
        hmac.compare_digest(hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(), received)
        for secret in secrets
    )


async def _accept_meta_event(
    request: Request, channel: str, secrets: Iterable[Optional[str]], handler: Callable[[dict], Awaitable[None]]
) -> dict:
    """Verify a Meta webhook delivery, then process it in the background and ACK immediately."""
    body = await request.body()
    configured = [s for s in secrets if s]
    if configured:
        if not _signature_valid(body, request.headers.get("X-Hub-Signature-256"), configured):
            logger.warning(f"Rejected {channel} webhook with missing or invalid X-Hub-Signature-256")
            raise HTTPException(status_code=403, detail="Invalid webhook signature")
    else:
        logger.warning(f"{channel} webhook accepted WITHOUT signature verification: set META_APP_SECRET")

    try:
        payload = json.loads(body) if body else {}
    except ValueError:
        payload = {}
    if isinstance(payload, dict) and payload:
        async def _run() -> None:
            try:
                await handler(payload)
            except Exception:
                logger.exception(f"Failed to process {channel} webhook event")

        task = asyncio.create_task(_run())
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
    return {"status": "EVENT_RECEIVED"}


from fastapi.responses import PlainTextResponse
from app.domains.channels.whatsapp_service import handle_inbound_whatsapp_event


@webhooks_router.get("/whatsapp")
async def verify_whatsapp_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
) -> Response:
    """Handles Meta WhatsApp Cloud API webhook handshake verification."""
    if hub_mode == "subscribe" and hub_verify_token == settings.META_WEBHOOK_VERIFY_TOKEN:
        return PlainTextResponse(
            content=str(hub_challenge),
            status_code=200,
            headers={
                "Content-Type": "text/plain; charset=utf-8",
                "Content-Encoding": "identity",
            },
        )
    raise HTTPException(status_code=403, detail="Verification token mismatch")


@webhooks_router.post("/whatsapp")
async def receive_whatsapp_webhook(request: Request) -> dict:
    """Receives asynchronous inbound messages and delivery status updates from WhatsApp."""
    return await _accept_meta_event(request, "WhatsApp", [settings.META_APP_SECRET], handle_inbound_whatsapp_event)


from fastapi.responses import PlainTextResponse


@webhooks_router.get("/facebook")
@webhooks_router.get("/messenger")
async def verify_facebook_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
) -> Response:
    """Handles Meta Facebook Messenger webhook handshake verification."""
    if hub_mode == "subscribe" and hub_verify_token == settings.META_WEBHOOK_VERIFY_TOKEN:
        return PlainTextResponse(
            content=str(hub_challenge),
            status_code=200,
            headers={
                "Content-Type": "text/plain; charset=utf-8",
                "Content-Encoding": "identity",
            },
        )
    raise HTTPException(status_code=403, detail="Verification token mismatch")


from app.domains.channels.facebook_service import handle_inbound_facebook_event


@webhooks_router.post("/facebook")
@webhooks_router.post("/messenger")
async def receive_facebook_webhook(request: Request) -> dict:
    """Receives asynchronous inbound messages from Facebook Messenger."""
    return await _accept_meta_event(request, "Messenger", [settings.META_APP_SECRET], handle_inbound_facebook_event)


from app.domains.channels.instagram_service import handle_inbound_instagram_event


@webhooks_router.get("/instagram")
async def verify_instagram_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
) -> Response:
    """Handles Meta Instagram Messaging webhook handshake verification."""
    if hub_mode == "subscribe" and hub_verify_token == settings.META_WEBHOOK_VERIFY_TOKEN:
        return PlainTextResponse(
            content=str(hub_challenge),
            status_code=200,
            headers={
                "Content-Type": "text/plain; charset=utf-8",
                "Content-Encoding": "identity",
            },
        )
    raise HTTPException(status_code=403, detail="Verification token mismatch")


@webhooks_router.post("/instagram")
async def receive_instagram_webhook(request: Request) -> dict:
    """Receives asynchronous inbound direct messages from Instagram."""
    return await _accept_meta_event(request, "Instagram", [settings.INSTAGRAM_APP_SECRET, settings.META_APP_SECRET], handle_inbound_instagram_event)


@webhooks_router.post("/stripe")
async def receive_stripe_webhook(
    request: Request,
    stripe_signature: str = Header(alias="Stripe-Signature"),
) -> dict:
    """Processes asynchronous payment events and subscription lifecycle from Stripe."""
    payload = await request.body()
    return {"status": "received"}
