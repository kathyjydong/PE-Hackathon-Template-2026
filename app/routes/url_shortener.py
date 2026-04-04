from flask import Blueprint, request, jsonify, redirect, abort
from app.models import Url # Look how clean this import is now!

url_bp = Blueprint('url', __name__)

@url_bp.route('/shorten', methods=['POST'])
def shorten():
    data = request.get_json()
    long_url = data.get('url')
    if not long_url:
        return jsonify({"error": "URL is missing"}), 400

    # If it exists in the Docker DB already, just return it
    existing = Url.get_or_none(Url.original_url == long_url)
    if existing:
        return jsonify({"short_url": f"http://localhost:5000/{existing.short_code}"})

    # Save new link to the Postgres container
    new_code = Url.generate_code()
    Url.create(original_url=long_url, short_code=new_code)
    return jsonify({"short_url": f"http://localhost:5000/{new_code}"}), 201

@url_bp.route('/<short_code>', methods=['GET'])
def resolve(short_code):
    entry = Url.get_or_none(Url.short_code == short_code)
    if entry:
        return redirect(entry.original_url)
    return abort(404)