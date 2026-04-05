#!/usr/bin/env bash
# End-to-end: Docker Compose stack → wait for nginx :8080 → k6 load test
#
# From repo root:
#   chmod +x scripts/run-loadtest.sh
#   ./scripts/run-loadtest.sh
#
# Options:
#   ./scripts/run-loadtest.sh              # full stack + k6 (host k6 binary)
#   ./scripts/run-loadtest.sh --docker-k6  # full stack + k6 via grafana/k6 image
#   ./scripts/run-loadtest.sh --stack-only # start stack and exit (no k6)
#
# Local Flask (run.py) instead of app container — use AFTER db+redis are up:
#   docker compose up -d db redis
#   cp .env.example .env   # if needed; set DATABASE_HOST=localhost, REDIS_URL=redis://127.0.0.1:6379/0
#   uv run run.py          # uses PORT from env, default 5000 — on Mac often PORT=5001
#   K6_DIRECT_APP=1 BASE_URL=http://127.0.0.1:5001 k6 run k6/load.js   # default 500 VUs — use TARGET_VUS=25 with run.py

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

STACK_ONLY=false
DOCKER_K6=false
for arg in "$@"; do
  case "$arg" in
    --stack-only) STACK_ONLY=true ;;
    --docker-k6) DOCKER_K6=true ;;
    -h|--help)
      head -n 25 "$0" | tail -n +2
      exit 0
      ;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  echo "Install Docker Desktop / Docker Engine, then retry."
  exit 1
fi

if [ ! -f .env ]; then
  echo "No .env found. Copying from .env.example — edit secrets if needed."
  cp .env.example .env
fi

echo "==> Building and starting stack (db, redis, app, nginx)..."
docker compose up --build -d

echo "==> Waiting for load balancer http://127.0.0.1:8080/health (up to 120s)..."
ok=false
for i in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:8080/health" >/dev/null; then
    ok=true
    break
  fi
  echo "   ... attempt $i/60"
  sleep 2
done

if [ "$ok" != true ]; then
  echo "Health check failed. Logs: docker compose logs --tail=80 app nginx"
  exit 1
fi
echo "==> LB is up."

if [ "$STACK_ONLY" = true ]; then
  echo "Stack only (--stack-only). Run k6 when ready:"
  echo "  k6 run k6/load.js"
  exit 0
fi

if [ "$DOCKER_K6" = true ]; then
  echo "==> Running k6 in grafana/k6 (K6_IN_DOCKER=1)..."
  docker run --rm \
    -e K6_IN_DOCKER=1 \
    -v "$ROOT:/work" \
    grafana/k6 run /work/k6/load.js
  exit 0
fi

if ! command -v k6 >/dev/null 2>&1; then
  echo "k6 not on PATH. Install: brew install k6"
  echo "Or run:  $0 --docker-k6"
  exit 1
fi

echo "==> Running k6 (default BASE_URL http://127.0.0.1:8080)..."
k6 run k6/load.js
