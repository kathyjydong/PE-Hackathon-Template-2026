from datetime import datetime

from flask import Blueprint, jsonify, request

from app.models import Event, Url, User


events_bp = Blueprint("events", __name__)


def _parse_datetime(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value

    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    try:
        # Handles values such as 2026-04-04T12:00:00Z
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp/start_time must be a valid datetime") from exc


def _serialize_event(event, url_id=None):
    return {
        "id": event.id,
        "title": event.title,
        "description": event.description,
        "start_time": event.start_time.isoformat(timespec="seconds"),
        "host_id": event.host_id,
        "url_id": url_id,
    }


@events_bp.route("/events", methods=["GET"])
def list_events():
    user_id = request.args.get("user_id", type=int)
    url_id = request.args.get("url_id", type=int)

    query = Event.select().order_by(Event.id)

    if user_id is not None:
        query = query.where(Event.host_id == user_id)

    if url_id is not None:
        query = query.join(Url).where(Url.id == url_id).distinct()

    events = []
    for event in query:
        associated_url_id = None
        if url_id is not None:
            associated_url_id = url_id
        events.append(_serialize_event(event, associated_url_id))

    return jsonify(events), 200


@events_bp.route("/events", methods=["POST"])
def create_event():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error={"body": "Request body must be a JSON object"}), 400

    host_id = payload.get("host_id", payload.get("user_id"))
    if not isinstance(host_id, int):
        return jsonify(error={"host_id": "host_id or user_id must be an integer"}), 400

    host = User.get_or_none(User.id == host_id)
    if host is None:
        return jsonify(error={"host_id": "Unknown user"}), 404

    title = payload.get("title", payload.get("event_type"))
    if not isinstance(title, str) or not title.strip():
        return jsonify(error={"title": "title or event_type is required"}), 400

    description = payload.get("description", payload.get("details"))
    if description is not None and not isinstance(description, str):
        return jsonify(error={"description": "description/details must be a string"}), 400

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

    associated_url_id = None
    url_id = payload.get("url_id")
    if url_id is not None:
        if not isinstance(url_id, int):
            return jsonify(error={"url_id": "url_id must be an integer"}), 400
        url = Url.get_or_none(Url.id == url_id)
        if url is None:
            return jsonify(error={"url_id": "Unknown url"}), 404
        Url.update(event=event).where(Url.id == url.id).execute()
        associated_url_id = url.id

    return jsonify(_serialize_event(event, associated_url_id)), 201