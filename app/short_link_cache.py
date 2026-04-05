"""Redis cache for short-link alias resolution. Postgres remains source of truth."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import redis

from app.redis_client import get_redis

logger = logging.getLogger(__name__)

KEY_PREFIX = "short:"
DEFAULT_TTL_SECONDS = int(os.environ.get("SHORT_LINK_CACHE_TTL", "3600"))


def _redis_key(alias: str) -> str:
    return f"{KEY_PREFIX}{alias}"


def url_row_to_cache_dict(entry: Any) -> dict[str, Any]:
    """Build cache payload from a Url model instance."""
    created = getattr(entry, "created_at", None)
    created_iso = created.isoformat() if created else None
    return {
        "url": entry.original_url,
        "active": not bool(entry.revoked),
        "id": entry.id,
        "createdAt": created_iso,
        "updatedAt": created_iso,
    }


def get_cached_short_link(alias: str) -> dict[str, Any] | None:
    """
    GET short:<alias> from Redis. Returns parsed dict on hit, None on miss or Redis error.
    """
    client = get_redis()
    if not client:
        return None
    try:
        raw = client.get(_redis_key(alias))
        if raw is None:
            return None
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except (redis.RedisError, json.JSONDecodeError, TypeError, ValueError) as err:
        logger.warning("Redis get failed alias=%s: %s", alias, err)
        return None


def set_cached_short_link(alias: str, data: dict[str, Any]) -> bool:
    """SET short:<alias> with TTL. Returns False if Redis unavailable or command fails."""
    client = get_redis()
    if not client:
        return False
    try:
        payload = json.dumps(data, default=str)
        client.setex(_redis_key(alias), DEFAULT_TTL_SECONDS, payload)
        return True
    except (redis.RedisError, TypeError, ValueError) as err:
        logger.warning("Redis setex failed alias=%s: %s", alias, err)
        return False


def delete_cached_short_link(alias: str) -> None:
    """Delete cache key for alias. Swallows Redis errors."""
    client = get_redis()
    if not client:
        return
    try:
        client.delete(_redis_key(alias))
    except redis.RedisError as err:
        logger.warning("Redis delete failed alias=%s: %s", alias, err)
