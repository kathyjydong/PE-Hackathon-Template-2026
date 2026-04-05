# Troubleshooting Playbook

This document is a practical "if X happens, try Y" runbook for local and demo-time issues.

## Quick Triage (Run First)

```bash
docker compose ps -a
docker compose logs --tail=120 app
docker compose logs --tail=80 db
docker compose config
```

Use this to answer four questions quickly:

1. Is the service up?
2. Did `app` crash or fail at startup?
3. Is the database healthy?
4. Is the compose file valid?

## If X Happens, Try Y

### Compose fails before starting

If you see:

- `mapping key "environment" already defined`

Try:

1. Remove duplicate keys in `docker-compose.yml`.
2. Validate with `docker compose config`.
3. Retry `docker compose up -d --build`.

### Compose says a volume is undefined

If you see:

- `service "app" refers to undefined volume socket_data`

Try:

1. Add top-level `volumes:` entries for all referenced named volumes.
2. Ensure both `postgres_data` and `socket_data` are declared.
3. Retry `docker compose up -d --build`.

### BASE_URL warning appears

If you see:

- `The "BASE_URL" variable is not set. Defaulting to a blank string.`

Try:

1. Set once in shell: `export BASE_URL=http://localhost`
2. Or persist in `.env`: `BASE_URL=http://localhost`

### App returns JSON, but you cannot see logs

If you see:

- `curl` responses but no log lines where expected

Try:

1. Keep one terminal on logs:

```bash
docker compose logs -f app
```

2. Generate traffic from another terminal:

```bash
PORT=$(docker compose port app 5000 | awk -F: '{print $2}')
curl -i "http://localhost:${PORT}/health"
curl -i "http://localhost:${PORT}/does-not-exist"
```

### Chaos demo does not show restart

If you see:

- `docker compose kill app` leaves app down

Try:

1. Use process crash instead of manual container kill:

```bash
docker compose exec -T app sh -lc 'kill -9 1'
```

2. Watch recovery:

```bash
docker compose ps app
```

### Unexpected 500 with DB column errors

If you see:

- `column t1.clicks does not exist` (or similar schema drift)

Try:

1. Apply idempotent schema fixes:

```bash
docker compose exec -T db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "ALTER TABLE url ADD COLUMN IF NOT EXISTS clicks INTEGER NOT NULL DEFAULT 0; ALTER TABLE url ADD COLUMN IF NOT EXISTS revoked BOOLEAN NOT NULL DEFAULT FALSE; ALTER TABLE url ADD COLUMN IF NOT EXISTS title VARCHAR(255);"'
```

2. Restart app:

```bash
docker compose restart app
```

### `curl http://localhost:PORT/...` fails

If you see:

- You used literal `PORT` text instead of a real number

Try:

```bash
PORT=$(docker compose port app 5000 | awk -F: '{print $2}')
curl -i "http://localhost:${PORT}/health"
```

## Verification Checks

After any fix, verify fast with:

```bash
./scripts/verify-resilience.sh
```

Expected result:

- Summary with all checks passing.

## Incident Notes From Today

1. Duplicate `environment` in compose caused YAML parse failure.
   - Fix: removed duplicate key.
2. Missing `socket_data` volume declaration blocked stack startup.
   - Fix: declared required named volumes.
3. Manual `docker compose kill app` did not reliably demonstrate restart behavior.
   - Fix: switched chaos demo to PID 1 crash command.
4. DB schema drift (`url.clicks` missing) produced 500 errors.
   - Fix: ran idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` commands.
5. Confusion between API response output and app logs.
   - Fix: standardized two-terminal workflow (one for logs, one for requests).

## References

- CI/CD deploy gate: `.github/workflows/cd.yml`
- Emergency runbook: [In Case of Emergency](in-case-of-emergency.md)
