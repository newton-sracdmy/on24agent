"""Per-organization throttling for Instruction Builder Studio endpoints that call the paid LLM.

Fixed one-minute windows in Redis keyed by organization and action.
"""

import logging
from uuid import UUID

import redis.asyncio as aioredis

from app.config import settings
from app.exceptions import RateLimitExceededError

logger = logging.getLogger("agent_rate_limit")

WINDOW_SECONDS = 60
LIMITS_PER_MINUTE = {
    "generate": 10,
    "test": 30,
}

_client: aioredis.Redis | None = None


def _get_client() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(settings.REDIS_URL)
    return _client


async def ensure_llm_call_allowed(org_id: UUID, action: str) -> None:
    """Raise 429 once an organization exceeds its per-minute budget for this action."""
    key = f"agents:studio:{action}:{org_id}"
    try:
        pipe = _get_client().pipeline()
        pipe.incr(key)
        pipe.expire(key, WINDOW_SECONDS, nx=True)
        count, _ = await pipe.execute()
    except Exception as e:
        # Fail open: Redis being down must not disable the Studio
        logger.warning(f"Studio rate limit check unavailable: {e}")
        return
    if int(count) > LIMITS_PER_MINUTE[action]:
        raise RateLimitExceededError(retry_after_seconds=WINDOW_SECONDS)
