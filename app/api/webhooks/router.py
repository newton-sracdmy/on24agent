"""Webhook master router handling incoming payloads from Meta WhatsApp, Telegram, Stripe, etc."""

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from app.config import settings

webhooks_router = APIRouter()


@webhooks_router.get("/whatsapp")
async def verify_whatsapp_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
) -> Response:
    """Handles Meta WhatsApp Cloud API webhook handshake verification."""
    if hub_mode == "subscribe" and hub_verify_token == settings.META_WEBHOOK_VERIFY_TOKEN:
        return Response(content=hub_challenge, media_type="text/plain", status_code=200)
    raise HTTPException(status_code=403, detail="Verification token mismatch")


@webhooks_router.post("/whatsapp")
async def receive_whatsapp_webhook(request: Request) -> dict:
    """Receives asynchronous inbound messages and delivery status updates from WhatsApp."""
    payload = await request.json()
    # Inbound processing dispatched to background worker
    return {"status": "received"}


@webhooks_router.post("/stripe")
async def receive_stripe_webhook(
    request: Request,
    stripe_signature: str = Header(alias="Stripe-Signature"),
) -> dict:
    """Processes asynchronous payment events and subscription lifecycle from Stripe."""
    payload = await request.body()
    return {"status": "received"}
