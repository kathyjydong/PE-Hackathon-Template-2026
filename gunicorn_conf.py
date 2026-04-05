"""
Gunicorn settings for Docker / production.

Sync workers (-w 64) cap concurrency at 64: k6 at 500 VUs queues for seconds (bad p95).
Use gthread with modest workers × many threads so Redis resolve hits stay parallel.
"""

import os

from prometheus_client import multiprocess

# Bindings: unix for nginx upstream; TCP for host / k6 direct.
bind = [
    "unix:/tmp/app.sock",
    "0.0.0.0:5000",
]

backlog = int(os.environ.get("GUNICORN_BACKLOG", "2048"))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))
worker_class = os.environ.get("GUNICORN_WORKER_CLASS", "gthread").strip().lower()
workers = int(os.environ.get("GUNICORN_WORKERS", "4"))

if worker_class == "gthread":
    # Extra threads compensate for fewer workers (keeps Redis resolve concurrency up).
    threads = int(os.environ.get("GUNICORN_THREADS", "96"))
    # Avoid accidental 64 workers × 64 threads if an old .env only bumped workers.
    max_conc = int(os.environ.get("GUNICORN_MAX_CONCURRENCY", "512"))
    if workers * threads > max_conc:
        threads = max(1, max_conc // max(workers, 1))
else:
    threads = 1

accesslog = os.environ.get("GUNICORN_ACCESS_LOG", "-")
errorlog = os.environ.get("GUNICORN_ERROR_LOG", "-")
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info").lower()


def child_exit(server, worker):
    multiproc_dir = os.getenv("PROMETHEUS_MULTIPROC_DIR", "").strip()
    if multiproc_dir:
        multiprocess.mark_process_dead(worker.pid)
