from dotenv import load_dotenv
from flask import Flask, jsonify, render_template
from app.database import init_db
from app.routes import register_routes

def create_app():
    load_dotenv()

    app = Flask(__name__)

    init_db(app)

    register_routes(app)

    @app.route("/")
    def home():
        return render_template("index.html")

    @app.route("/health")
    def health():
        return jsonify(status="ok")

    return app