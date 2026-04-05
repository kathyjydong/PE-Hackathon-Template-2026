import json
from datetime import datetime

from flask import Blueprint, jsonify, request
from werkzeug.exceptions import BadRequest

from app.models import Event, Url, User


events_bp = Blueprint("events", __name__)


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


def _parse_query_int(name):
    raw = request.args.get(name)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValueError(name)


def _parse_datetime(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise ValueError("timestamp/start_time must be a valid datetime string")

    text = value.strip()

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp/start_time must be a valid datetime") from exc


def _normalize_details(payload):
    # Canonical alias used by the tests
    if "details" in payload:
        details = payload.get("details")

        if details is None:
            return None

        if isinstance(details, (dict, list)):
            return json.dumps(details)

        # Accept stringified JSON object/array, but reject loose strings like "hello"
        if isinstance(details, str):
            try:
                parsed = json.loads(details)
            except (TypeError, ValueError):
                raise ValueError("details must be a JSON object or array")

            if isinstance(parsed, (dict, list)):
                return json.dumps(parsed)

            raise ValueError("details must be a JSON object or array")

        raise ValueError("details must be a JSON object or array")

    # Backward-compatible alias
    description = payload.get("description")
    if description is None:
        return None
    if isinstance(description, (dict, list)):
        return json.dumps(description)
    if isinstance(description, str):
        return description

    raise ValueError("description must be a string, JSON object, or JSON array")


def _deserialize_description(value):
    if isinstance(value, str) and value:
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value
    return value


def _get_event_url_id(event):
    linked_url = event.urls.order_by(Url.id).first()
    return linked_url.id if linked_url else None


def _serialize_event(event):
    description = _deserialize_description(event.description)

    return {
        "id": event.id,
        "event_type": event.title,
        "details": description,
        "timestamp": event.start_time.isoformat(timespec="seconds"),
        "user_id": event.host_id,
        "url_id": _get_event_url_id(event),

        # Backward-compatible aliases
        "title": event.title,
        "description": description,
        "start_time": event.start_time.isoformat(timespec="seconds"),
        "host_id": event.host_id,
    }


@events_bp.route("/events", methods=["GET"])
def list_events():
    try:
        user_id = _parse_query_int("user_id")
        url_id = _parse_query_int("url_id")
    except ValueError as exc:
        field = str(exc)
        return jsonify(error={field: f"{field} must be an integer"}), 400

    event_type = request.args.get("event_type")

    query = Event.select().order_by(Event.id)

    if user_id is not None:
        query = query.where(Event.host_id == user_id)

    if url_id is not None:
        query = query.join(Url).where(Url.id == url_id).distinct()

    if event_type is not None:
        query = query.where(Event.title == event_type)

    return jsonify([_serialize_event(event) for event in query]), 200


@events_bp.route("/events", methods=["POST"])
def create_event():
    payload, error_response = _parse_json_body()
    if error_response:
        return error_response

    host_id = payload.get("host_id", payload.get("user_id"))
    if isinstance(host_id, bool) or not isinstance(host_id, int):
        return jsonify(error={"host_id": "host_id or user_id must be an integer"}), 400

    host = User.get_or_none(User.id == host_id)
    if host is None:
        return jsonify(error={"host_id": "Unknown user"}), 404

    title = payload.get("title", payload.get("event_type"))
    if not isinstance(title, str) or not title.strip():
        return jsonify(error={"title": "title or event_type is required"}), 400

    try:
        description = _normalize_details(payload)
    except ValueError as exc:
        if "details" in payload:
            return jsonify(error={"details": str(exc)}), 400
        return jsonify(error={"description": str(exc)}), 400

    start_time_raw = payload.get("start_time", payload.get("timestamp"))
    try:
        start_time = _parse_datetime(start_time_raw) or datetime.now()
    except ValueError as exc:
        return jsonify(error={"start_time": str(exc)}), 400

    event = Event.create(
        title=title.strip(),
        description=description,
        start_time=start_time,
        host=host,
    )

    url_id = payload.get("url_id")
    if url_id is not None:
        if isinstance(url_id, bool) or not isinstance(url_id, int):
            return jsonify(error={"url_id": "url_id must be an integer"}), 400

        url = Url.get_or_none(Url.id == url_id)
        if url is None:
            return jsonify(error={"url_id": "Unknown url"}), 404

        Url.update(event=event).where(Url.id == url.id).execute()

    event = Event.get_by_id(event.id)
    return jsonify(_serialize_event(event)), 201