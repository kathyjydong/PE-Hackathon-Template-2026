# Deploy Guide

This guide covers how to get the app live and how to roll back safely.

## Deployment Model

Current production stack (from `docker-compose.yml`):

- `db` (PostgreSQL)
- `redis`
- `app` (Gunicorn + Flask)

All three services use `restart: always`.

## Prerequisites

- Ubuntu/Debian VM or droplet with Docker and Docker Compose plugin installed
- Git installed on the server
- Repo cloned on server (example path: `/opt/pe-hackathon`)
- `.env` present on server with production values
- Port access allowed by firewall (at minimum your app port and SSH)

Recommended `.env` production values:

- `FLASK_DEBUG=false`
- Strong `DATABASE_PASSWORD`
- `BASE_URL=https://your-domain`
- `GUNICORN_WORKERS` sized for your VM

## First-Time Live Setup

Run on server:

```bash
cd /opt/pe-hackathon
cp .env.example .env
# edit .env for production values

docker compose pull || true
docker compose up -d --build db redis app
```

Validate:

```bash
PORT=$(docker compose port app 5000 | awk -F: '{print $2}')
curl -i "http://localhost:${PORT}/health"
```

Expected: `HTTP/1.1 200` and JSON body `{"status":"ok"}`.

## Standard Deploy (Manual)

Use this for direct server deploys:

```bash
cd /opt/pe-hackathon
git fetch origin
git checkout main
git reset --hard origin/main
docker compose up -d --build db redis app
```

Post-deploy checks:

```bash
PORT=$(docker compose port app 5000 | awk -F: '{print $2}')
curl -fsS "http://localhost:${PORT}/health"
./scripts/verify-resilience.sh
```

If both pass, deployment is healthy.

## Standard Deploy (GitHub Actions CD)

Current CD flow in `.github/workflows/cd.yml`:

1. Triggered after CI workflow completes
2. Deploy job runs only when:
   - CI conclusion is success
   - branch is `staging` or `main`
3. CD re-runs tests, builds Docker image, SSHes into server, and runs:

```bash
git fetch origin
git reset --hard origin/$DEPLOY_BRANCH
docker compose up --build -d
```

## Rollback Guide

### Fast rollback to previous commit

If latest deploy is bad, run on server:

```bash
cd /opt/pe-hackathon
git log --oneline -n 5
# choose last known good commit hash
git checkout <GOOD_COMMIT_SHA>
docker compose up -d --build db redis app
```

Verify:

```bash
PORT=$(docker compose port app 5000 | awk -F: '{print $2}')
curl -i "http://localhost:${PORT}/health"
```

When stable, pin rollback branch/tag in git so it is reproducible.

### Rollback to previous tagged release (recommended)

```bash
cd /opt/pe-hackathon
git fetch --tags
git checkout tags/<GOOD_TAG>
docker compose up -d --build db redis app
```

## Emergency Recovery Commands

Check runtime state:

```bash
docker compose ps -a
docker compose logs --tail=200 app
```

Restart only app service:

```bash
docker compose restart app
```

Recreate stack without deleting DB volume:

```bash
docker compose down
docker compose up -d --build db redis app
```

## Data Safety Notes

- Do not use `docker compose down -v` in production unless you explicitly want to delete database data.
- `postgres_data` is the persistent DB volume.
- Always keep regular Postgres backups before major changes.

## Suggested Release Process

1. Merge to `staging`, validate smoke tests
2. Run load/resilience checks
3. Promote to `main`
4. Confirm health and error rate after deploy
5. If regression appears, rollback immediately using commit/tag steps above
