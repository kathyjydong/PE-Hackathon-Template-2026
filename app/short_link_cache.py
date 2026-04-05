"""Redis cache for short-link resolve: plain destination URL per alias (hot path, no JSON)."""

from __future__ import annotations

import logging
import os

import redis

from app.redis_client import get_redis

logger = logging.getLogger(__name__)

KEY_PREFIX = "url:"
DEFAULT_TTL_SECONDS = int(os.environ.get("SHORT_LINK_CACHE_TTL", "3600"))


def _redis_key(alias: str) -> str:
    return f"{KEY_PREFIX}{alias}"


def get_cached_resolve_url(alias: str) -> str | None:
    """
    GET url:<alias> from Redis. Returns the redirect target string on hit, else None.
    No JSON parse on the hot path.
    """
    client = get_redis()
    if not client:
        return None
    try:
        raw = client.get(_redis_key(alias))
        if raw is None or raw == "":
            return None
        return raw
    except (redis.RedisError, TypeError, ValueError) as err:
        logger.warning("Redis get failed alias=%s: %s", alias, err)
        return None


def set_cached_resolve_url(alias: str, url: str) -> bool:
    """SET url:<alias> to the plain URL string with TTL. Skips empty URLs."""
    if not url:
        return False
    client = get_redis()
    if not client:
        return False
    try:
        client.setex(_redis_key(alias), DEFAULT_TTL_SECONDS, url)
        return True
    except (redis.RedisError, TypeError, ValueError) as err:
        logger.warning("Redis setex failed alias=%s: %s", alias, err)
        return False


def delete_cached_short_link(alias: str) -> None:
    """Invalidate url:<alias>. Swallows Redis errors."""
    client = get_redis()
    if not client:
        return
    try:
        client.delete(_redis_key(alias))
    except redis.RedisError as err:
        logger.warning("Redis delete failed alias=%s: %s", alias, err)
