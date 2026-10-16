"""Brute-force protection for login, registration and password reset.

Fixed-window counters in Redis: failed logins are counted per email and per client IP,
registrations per client IP, and password reset requests per email and per client IP. Once a
counter reaches its limit, further attempts are rejected with 429 until the window expires.
"""

import hashlib
import logging
from typing import Optional

import redis.asyncio as aioredis

from app.config import settings
from app.exceptions import RateLimitExceededError

logger = logging.getLogger("auth_rate_limit")

# An IP may legitimately front many users (office NAT), so it gets more headroom than one email
IP_LIMIT_MULTIPLIER = 5

_client: Optional[aioredis.Redis] = None


def _get_client() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(settings.REDIS_URL)
    return _client


def _email_key(email: str) -> str:
    digest = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
    return f"auth:login_fail:email:{digest}"


def _ip_key(ip: Optional[str]) -> str:
    return f"auth:login_fail:ip:{ip or 'unknown'}"


async def _get_count(key: str) -> int:
    value = await _get_client().get(key)
    return int(value) if value else 0


async def _increment(key: str, window_seconds: int) -> int:
    pipe = _get_client().pipeline()
    pipe.incr(key)
    pipe.expire(key, window_seconds, nx=True)
    count, _ = await pipe.execute()
    return int(count)


async def ensure_login_allowed(email: str, ip: Optional[str]) -> None:
    """Raise 429 if this email or IP has too many recent failed logins."""
    try:
        email_fails = await _get_count(_email_key(email))
        ip_fails = await _get_count(_ip_key(ip))
    except Exception as e:
        # Fail open: Redis being down must not lock every user out
        logger.warning(f"Login rate limit check unavailable: {e}")
        return
    if (
        email_fails >= settings.LOGIN_MAX_FAILED_ATTEMPTS
        or ip_fails >= settings.LOGIN_MAX_FAILED_ATTEMPTS * IP_LIMIT_MULTIPLIER
    ):
        raise RateLimitExceededError(retry_after_seconds=settings.LOGIN_LOCKOUT_WINDOW_SECONDS)


async def record_login_failure(email: str, ip: Optional[str]) -> None:
    window = settings.LOGIN_LOCKOUT_WINDOW_SECONDS
    try:
        await _increment(_email_key(email), window)
        await _increment(_ip_key(ip), window)
    except Exception as e:
        logger.warning(f"Failed to record login failure: {e}")


async def clear_login_failures(email: str) -> None:
    try:
        await _get_client().delete(_email_key(email))
    except Exception as e:
        logger.warning(f"Failed to clear login failures: {e}")


async def ensure_registration_allowed(ip: Optional[str]) -> None:
    """Raise 429 if this IP has created too many accounts in the last hour."""
    try:
        count = await _increment(f"auth:register:ip:{ip or 'unknown'}", 3600)
    except Exception as e:
        logger.warning(f"Registration rate limit check unavailable: {e}")
        return
    if count > settings.REGISTER_MAX_PER_IP_PER_HOUR:
        raise RateLimitExceededError(retry_after_seconds=3600)


async def ensure_password_reset_request_allowed(email: str, ip: Optional[str]) -> bool:
    """Count a reset request; False once this email or IP is over its hourly limit.

    Over-limit requests are dropped silently rather than rejected, so the response never
    differs between registered and unregistered emails. The IP limit still raises 429, since
    it says nothing about any particular account.
    """
    digest = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
    try:
        ip_count = await _increment(f"auth:pw_reset:ip:{ip or 'unknown'}", 3600)
        email_count = await _increment(f"auth:pw_reset:email:{digest}", 3600)
    except Exception as e:
        logger.warning(f"Password reset rate limit check unavailable: {e}")
        return True
    if ip_count > settings.PASSWORD_RESET_MAX_PER_IP_PER_HOUR:
        raise RateLimitExceededError(retry_after_seconds=3600)
    return email_count <= settings.PASSWORD_RESET_MAX_PER_EMAIL_PER_HOUR


async def ensure_password_reset_attempt_allowed(ip: Optional[str]) -> None:
    """Raise 429 if this IP has submitted too many reset tokens in the last hour."""
    try:
        count = await _increment(f"auth:pw_reset_submit:ip:{ip or 'unknown'}", 3600)
    except Exception as e:
        logger.warning(f"Password reset attempt rate limit check unavailable: {e}")
        return
    if count > settings.PASSWORD_RESET_MAX_PER_IP_PER_HOUR:
        raise RateLimitExceededError(retry_after_seconds=3600)
