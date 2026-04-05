# Failure Modes

This runbook documents how the app behaves under common failures and how to demo recovery.

## Graceful Failure (Bad Input)

Goal: bad input should return clean JSON errors (not stack traces and not HTML error pages).

### Example 1: Missing URL

```bash
curl -i -X POST http://localhost/shorten \
  -H "Content-Type: application/json" \
  -d '{}'
```

Expected:

- HTTP 400
- JSON body:

```json
{"error":"URL is missing"}
```

### Example 2: Garbage JSON payload

```bash
curl -i -X POST http://localhost/shorten \
  -H "Content-Type: application/json" \
  -d '{not-valid-json'
```

Expected:

- HTTP 400
- JSON body:

```json
{"error":"URL is missing"}
```

### Example 3: Invalid custom alias

```bash
curl -i -X POST http://localhost/shorten \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com","custom_alias":"bad alias!"}'
```

Expected:

- HTTP 400
- JSON body with validation error message

## Chaos Mode (Container Kill + Auto Restart)

The project uses Docker Compose with restart policies (`restart: always`) in `docker-compose.yml` for `db`, `app`, and `nginx`.

### Start the stack

```bash
docker compose up -d --build
```

### Kill the app container

```bash
docker compose kill app
```

### Observe automatic recovery

```bash
docker compose ps
```

Expected:

- The `app` service returns to `Up` automatically.
- Traffic continues once app restarts.

Optional live watch:

```bash
while true; do docker compose ps; sleep 1; clear; done
```

## Live Demo Checklist

1. Start stack: `docker compose up -d --build`
2. Verify health: `curl -i http://localhost/health`
3. Send garbage data to `/shorten` and show clean JSON 400.
4. Kill app container: `docker compose kill app`
5. Show container auto-restarts with `docker compose ps`.
6. Hit health again to show service recovered: `curl -i http://localhost/health`

## Notes

- CI/CD deployment is blocked on failing tests in `.github/workflows/cd.yml`.
- Error handlers are configured to return JSON for HTTP errors and unexpected exceptions.

## Decision Log

This section records major technical choices and the reason each was selected.

### Decision: Use Redis for short-link resolve cache

Context:

- The hottest endpoint is `GET /<short_code>`.
- Repeated reads for the same short code can bottleneck on database lookups under load.

Choice:

- Cache `short_code -> original_url` in Redis.
- On resolve:
  - Cache hit: redirect immediately.
  - Cache miss: read from DB, then write-through into cache.

Why this choice:

- Reduces DB round-trips on hot keys.
- Lowers p95 latency on repeated resolves.
- Straightforward invalidation path on revoke/delete.

Tradeoffs:

- Added operational dependency (Redis service health matters).
- Need cache invalidation correctness on revoke/update/delete.
- Slight complexity increase in resolve path.

Alternatives considered:

- No cache (simpler, but higher DB pressure and slower hot-path latency).
- In-process cache only (faster local reads, but not shared across scaled app instances).

### Decision: Use Nginx as reverse proxy + load balancer

Context:

- The app is scaled to multiple workers/containers.
- Need one stable public entrypoint and predictable routing behavior.

Choice:

- Place Nginx in front of Flask app containers.
- Use `least_conn` balancing strategy.

Why this choice:

- Simple and proven L7 proxy for hackathon-scale deployment.
- Supports centralized headers, forwarding, and TLS termination.
- Enables one public host/port while scaling app replicas behind it.

Tradeoffs:

- Another hop in the request path.
- Requires proxy config maintenance (headers, timeouts, TLS file paths).

Alternatives considered:

- Directly exposing app container(s) (less control, weaker production posture).
- Cloud-managed LB only (good option, but less local reproducibility for team debugging).

### Decision: Keep strict request validation at route boundaries

Context:

- Hidden tests send malformed JSON, wrong content type, and invalid URL values.

Choice:

- Validate `Content-Type`, JSON shape, and URL format before DB writes.
- Return 400/415 with JSON error payloads.

Why this choice:

- Prevents crashing on malformed input.
- Produces predictable API behavior for graders and clients.
- Blocks invalid records from entering persistence.

Tradeoffs:

- Slightly more verbose route code.
- Need consistent validation across parallel endpoints (`/shorten` and `/urls`).
