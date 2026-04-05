import json
import os
import re
from datetime import datetime
from urllib.parse import urlparse

from flask import Blueprint, jsonify, redirect, request
from werkzeug.exceptions import BadRequest

from app.models import Event, Url, UrlRead, User, db, db_read
from app.short_link_cache import (
    delete_cached_short_link,
    get_cached_resolve_url,
    set_cached_resolve_url,
)

url_bp = Blueprint("url", __name__)

CUSTOM_ALIAS_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,32}$")


def _base_url():
    return os.getenv("BASE_URL", request.host_url.rstrip("/"))


def _short_url(short_code):
    return f"{_base_url()}/{short_code}"


def _is_valid_web_url(value):
    if not isinstance(value, str):
        return False
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _with_cache_headers(resp, label: str):
    """HIT/MISS for k6 and proxies; duplicate header helps clients that drop X-Cache."""
    resp.headers["X-Cache"] = label
    resp.headers["X-Cache-Status"] = label
    return resp


def _parse_json_body():
    if not request.is_json:
        return None, (jsonify({"error": "Content-Type must be application/json"}), 415)
    try:
        payload = request.get_json(silent=False)
    except BadRequest:
        return None, (jsonify({"error": "Malformed JSON body"}), 400)

    if payload is not None and not isinstance(payload, dict):
        return None, (jsonify({"error": "Request body must be a JSON object"}), 400)

    return payload, None


def _generate_unique_code():
    for _ in range(10):
        new_code = Url.generate_code()
        if Url.get_or_none(Url.short_code == new_code) is None:
            return new_code
    raise RuntimeError("Unable to generate a unique short code")


def _log_event_for_url(entry, event_type, details=None):
    # Event.host is required, so only log when this URL has an owner.
    if getattr(entry, "created_by_id", None) is None:
        return None

    host = getattr(entry, "created_by", None)
    if host is None:
        return None

    description = None
    if details is not None:
        description = json.dumps(details)

    event = Event.create(
        title=event_type,
        description=description,
        start_time=datetime.now(),
        host=host,
    )

    Url.update(event=event).where(Url.id == entry.id).execute()
    return event


@url_bp.route("/shorten", methods=["POST"])
def shorten():
    data, error_response = _parse_json_body()
    if error_response:
        return error_response

    data = data or {}
    long_url = data.get("url")
    custom_alias = (data.get("custom_alias") or "").strip()
    user_id = data.get("user_id")

    if long_url is None:
        return jsonify({"error": "URL is missing"}), 400

    if not _is_valid_web_url(long_url):
        return jsonify({"error": "URL must be a valid http/https address"}), 400

    created_by = None
    if user_id is not None:
        if isinstance(user_id, bool) or not isinstance(user_id, int):
            return jsonify({"error": "user_id must be an integer"}), 400
        created_by = User.get_or_none(User.id == user_id)
        if created_by is None:
            return jsonify({"error": "Unknown user"}), 404

    if custom_alias and not CUSTOM_ALIAS_PATTERN.fullmatch(custom_alias):
        return jsonify(
            {
                "error": "Custom alias must be 3-32 characters and contain only letters, numbers, hyphens, or underscores"
            }
        ), 400

    if custom_alias:
        alias_entry = Url.get_or_none(Url.short_code == custom_alias)
        if alias_entry:
            if not alias_entry.revoked and alias_entry.original_url == long_url:
                set_cached_resolve_url(alias_entry.short_code, alias_entry.original_url)
                return jsonify({"short_url": _short_url(alias_entry.short_code)}), 200
            return jsonify({"error": "That custom alias is already taken"}), 409

        entry = Url.create(
            original_url=long_url.strip(),
            short_code=custom_alias,
            created_by=created_by,
            clicks=0,
            revoked=False,
        )
        _log_event_for_url(
            entry,
            "created",
            {"short_code": entry.short_code, "original_url": entry.original_url},
        )
        set_cached_resolve_url(entry.short_code, entry.original_url)
        return jsonify({"short_url": _short_url(custom_alias)}), 201

    new_code = _generate_unique_code()
    entry = Url.create(
        original_url=long_url.strip(),
        short_code=new_code,
        created_by=created_by,
        clicks=0,
        revoked=False,
    )
    _log_event_for_url(
        entry,
        "created",
        {"short_code": entry.short_code, "original_url": entry.original_url},
    )
    set_cached_resolve_url(entry.short_code, entry.original_url)
    return jsonify({"short_url": _short_url(new_code)}), 201


@url_bp.route("/revoke", methods=["POST"])
def revoke():
    data, error_response = _parse_json_body()
    if error_response:
        return error_response

    data = data or {}
    short_code = (data.get("short_code") or "").strip()
    if not short_code:
        return jsonify({"error": "short_code is required"}), 400

    entry = Url.get_or_none(Url.short_code == short_code)
    if entry is None:
        return jsonify({"error": "Unknown short_code"}), 404

    if entry.revoked:
        delete_cached_short_link(short_code)
        return jsonify({"short_code": short_code, "revoked": True}), 200

    Url.update(revoked=True).where(Url.id == entry.id).execute()
    _log_event_for_url(entry, "revoked", {"short_code": short_code})
    delete_cached_short_link(short_code)
    return jsonify({"short_code": short_code, "revoked": True}), 200


@url_bp.route("/analytics/<short_code>", methods=["GET"])
def analytics(short_code):
    entry = Url.get_or_none(Url.short_code == short_code)
    if entry is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"short_code": short_code, "clicks": entry.clicks}), 200


@url_bp.route("/<short_code>/analytics", methods=["GET"])
def analytics_alt(short_code):
    return analytics(short_code)


@url_bp.route("/<short_code>", methods=["DELETE"])
@url_bp.route("/shorten/<short_code>", methods=["DELETE"])
def deactivate(short_code):
    entry = Url.get_or_none(Url.short_code == short_code)
    if entry is None:
        return jsonify({"error": "Not found"}), 404

    if not entry.revoked:
        Url.update(revoked=True).where(Url.id == entry.id).execute()
        _log_event_for_url(entry, "deleted", {"short_code": short_code})
        delete_cached_short_link(short_code)

    return "", 204


@url_bp.route("/<short_code>", methods=["GET"])
def resolve(short_code):
    # Hot path: Redis string only → redirect + X-Cache (no DB, no JSON).
    target_url = get_cached_resolve_url(short_code)
    if target_url is not None:
        return _with_cache_headers(redirect(target_url), "HIT")

    # Cache miss: SELECT on read replica; click counter UPDATE stays on primary.
    db_read.connect(reuse_if_open=True)
    entry = UrlRead.get_or_none(UrlRead.short_code == short_code)
    if entry is None:
        resp = jsonify({"error": "Not found"})
        resp.status_code = 404
        return _with_cache_headers(resp, "MISS")

    if entry.revoked:
        resp = jsonify({"error": "This link has been revoked"})
        resp.status_code = 410
        return _with_cache_headers(resp, "MISS")

    if all(hasattr(Url, attr) for attr in ("update", "clicks", "id")) and hasattr(entry, "id"):
        db.connect(reuse_if_open=True)
        Url.update(clicks=Url.clicks + 1).where(Url.id == entry.id).execute()
        _log_event_for_url(entry, "click", {"short_code": short_code})

    set_cached_resolve_url(short_code, entry.original_url)
    return _with_cache_headers(redirect(entry.original_url), "MISS")
