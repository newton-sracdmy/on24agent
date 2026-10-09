"""Webhook master router handling incoming payloads from Meta WhatsApp, Telegram, Stripe, etc."""

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from app.config import settings

webhooks_router = APIRouter()


from fastapi.responses import PlainTextResponse
import asyncio
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
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    if payload:
        asyncio.create_task(handle_inbound_whatsapp_event(payload))

    return {"status": "EVENT_RECEIVED"}


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


import asyncio
from app.domains.channels.facebook_service import handle_inbound_facebook_event


@webhooks_router.post("/facebook")
@webhooks_router.post("/messenger")
async def receive_facebook_webhook(request: Request) -> dict:
    """Receives asynchronous inbound messages from Facebook Messenger."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    if payload:
        # Dispatch background processing so webhook immediately ACKs Meta with 200 OK
        asyncio.create_task(handle_inbound_facebook_event(payload))

    return {"status": "EVENT_RECEIVED"}


@webhooks_router.post("/stripe")
async def receive_stripe_webhook(
    request: Request,
    stripe_signature: str = Header(alias="Stripe-Signature"),
) -> dict:
    """Processes asynchronous payment events and subscription lifecycle from Stripe."""
    payload = await request.body()
    return {"status": "received"}
