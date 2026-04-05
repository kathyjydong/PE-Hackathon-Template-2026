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

The project uses Docker Compose with restart policies (`restart: always`) in `docker-compose.yml` for `db`, `app`, and `redis`.

### Start the stack

```bash
docker compose up -d --build
```

### Crash the app process (PID 1) inside the container

```bash
docker compose exec -T app sh -lc 'kill -9 1'
```

### Observe automatic recovery

```bash
docker compose ps
```

Expected:

- The `app` service returns to `Up` automatically.
- Traffic continues once app restarts.

Note:

- `docker compose kill app` is treated as a manual container stop and may not trigger restart policy behavior for chaos testing.
- Crashing PID 1 inside the container better simulates a real process failure.

Optional live watch:

```bash
while true; do docker compose ps; sleep 1; clear; done
```

## Live Demo Checklist

1. Start stack: `docker compose up -d --build`
2. Verify health: `curl -i http://localhost/health`
3. Send garbage data to `/shorten` and show clean JSON 400.
4. Crash app process: `docker compose exec -T app sh -lc 'kill -9 1'`
5. Show container auto-restarts with `docker compose ps`.
6. Hit health again to show service recovered: `curl -i http://localhost/health`

## Structured Logging Screenshot

Goal: show JSON logs with timestamp, log level, and request metadata.

### Start the app

```bash
docker compose up -d --build db redis app
```

### Stream app logs in one terminal

```bash
docker compose logs -f app
```

### Generate log lines from another terminal

```bash
PORT=$(docker compose port app 5000 | awk -F: '{print $2}')
curl -i "http://localhost:${PORT}/health"
curl -i "http://localhost:${PORT}/does-not-exist"
```

Optional error log:

```bash
docker compose stop db
curl -i -X POST "http://localhost:${PORT}/shorten" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com"}'
docker compose start db
```

### What to screenshot

- A JSON log line with `"level":"INFO"` from `/health`
- A JSON log line with `"level":"WARN"` from the 404 request
- A JSON log line with `"level":"ERROR"` if you trigger the optional DB outage step

## Notes

- CI/CD deployment is blocked on failing tests in `.github/workflows/cd.yml`.
- Error handlers are configured to return JSON for HTTP errors and unexpected exceptions.
