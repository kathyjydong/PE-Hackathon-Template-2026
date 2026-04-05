import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    # FLASK_DEBUG in .env turns this on; override for load tests, e.g.:
    #   FLASK_DEBUG=false uv run run.py
    _debug = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes")
    _port = int(os.environ.get("PORT", "5000"))
    # threaded=True: default dev server is single-threaded → k6 sees connection stalls / failures.
    # use_reloader only when debugging so load tests run one process.
    app.run(
        debug=_debug,
        port=_port,
        threaded=True,
        use_reloader=_debug,
    )
