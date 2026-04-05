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

    cleaned = value.strip()
    if not cleaned:
        return False

    # Reject whitespace anywhere inside the URL string
    if any(ch.isspace() for ch in cleaned):
        return False

    parsed = urlparse(cleaned)

    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
        and bool(parsed.hostname)
    )


def _parse_json_body():
    if not request.is_json:
        return None, (
            jsonify(error={"content_type": "Content-Type must be application/json"}),
            415,
        )
    try:
        payload = request.get_json(silent=False)
    except BadRequest:
        return None, (jsonify(error={"body": "Malformed JSON body"}), 400)

    if not isinstance(payload, dict):
        return None, (jsonify(error={"body": "Request body must be a JSON object"}), 400)

    return payload, None


def _generate_unique_short_code():
    for _ in range(10):
        candidate = Url.generate_code()
        if Url.get_or_none(Url.short_code == candidate) is None:
            return candidate
    raise RuntimeError("Failed to generate a unique short code")


def _parse_query_int(name):
    raw = request.args.get(name)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an integer")


def _extract_url_value(payload):
    if "original_url" in payload:
        return payload.get("original_url"), "original_url", True
    if "url" in payload:
        return payload.get("url"), "url", True
    return None, "original_url", False


def _validate_url_field(value, field_name):
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a valid http/https URL")

    if value is None:
        raise ValueError(f"{field_name} must be a valid http/https URL")

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a valid http/https URL")

    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} must be a valid http/https URL")

    if not _is_valid_web_url(cleaned):
        raise ValueError(f"{field_name} must be a valid http/https URL")

    return cleaned


@urls_bp.route("", methods=["GET"])
@urls_bp.route("/", methods=["GET"])
def list_urls():
    try:
        user_id = _parse_query_int("user_id")
    except ValueError as exc:
        return jsonify(error={"user_id": str(exc)}), 400

    query = Url.select().order_by(Url.id)

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

    original_url_raw, url_field, url_present = _extract_url_value(payload)
    title = payload.get("title")
    user_id = payload.get("user_id")

    if not url_present:
        return jsonify(error={url_field: f"{url_field} is required"}), 400

    try:
        original_url = _validate_url_field(original_url_raw, url_field)
    except ValueError as exc:
        return jsonify(error={url_field: str(exc)}), 400

    if title is not None and not isinstance(title, str):
        return jsonify(error={"title": "title must be a string"}), 400

    created_by = None
    if user_id is not None:
        if isinstance(user_id, bool) or not isinstance(user_id, int):
            return jsonify(error={"user_id": "user_id must be an integer"}), 400
        created_by = User.get_or_none(User.id == user_id)
        if created_by is None:
            return jsonify(error={"user_id": "Unknown user"}), 404

    try:
        item = Url.create(
            original_url=original_url,
            title=title,
            short_code=_generate_unique_short_code(),
            created_by=created_by,
            clicks=0,
            revoked=False,
        )
    except IntegrityError:
        return jsonify(error={"url": "Failed to create URL"}), 409
    except RuntimeError:
        return jsonify(error={"short_code": "Failed to generate a unique short code"}), 500

    return jsonify(_serialize_url(item)), 201


@urls_bp.route("/<int:url_id>", methods=["PUT"])
def update_url(url_id):
    item = Url.get_or_none(Url.id == url_id)
    if item is None:
        return jsonify(error="Not found"), 404

    payload, error_response = _parse_json_body()
    if error_response:
        return error_response

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

    original_url_raw, url_field, url_present = _extract_url_value(payload)
    if url_present:
        try:
            updates["original_url"] = _validate_url_field(original_url_raw, url_field)
        except ValueError as exc:
            return jsonify(error={url_field: str(exc)}), 400

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