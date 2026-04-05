# Decision Log

This document captures major technical and architectural decisions in the current codebase.

## System Architecture (Current)

Request path:

1. Nginx accepts traffic on HTTP and HTTPS and forwards requests upstream.
2. Gunicorn serves the Flask app (multiple workers) through a shared Unix socket.
3. Flask routes validate input and execute business logic.
4. PostgreSQL stores durable entities (users, events, urls).
5. Redis serves the short-link hot path cache.
6. Prometheus metrics are exposed from `/metrics`, and structured JSON logs are emitted to stdout.

Code references:

- App factory and middleware wiring: `app/__init__.py`
- DB init and request DB connection policy: `app/database.py`
- Data model schema: `app/models/schema.py`
- Routing modules: `app/routes/`
- Redis cache behavior: `app/short_link_cache.py`, `app/redis_client.py`
- Runtime topology: `docker-compose.yml`, `nginx.conf`
- CI/CD deployment gate: `.github/workflows/ci.yml`, `.github/workflows/cd.yml`

## Decision 1: Application Factory + Blueprint Module Boundaries

Context:

- The project needs to evolve quickly across multiple API areas (users, events, url-shortening, url CRUD) while staying testable.

Choice:

- Use a Flask application factory (`create_app`) to centralize setup.
- Register route domains as separate blueprints (`url`, `users`, `events`, `urls`).

Why this choice:

- Keeps cross-cutting concerns (logging, metrics, error handling, DB/Redis init) in one startup path.
- Reduces coupling between route domains.
- Improves maintainability for parallel feature work and hidden-test fixes.

Tradeoffs:

- Validation and utility helpers can become duplicated across route modules.
- Blueprint-level conventions must be kept consistent manually.

Alternatives considered:

- Single monolithic routes file (faster to start, harder to maintain).
- Class-based layered architecture (cleaner abstraction, heavier for hackathon speed).

## Decision 2: Peewee ORM with Explicit Schema Ownership

Context:

- Need relational data with constraints and simple migration-like safety under hackathon timelines.

Choice:

- Use Peewee models (`User`, `Event`, `Url`) with explicit fields and foreign keys.
- Keep bootstrap-safe DDL in startup (`create_tables(..., safe=True)` + idempotent `ALTER TABLE ... IF NOT EXISTS`).

Why this choice:

- Fast productivity with SQL-backed correctness.
- Foreign keys encode ownership/lifecycle relationships in database semantics.
- Startup safety protects repeated deploys when schema is partially initialized.

Tradeoffs:

- Startup DDL is not a full migration framework.
- Requires careful compatibility when adding/changing fields.

Alternatives considered:

- Raw SQL only (full control, slower iteration).
- SQLAlchemy + migration tooling (richer ecosystem, more setup overhead).

## Decision 3: Hot-Path Redis Cache for URL Resolve

Context:

- `GET /<short_code>` is the highest-frequency endpoint under load tests.

Choice:

- Cache as Redis string key-value: `url:<alias> -> original_url`.
- Resolve flow:
  - Cache HIT: immediate redirect, no DB read.
  - Cache MISS: DB lookup, click increment/event log, write-through cache, redirect.
- Add `X-Cache` and `X-Cache-Status` headers for diagnostics and k6 checks.

Why this choice:

- Reduces database pressure on repeated resolves.
- Improves p95 latency and throughput predictability.
- Keeps hot-path serialization minimal (plain string, no JSON decode).

Tradeoffs:

- Requires invalidation discipline for revoke/delete and lifecycle changes.
- Adds operational dependency and failure modes around Redis availability.

Alternatives considered:

- No cache (simpler but slower and DB-heavier).
- In-process cache (fast local reads, but inconsistent across replicas/workers).

## Decision 4: Selective DB Connection Strategy Per Request

Context:

- Many endpoints need DB access, but some paths (`/health`, `/`) do not.
- Resolve endpoint can avoid DB on Redis hit.

Choice:

- Open DB connection in `before_request` only for endpoints that require it.
- Skip automatic connect for `url.resolve`; resolve opens DB only on cache miss.
- Ensure cleanup via `teardown_appcontext`.

Why this choice:

- Avoids unnecessary connection churn on non-DB or cache-hit requests.
- Preserves correctness on miss path while improving hot-path efficiency.

