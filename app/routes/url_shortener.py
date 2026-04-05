import os
import re

from flask import Blueprint, request, jsonify, redirect
from app.models import Url, db, db_read
from app.models.schema import Url as _UrlSchema  # real Peewee model for bind_ctx
from app.short_link_cache import (
    delete_cached_short_link,
    delete_cached_url_to_code,
    get_cached_resolve_url,
    get_cached_url_to_code,
    set_cached_resolve_url,
    set_cached_url_to_code,
)

url_bp = Blueprint('url', __name__)

CUSTOM_ALIAS_PATTERN = re.compile(r'^[A-Za-z0-9_-]{3,32}$')


def _base_url():
    return os.getenv("BASE_URL", request.host_url.rstrip("/"))


def _short_url(short_code):
    return f"{_base_url()}/{short_code}"


def _with_cache_headers(resp, label: str):
    """HIT/MISS for k6 and proxies; duplicate header helps clients that drop X-Cache."""
    resp.headers["X-Cache"] = label
    resp.headers["X-Cache-Status"] = label
    return resp


def _cache_url_pair(short_code: str, original_url: str) -> None:
    """Populate both forward and reverse Redis entries for a URL pair."""
    set_cached_resolve_url(short_code, original_url)
    set_cached_url_to_code(original_url, short_code)


@url_bp.route('/shorten', methods=['POST'])
def shorten():
    data = request.get_json(silent=True) or {}
    long_url = data.get('url')
    custom_alias = (data.get('custom_alias') or '').strip()

    if not long_url:
        return jsonify({"error": "URL is missing"}), 400

    if custom_alias and not CUSTOM_ALIAS_PATTERN.fullmatch(custom_alias):
        return jsonify({
            "error": "Custom alias must be 3-32 characters and contain only letters, numbers, hyphens, or underscores"
        }), 400

    if custom_alias:
        alias_entry = Url.get_or_none(Url.short_code == custom_alias)
        if alias_entry:
            if not alias_entry.revoked and alias_entry.original_url == long_url:
                _cache_url_pair(alias_entry.short_code, alias_entry.original_url)
                return jsonify({"short_url": _short_url(alias_entry.short_code)})
            return jsonify({"error": "That custom alias is already taken"}), 409

        created = Url.create(original_url=long_url, short_code=custom_alias)
        _cache_url_pair(created.short_code, created.original_url)
        return jsonify({"short_url": _short_url(custom_alias)}), 201

    # Hot path: check reverse cache before hitting the read replica
    cached_code = get_cached_url_to_code(long_url)
    if cached_code is not None:
        return _with_cache_headers(
            jsonify({"short_url": _short_url(cached_code)}), "HIT"
        )

    # Cache miss: query read replica for existing non-revoked entry
    db_read.connect(reuse_if_open=True)
    with db_read.bind_ctx([_UrlSchema]):
        existing = Url.get_or_none(
            (Url.original_url == long_url) & (Url.revoked == False)  # noqa: E712
        )

    if existing:
        _cache_url_pair(existing.short_code, existing.original_url)
        return _with_cache_headers(
            jsonify({"short_url": _short_url(existing.short_code)}), "MISS"
        )

    # New URL — write to primary
    new_code = Url.generate_code()
    created = Url.create(original_url=long_url, short_code=new_code)
    _cache_url_pair(created.short_code, created.original_url)
    return _with_cache_headers(
        jsonify({"short_url": _short_url(new_code)}), "MISS"
    ), 201


@url_bp.route("/revoke", methods=["POST"])
def revoke():
    """Mark a short link as revoked. The row stays in the database; redirects stop."""
    data = request.get_json(silent=True) or {}
    short_code = (data.get("short_code") or "").strip()
    if not short_code:
        return jsonify({"error": "short_code is required"}), 400

    entry = Url.get_or_none(Url.short_code == short_code)
    if entry is None:
        return jsonify({"error": "Unknown short_code"}), 404

    if entry.revoked:
        delete_cached_short_link(short_code)
        delete_cached_url_to_code(entry.original_url)
        return jsonify({"short_code": short_code, "revoked": True}), 200

    Url.update(revoked=True).where(Url.id == entry.id).execute()
    delete_cached_short_link(short_code)
    delete_cached_url_to_code(entry.original_url)
    return jsonify({"short_code": short_code, "revoked": True}), 200


@url_bp.route('/<short_code>', methods=['GET'])
def resolve(short_code):
    # Hot path: Redis forward cache → redirect with no DB touch
    target_url = get_cached_resolve_url(short_code)
    if target_url is not None:
        return _with_cache_headers(redirect(target_url), "HIT")

    # Cache miss: use read replica (single-writer, multi-reader pattern)
    db_read.connect(reuse_if_open=True)
    with db_read.bind_ctx([_UrlSchema]):
        entry = Url.get_or_none(Url.short_code == short_code)

    if entry is None:
        resp = jsonify({"error": "Not found"})
        resp.status_code = 404
        return _with_cache_headers(resp, "MISS")

    if entry.revoked:
        resp = jsonify({"error": "This link has been revoked"})
        resp.status_code = 410
        return _with_cache_headers(resp, "MISS")

    # Populate both caches on miss so the next request is served from Redis
    _cache_url_pair(short_code, entry.original_url)
    return _with_cache_headers(redirect(entry.original_url), "MISS")
