"""Idempotency guard for inbound channel webhooks.

Meta delivers webhooks at-least-once, so the same message can arrive twice (sometimes within
milliseconds, on different workers). We claim each external message ID in Redis with SET NX;
only the first claimer processes it.
"""

import logging
from typing import Optional

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger("channel_dedup")

DEDUP_TTL_SECONDS = 24 * 3600

_client: Optional[aioredis.Redis] = None


def _get_client() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(settings.REDIS_URL)
    return _client


async def claim_inbound_message(channel: str, external_id: Optional[str]) -> bool:
    """Return True if this message should be processed, False if it was already seen."""
    if not external_id:
        return True
    try:
        claimed = await _get_client().set(f"inbound:{channel}:{external_id}", 1, nx=True, ex=DEDUP_TTL_SECONDS)
        return bool(claimed)
    except Exception as e:
        # Fail open: a rare duplicate is better than dropping a customer's message
        logger.warning(f"Dedup check unavailable for {channel} message {external_id}: {e}")
        return True
