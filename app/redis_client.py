"""Redis client (Python equivalent of a small redis.js config module)."""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

import redis

if TYPE_CHECKING:
    from flask import Flask

_client: redis.Redis | None = None

DEFAULT_REDIS_URL = "redis://localhost:6379"


def _normalize_redis_url(url: str) -> str:
    """redis-py requires redis://, rediss://, or unix://. Allow host:port as shorthand."""
    url = url.strip()
    if not url:
        return ""
    if url.startswith(("redis://", "rediss://", "unix://")):
        return url
    return f"redis://{url}"


def _redis_url_from_env() -> str:
    raw = os.environ.get("REDIS_URL")
    if raw is None or not str(raw).strip():
        return DEFAULT_REDIS_URL
    return _normalize_redis_url(str(raw).strip())


def get_redis() -> redis.Redis | None:
    """Return the connected client, or None if Redis was not configured."""
    return _client


def init_redis(app: Flask) -> None:
    """
    Connect using REDIS_URL, or redis://localhost:6379 if REDIS_URL is missing/empty.

    Retries with a fixed delay between attempts so startup is resilient if Redis is slow
    to accept connections after Docker healthchecks.
    """
    global _client
    raw = os.environ.get("REDIS_URL")
    using_default = raw is None or not str(raw).strip()
    url = _redis_url_from_env()
    if not url:
        app.logger.error("REDIS_URL resolved to empty after normalization; Redis disabled")
        _client = None
        return

    if using_default:
        app.logger.info("REDIS_URL not set or empty; using default %s", url)

    max_attempts = max(1, int(os.environ.get("REDIS_CONNECT_RETRIES", "30")))
    delay_sec = max(0.1, float(os.environ.get("REDIS_CONNECT_DELAY", "1.0")))
    last_err: BaseException | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            r = redis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                health_check_interval=30,
                retry_on_timeout=True,
            )
            r.ping()
        except (redis.RedisError, ValueError, OSError) as err:
            last_err = err
            if attempt >= max_attempts:
                break
            app.logger.warning(
                "Redis not ready (%s), retry %s/%s in %.1fs: %s",
                url,
                attempt,
                max_attempts,
                delay_sec,
                err,
            )
            time.sleep(delay_sec)
            continue

        _client = r
        if attempt > 1:
            app.logger.info("Connected to Redis after %s attempts", attempt)
        else:
            app.logger.info("Connected to Redis")
        return

    app.logger.error(
        "Redis unavailable after %s attempts (%s). App will run without cache. Last error: %s",
        max_attempts,
        url,
        last_err,
    )
    _client = None
