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

## Checklist

1. Start stack: `docker compose up -d --build`
2. Verify health: `curl -i http://localhost/health`
3. Send garbage data to `/shorten` and show clean JSON 400.
4. Kill app container: `docker compose kill app`
5. Show container auto-restarts with `docker compose ps`.
6. Hit health again to show service recovered: `curl -i http://localhost/health`

## Notes

- CI/CD deployment is blocked on failing tests in `.github/workflows/cd.yml`.
- Error handlers are configured to return JSON for HTTP errors and unexpected exceptions.
- Emergency response runbook: [In Case of Emergency](in-case-of-emergency.md)
