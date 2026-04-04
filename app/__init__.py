from dotenv import load_dotenv
from flask import Flask, jsonify
from app.database import init_db, db 
from app.routes import register_routes

def create_app():
    load_dotenv()

    app = Flask(__name__)

    init_db(app)

    from app import models  


    with app.app_context():
        db.create_tables([models.User, models.Event, models.Url])
        print("Successfully created database tables!")
   

    register_routes(app)

    @app.route("/health")
    def health():
        return jsonify(status="ok")

    return app