import os
import re

from flask import Blueprint, request, jsonify, redirect, abort
from app.models import Url

url_bp = Blueprint('url', __name__)

CUSTOM_ALIAS_PATTERN = re.compile(r'^[A-Za-z0-9_-]{3,32}$')


def _base_url():
    return os.getenv("BASE_URL", request.host_url.rstrip("/"))


def _short_url(short_code):
    return f"{_base_url()}/{short_code}"


# Method to generate a short code for URL
# Will be changed later for things like custom url and password protected urls but this is for MVP
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
            if alias_entry.original_url == long_url:
                return jsonify({"short_url": _short_url(alias_entry.short_code)})
            return jsonify({"error": "That custom alias is already taken"}), 409

        Url.create(original_url=long_url, short_code=custom_alias)
        return jsonify({"short_url": _short_url(custom_alias)}), 201

# Logic for if it already exists within the docker container db just return it
    existing = Url.get_or_none(Url.original_url == long_url)
    if existing:
        return jsonify({"short_url": _short_url(existing.short_code)})

# Save new link to the Postgres docker container
    new_code = Url.generate_code()
    Url.create(original_url=long_url, short_code=new_code)
    return jsonify({"short_url": _short_url(new_code)}), 201

# Get endpoint for getting the original URL from the short code. Logic behind redirect
@url_bp.route('/<short_code>', methods=['GET'])
def resolve(short_code):
    entry = Url.get_or_none(Url.short_code == short_code)
    if entry:
        return redirect(entry.original_url)
    return abort(404)