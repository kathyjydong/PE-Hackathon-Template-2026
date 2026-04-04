from dotenv import load_dotenv
from flask import Flask, jsonify
from app.database import init_db
from app.routes import register_routes

def create_app():
    load_dotenv()

    app = Flask(__name__)

    init_db(app)

    register_routes(app)

    @app.route("/health")
    def health():
        return jsonify(status="ok")

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify(error="Not found"), 404

    @app.errorhandler(500)
    def internal_error(_error):
        return jsonify(error="Internal server error"), 500

    return app