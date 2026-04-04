import csv
from datetime import datetime

from flask import Blueprint, jsonify, request
from peewee import IntegrityError, chunked

from app.models import User


users_bp = Blueprint("users", __name__)


def _serialize_user(user):
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "created_at": user.created_at.isoformat(timespec="seconds"),
    }


def _normalize_string(value):
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _parse_created_at(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        raise ValueError("created_at must use YYYY-MM-DD HH:MM:SS format")


def _parse_user_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError({"body": "Request body must be a JSON object"})

    errors = {}
    username = _normalize_string(payload.get("username"))
    email = _normalize_string(payload.get("email"))

    if "username" in payload and not isinstance(payload.get("username"), str):
        errors["username"] = "must be a string"
    if "email" in payload and not isinstance(payload.get("email"), str):
        errors["email"] = "must be a string"

    if payload.get("username") is None and "username" not in payload:
        errors["username"] = "is required"
    if payload.get("email") is None and "email" not in payload:
        errors["email"] = "is required"

    if errors:
        raise ValueError(errors)

    if username is None:
        raise ValueError({"username": "cannot be empty"})
    if email is None:
        raise ValueError({"email": "cannot be empty"})

    return username, email


@users_bp.route("/users/bulk", methods=["POST"])
def bulk_load_users():
    uploaded = request.files.get("file")
    if uploaded is None:
        return jsonify(error={"file": "is required"}), 400

    raw_text = uploaded.read().decode("utf-8-sig")
    reader = csv.DictReader(raw_text.splitlines())
    if not reader.fieldnames:
        return jsonify(error={"file": "must contain a CSV header"}), 400

    required_headers = {"username", "email"}
    missing_headers = required_headers - set(reader.fieldnames)
    if missing_headers:
        return jsonify(error={"file": f"missing required columns: {', '.join(sorted(missing_headers))}"}), 400

    rows = []
    try:
        for row in reader:
            username = _normalize_string(row.get("username"))
            email = _normalize_string(row.get("email"))
            if username is None or email is None:
                return jsonify(error={"file": "each row must include username and email"}), 400

            user_row = {
                "username": username,
                "email": email,
                "password_hash": _normalize_string(row.get("password_hash")) or "",
            }

            row_id = _normalize_string(row.get("id"))
            if row_id is not None:
                user_row["id"] = int(row_id)

            created_at = row.get("created_at")
            if created_at not in (None, ""):
                user_row["created_at"] = _parse_created_at(created_at)

            rows.append(user_row)
    except ValueError as exc:
        return jsonify(error={"file": str(exc)}), 400

    before_count = User.select().count()
    with User._meta.database.atomic():
        for batch in chunked(rows, 100):
            User.insert_many(batch).on_conflict_ignore().execute()

    inserted = User.select().count() - before_count
    return jsonify(count=inserted), 201


@users_bp.route("/users", methods=["GET"])
def list_users():
    query = User.select().order_by(User.id)

    page = request.args.get("page", type=int)
    per_page = request.args.get("per_page", type=int)
    if page is not None or per_page is not None:
        page = page or 1
        per_page = per_page or 20
        if page < 1 or per_page < 1:
            return jsonify(error={"pagination": "page and per_page must be positive integers"}), 400
        query = query.paginate(page, per_page)

    return jsonify([_serialize_user(user) for user in query])


@users_bp.route("/users/<int:user_id>", methods=["GET"])
def get_user(user_id):
    user = User.get_or_none(User.id == user_id)
    if user is None:
        return jsonify(error="Not found"), 404
    return jsonify(_serialize_user(user))


@users_bp.route("/users", methods=["POST"])
def create_user():
    payload = request.get_json(silent=True)
    try:
        username, email = _parse_user_payload(payload)
    except ValueError as exc:
        return jsonify(error=exc.args[0]), 400

    # Using an atomic transaction to handle the creation/reconciliation
    with User._meta.database.atomic():
        try:
            # Try to create the user
            user = User.create(username=username, email=email, password_hash="")
            return jsonify(_serialize_user(user)), 201
        except IntegrityError:
            # If creation fails, find WHY. 
            # Is it the username, the email, or both?
            existing = User.get_or_none((User.username == username) | (User.email == email))
            
            if existing:
                try:
                    # Attempt to update the existing record to match the new input
                    # This effectively turns the POST into an Upsert
                    existing.username = username
                    existing.email = email
                    existing.save()
                    return jsonify(_serialize_user(existing)), 201
                except IntegrityError:
                    # This happens if the update itself conflicts with a THIRD record
                    return jsonify(error={"user": "reconciliation failed: username or email taken"}), 409
            
            return jsonify(error={"user": "username or email already exists"}), 409


@users_bp.route("/users/<int:user_id>", methods=["PUT"])
def update_user(user_id):
    user = User.get_or_none(User.id == user_id)
    if user is None:
        return jsonify(error="Not found"), 404

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error={"body": "Request body must be a JSON object"}), 400

    updates = {}
    errors = {}

    if "username" in payload:
        username = payload.get("username")
        if not isinstance(username, str):
            errors["username"] = "must be a string"
        else:
            username = username.strip()
            if not username:
                errors["username"] = "cannot be empty"
            else:
                updates["username"] = username

    if "email" in payload:
        email = payload.get("email")
        if not isinstance(email, str):
            errors["email"] = "must be a string"
        else:
            email = email.strip()
            if not email:
                errors["email"] = "cannot be empty"
            else:
                updates["email"] = email

    if errors:
        return jsonify(error=errors), 400
    if not updates:
        return jsonify(error={"body": "No valid fields provided"}), 400

    try:
        User.update(updates).where(User.id == user_id).execute()
    except IntegrityError:
        return jsonify(error={"user": "username or email already exists"}), 409

    user = User.get_by_id(user_id)
    return jsonify(_serialize_user(user))


@users_bp.route("/users/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    deleted = User.delete().where(User.id == user_id).execute()
    if deleted == 0:
        return jsonify(error="Not found"), 404
    return "", 204