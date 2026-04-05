"""Redis client (Python equivalent of a small redis.js config module)."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from urllib.parse import quote, urlparse, urlunparse

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


def _apply_redis_password_from_env(url: str) -> str:
    """
    Docker Compose prod sets redis-server --requirepass and often puts the secret only in
    REDIS_PASSWORD while REDIS_URL stays redis://redis:6379/0. redis-py does not read
    REDIS_PASSWORD; without auth, ping fails and the app runs with cache disabled (empty Redis).
    """
    password = (os.environ.get("REDIS_PASSWORD") or "").strip()
    if not password or url.startswith("unix://"):
        return url
    parsed = urlparse(url)
    if parsed.password is not None:
        return url
    if not parsed.netloc:
        return url
    qpass = quote(password, safe="")
    if "@" not in parsed.netloc:
        netloc = f":{qpass}@{parsed.netloc}"
    else:
        user_host = parsed.netloc.split("@", 1)
        user_part, host_part = user_host[0], user_host[1]
        userinfo = f"{user_part}:{qpass}" if user_part else f":{qpass}"
        netloc = f"{userinfo}@{host_part}"
    return urlunparse(
        (parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
    )


def get_redis() -> redis.Redis | None:
    """Return the connected client, or None if Redis was not configured."""
    return _client


def init_redis(app: Flask) -> None:
    """
    Connect to Redis when REDIS_URL is set (e.g. redis://localhost:6379/0).
    If REDIS_URL is unset, Redis is skipped so local Postgres-only dev still works.
    """
    global _client
    url = _apply_redis_password_from_env(
        _normalize_redis_url(os.environ.get("REDIS_URL") or "")
    )
    if not url:
        app.logger.info("REDIS_URL not set; Redis disabled")
        return

    try:
        max_conn = int(os.environ.get("REDIS_MAX_CONNECTIONS", "128"))
        r = redis.from_url(url, decode_responses=True, max_connections=max_conn)
        r.ping()
    except (redis.RedisError, ValueError) as err:
        app.logger.error(
            "Redis unavailable at startup (%s). App will run without cache. Error: %s",
            url,
            err,
        )
        _client = None
        return

    _client = r
    app.logger.info("Connected to Redis")
