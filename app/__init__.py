import os

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template
from time import perf_counter
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from prometheus_client import CollectorRegistry, make_wsgi_app, multiprocess
from werkzeug.exceptions import HTTPException
from app.database import init_db
from app.logging_config import configure_structured_logging
from app.metrics import record_request_metrics, record_exception
from app.redis_client import init_redis
from app.routes import register_routes


def _build_metrics_wsgi_app():
    multiproc_dir = os.getenv("PROMETHEUS_MULTIPROC_DIR", "").strip()
    if not multiproc_dir:
        return make_wsgi_app()

    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)
    return make_wsgi_app(registry=registry)


def create_app():
    load_dotenv()
    configure_structured_logging()

    app = Flask(__name__)
    app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {"/metrics": _build_metrics_wsgi_app()})

    @app.before_request
    def _start_timer():
        from flask import g

        g.request_started_at = perf_counter()

    @app.after_request
    def _log_request(response):
        from flask import g, request

        started = getattr(g, "request_started_at", None)
        latency_ms = None
        if started is not None:
            latency_ms = round((perf_counter() - started) * 1000, 2)

        record_request_metrics(request=request, response=response, latency_ms=latency_ms)

        app.logger.info(
            "Request completed",
            extra={
                "component": "api",
                "method": request.method,
                "path": request.path,
                "status_code": response.status_code,
                "latency_ms": latency_ms,
            },
        )
        return response

    init_redis(app)
    init_db(app)

    register_routes(app)

    @app.route("/")
    def home():
        return render_template("index.html")

    @app.route("/health")
    def health():
        app.logger.info("Health check", extra={"component": "health"})
        return jsonify(status="ok")

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify(error="Not found"), 404

    @app.errorhandler(500)
    def internal_error(_error):
        return jsonify(error="Internal server error"), 500

    @app.errorhandler(HTTPException)
    def handle_http_exception(error):
        app.logger.warning(
            "HTTP error",
            extra={
                "component": "api",
                "status_code": error.code,
            },
        )
        return jsonify(error=error.description), error.code

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        app.logger.exception("Unhandled exception", extra={"component": "api"})
        record_exception()
        return jsonify(error="Internal server error"), 500

    return app