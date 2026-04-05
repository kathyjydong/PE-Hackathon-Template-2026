"""Redis cache for short-link resolve: plain destination URL per alias (hot path, no JSON)."""

from __future__ import annotations

import hashlib
import logging
import os

import redis

from app.redis_client import get_redis

logger = logging.getLogger(__name__)

# Forward cache:  url:<short_code>  →  original_url
KEY_PREFIX = "url:"
# Reverse cache:  orig:<sha256>     →  short_code
ORIG_KEY_PREFIX = "orig:"

DEFAULT_TTL_SECONDS = int(os.environ.get("SHORT_LINK_CACHE_TTL", "3600"))

_DEBUG_RESOLVE = os.environ.get("REDIS_RESOLVE_DEBUG", "").strip().lower() in (
    "1",
    "true",
    "yes",
)


def _redis_key(alias: str) -> str:
    return f"{KEY_PREFIX}{alias}"


def _orig_key(original_url: str) -> str:
    digest = hashlib.sha256(original_url.encode()).hexdigest()
    return f"{ORIG_KEY_PREFIX}{digest}"


# ---------------------------------------------------------------------------
# Forward cache: short_code → original_url  (resolve hot path)
# ---------------------------------------------------------------------------

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
            if _DEBUG_RESOLVE:
                logger.info("resolve cache miss alias=%s", alias)
            return None
        if _DEBUG_RESOLVE:
            logger.info("resolve cache hit alias=%s", alias)
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


# ---------------------------------------------------------------------------
# Reverse cache: original_url → short_code  (shorten dedup hot path)
# ---------------------------------------------------------------------------

def get_cached_url_to_code(original_url: str) -> str | None:
    """
    GET orig:<sha256(original_url)> from Redis.
    Returns the short_code on hit, else None.
    Lets shorten() skip the DB dedup query entirely on repeat submissions.
    """
    client = get_redis()
    if not client:
        return None
    try:
        raw = client.get(_orig_key(original_url))
        if raw is None or raw == "":
            return None
        if _DEBUG_RESOLVE:
            logger.info("reverse cache hit url=%s code=%s", original_url, raw)
        return raw
    except (redis.RedisError, TypeError, ValueError) as err:
        logger.warning("Redis reverse get failed: %s", err)
        return None


def set_cached_url_to_code(original_url: str, short_code: str) -> bool:
    """SET orig:<sha256> → short_code with the same TTL as the forward entry."""
    if not original_url or not short_code:
        return False
    client = get_redis()
    if not client:
        return False
    try:
        client.setex(_orig_key(original_url), DEFAULT_TTL_SECONDS, short_code)
        return True
    except (redis.RedisError, TypeError, ValueError) as err:
        logger.warning("Redis reverse setex failed: %s", err)
        return False


def delete_cached_url_to_code(original_url: str) -> None:
    """Invalidate orig:<sha256> entry on revoke. Swallows Redis errors."""
    client = get_redis()
    if not client:
        return
    try:
        client.delete(_orig_key(original_url))
    except redis.RedisError as err:
        logger.warning("Redis reverse delete failed: %s", err)
