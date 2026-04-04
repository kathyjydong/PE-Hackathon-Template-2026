import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    # FLASK_DEBUG in .env turns this on; override for load tests, e.g.:
    #   FLASK_DEBUG=false uv run run.py
    _debug = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes")
    app.run(debug=_debug)
