from flask import Blueprint, request, jsonify, redirect, abort
from app.models import Url

url_bp = Blueprint('url', __name__)


# Method to generate a short code for URL
# Will be changed later for things like custom url and password protected urls but this is for MVP
@url_bp.route('/shorten', methods=['POST'])
def shorten():
    data = request.get_json()
    long_url = data.get('url')
    if not long_url:
        return jsonify({"error": "URL is missing"}), 400

# Logic for if it already exists withing the docker container db just return it
    existing = Url.get_or_none(Url.original_url == long_url)
    if existing:
        return jsonify({"short_url": f"http://localhost:5000/{existing.short_code}"})

# Save new link to the Postgres docker container
    new_code = Url.generate_code()
    Url.create(original_url=long_url, short_code=new_code)
    return jsonify({"short_url": f"http://localhost:5000/{new_code}"}), 201

# Get endpoint for getting the original URL from the short code. Logic behind redirect
@url_bp.route('/<short_code>', methods=['GET'])
def resolve(short_code):
    entry = Url.get_or_none(Url.short_code == short_code)
    if entry:
        return redirect(entry.original_url)
    return abort(404)