Tradeoffs:

- Endpoint-name coupling in DB hook logic must stay aligned with route naming.
- Slightly more complex lifecycle than always-open-per-request.

Alternatives considered:

- Always connect for every request (simpler, more overhead at scale).

## Decision 5: Strict Boundary Validation and Error Contract

Context:

- Hidden tests and real clients submit malformed JSON, missing fields, wrong content types, and mixed alias keys.

Choice:

- Validate request `Content-Type`, JSON parse success, object shape, field types, and URL validity at route boundaries.
- Support compatibility aliases where needed (for example `url` and `original_url`; `event_type` and `title`).
- Return explicit JSON error payloads with correct status codes (`400`, `404`, `409`, `410`, `415`).

Why this choice:

- Produces deterministic behavior for graders and clients.
- Prevents bad data entering persistence.
- Reduces runtime ambiguity and downstream debugging effort.

Tradeoffs:

- More verbose route code.
- Consistency burden across multiple route modules.

Alternatives considered:

- Lenient parsing and coercion (less code, more ambiguous behavior).

## Decision 6: Structured Logging + Prometheus Metrics as First-Class Ops Signals

Context:

- The system needs visibility without SSH-heavy debugging and should support external log streaming.

Choice:

- Emit structured JSON logs with stable fields (`timestamp`, `level`, `component`, `method`, `path`, `status_code`, `latency_ms`, etc.).
- Record request count, latency histogram, and error counters through Prometheus client.
- Mount `/metrics` through WSGI middleware (with multiprocess collector support).

Why this choice:

- Enables machine-readable logs for Kafka pipelines and dashboards.
- Provides objective latency/error telemetry for load-test tuning.
- Works in both single-process and Gunicorn multiprocess modes.

Tradeoffs:

- Needs careful metric cardinality discipline (path labels can grow).
- Requires runtime configuration (`PROMETHEUS_MULTIPROC_DIR`) in multiprocess deployments.

Alternatives considered:

- Plain text logs only (human-friendly but weaker for automation).
- No metrics endpoint (fewer dependencies, reduced observability).

## Decision 7: Nginx Front Door with Gunicorn Worker Pool

Context:

- Need one public entrypoint, TLS handling, reverse-proxy headers, and load distribution.

Choice:

- Run Nginx as L7 reverse proxy in front of Gunicorn.
- Use `least_conn` upstream policy and Unix socket handoff.
- Preserve forwarding headers and cache headers.

Why this choice:

- Separates transport concerns (TLS, proxy behavior) from app code.
- Supports stable ingress across local and production environments.
- Fits high-concurrency load patterns better than Flask dev server.

Tradeoffs:

- More moving parts to configure (cert files, ports, headers, timeouts).
- Misconfigured TLS paths can cause startup loops.

Alternatives considered:

- Expose Gunicorn directly (simpler, less edge control).
- Managed cloud LB only (clean in production, less parity with local stack).

## Decision 8: CI/CD Gate on Tested Branches

Context:

- Deploys should not run from failing CI runs.
- Team needs controlled branch-based release behavior.

Choice:

- Trigger CD from successful CI workflow runs only.
- Restrict deploy branches to `staging` and `main`.
- Re-run tests in deploy job before build/deploy.

Why this choice:

- Reduces accidental bad deployments.
- Keeps release flow explicit and auditable.

Tradeoffs:

- Slightly longer pipeline runtime.
- Duplicate test execution between CI and CD jobs.

Alternatives considered:

- Deploy on every push (faster, riskier).
- Manual deploy-only flow (safer, slower feedback).

## Decision 9: Backward-Compatible API Shape During Iteration

Context:

- Multiple test suites and clients can expect different field names during iterative development.

Choice:

- Preserve compatibility aliases in request and response contracts while using a canonical internal model.
- Examples:
  - URL create accepts both `url` and `original_url`.
  - Event payloads support `event_type/details/timestamp` and compatibility aliases.

Why this choice:

- Enables incremental hardening without breaking existing callers.
- Helps satisfy hidden tests that probe alternate field conventions.

Tradeoffs:

- Increases route-level contract complexity.
- Requires clear docs to avoid long-term API drift.

Alternatives considered:

- Immediate strict breaking contract (cleaner, but riskier for grading/client compatibility).
