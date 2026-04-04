from urllib.parse import urlparse

from flask import Blueprint, jsonify, request
from peewee import IntegrityError
from werkzeug.exceptions import BadRequest

from app.models import Url, User


urls_bp = Blueprint("urls", __name__)


def _to_bool(raw):
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return None
    value = str(raw).strip().lower()
    if value in {"true", "1", "yes", "y"}:
        return True
    if value in {"false", "0", "no", "n"}:
        return False
    return None


def _serialize_url(item):
    return {
        "id": item.id,
        "original_url": item.original_url,
        "short_code": item.short_code,
        "title": item.title,
        "user_id": item.created_by_id,
        "is_active": not item.revoked,
        "clicks": item.clicks,
        "created_at": item.created_at.isoformat(timespec="seconds"),
    }


def _is_valid_web_url(value):
    if not isinstance(value, str):
        return False
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _parse_json_body():
    if not request.is_json:
        return None, (jsonify(error={"content_type": "Content-Type must be application/json"}), 415)
    try:
        return request.get_json(silent=False), None
    except BadRequest:
        return None, (jsonify(error={"body": "Malformed JSON body"}), 400)


def _generate_unique_short_code():
    for _ in range(10):
        candidate = Url.generate_code()
        if Url.get_or_none(Url.short_code == candidate) is None:
            return candidate
    raise RuntimeError("Failed to generate a unique short code")


@urls_bp.route("", methods=["GET"])
@urls_bp.route("/", methods=["GET"])
def list_urls():
    query = Url.select().order_by(Url.id)

    user_id = request.args.get("user_id", type=int)
    if user_id is not None:
        query = query.where(Url.created_by_id == user_id)

    is_active_raw = request.args.get("is_active")
    if is_active_raw is not None:
        is_active = _to_bool(is_active_raw)
        if is_active is None:
            return jsonify(error={"is_active": "must be a boolean"}), 400
        query = query.where(Url.revoked == (not is_active))

    return jsonify([_serialize_url(item) for item in query]), 200


@urls_bp.route("/<int:url_id>", methods=["GET"])
def get_url(url_id):
    item = Url.get_or_none(Url.id == url_id)
    if item is None:
        return jsonify(error="Not found"), 404
    return jsonify(_serialize_url(item)), 200


@urls_bp.route("", methods=["POST"])
@urls_bp.route("/", methods=["POST"])
def create_url():
    payload, error_response = _parse_json_body()
    if error_response:
        return error_response

    if not isinstance(payload, dict):
        return jsonify(error={"body": "Request body must be a JSON object"}), 400

    original_url = payload.get("original_url")
    title = payload.get("title")
    user_id = payload.get("user_id")

    if not isinstance(original_url, str) or not original_url.strip():
        return jsonify(error={"original_url": "original_url is required"}), 400

    if not _is_valid_web_url(original_url):
        return jsonify(error={"original_url": "original_url must be a valid http/https URL"}), 400

    if title is not None and not isinstance(title, str):
        return jsonify(error={"title": "title must be a string"}), 400

    created_by = None
    if user_id is not None:
        if not isinstance(user_id, int):
            return jsonify(error={"user_id": "user_id must be an integer"}), 400
        created_by = User.get_or_none(User.id == user_id)
        if created_by is None:
            return jsonify(error={"user_id": "Unknown user"}), 404

    try:
        item = Url.create(
            original_url=original_url.strip(),
            title=title,
            short_code=_generate_unique_short_code(),
            created_by=created_by,
            clicks=0,
            revoked=False,
        )
    except IntegrityError:
        return jsonify(error={"url": "Failed to create URL"}), 409

    return jsonify(_serialize_url(item)), 201


@urls_bp.route("/<int:url_id>", methods=["PUT"])
def update_url(url_id):
    item = Url.get_or_none(Url.id == url_id)
    if item is None:
        return jsonify(error="Not found"), 404

    payload, error_response = _parse_json_body()
    if error_response:
        return error_response

    if not isinstance(payload, dict):
        return jsonify(error={"body": "Request body must be a JSON object"}), 400

    updates = {}

    if "title" in payload:
        title = payload.get("title")
        if title is not None and not isinstance(title, str):
            return jsonify(error={"title": "title must be a string"}), 400
        updates["title"] = title

    if "is_active" in payload:
        is_active = _to_bool(payload.get("is_active"))
        if is_active is None:
            return jsonify(error={"is_active": "is_active must be a boolean"}), 400
        updates["revoked"] = not is_active

    if "original_url" in payload:
        original_url = payload.get("original_url")
        if not isinstance(original_url, str) or not original_url.strip():
            return jsonify(error={"original_url": "original_url must be a non-empty string"}), 400
        if not _is_valid_web_url(original_url):
            return jsonify(error={"original_url": "original_url must be a valid http/https URL"}), 400
        updates["original_url"] = original_url.strip()

    if not updates:
        return jsonify(error={"body": "No valid fields provided"}), 400

    Url.update(updates).where(Url.id == url_id).execute()
    updated = Url.get_by_id(url_id)
    return jsonify(_serialize_url(updated)), 200


@urls_bp.route("/<int:url_id>", methods=["DELETE"])
def delete_url(url_id):
    deleted = Url.delete().where(Url.id == url_id).execute()
    if deleted == 0:
        return jsonify(error="Not found"), 404
    return "", 204


@urls_bp.route("/<int:url_id>/analytics", methods=["GET"])
def url_analytics(url_id):
    item = Url.get_or_none(Url.id == url_id)
    if item is None:
        return jsonify(error="Not found"), 404
    return jsonify({"id": item.id, "short_code": item.short_code, "clicks": item.clicks}), 200