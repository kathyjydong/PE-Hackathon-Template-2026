"""Redis client (Python equivalent of a small redis.js config module)."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import redis

if TYPE_CHECKING:
    from flask import Flask

_client: redis.Redis | None = None


def _normalize_redis_url(url: str) -> str:
    """redis-py requires redis://, rediss://, or unix://. Allow host:port as shorthand."""
    url = url.strip()
    if not url:
        return ""
    if url.startswith(("redis://", "rediss://", "unix://")):
        return url
    return f"redis://{url}"


def get_redis() -> redis.Redis | None:
    """Return the connected client, or None if Redis was not configured."""
    return _client


def init_redis(app: Flask) -> None:
    """
    Connect to Redis when REDIS_URL is set (e.g. redis://localhost:6379/0).
    If REDIS_URL is unset, Redis is skipped so local Postgres-only dev still works.
    """
    global _client
    url = _normalize_redis_url(os.environ.get("REDIS_URL") or "")
    if not url:
        app.logger.info("REDIS_URL not set; Redis disabled")
        return

    try:
        r = redis.from_url(url, decode_responses=True)
        r.ping()
    except (redis.RedisError, ValueError) as err:
        app.logger.error("Redis connection failed: %s", err)
        raise RuntimeError(
            "Failed to connect to Redis. Use a full URL like redis://127.0.0.1:6379/0 "
            f"(got REDIS_URL after normalize: {url!r}). Error: {err}"
        ) from err

    _client = r
    app.logger.info("Connected to Redis")
