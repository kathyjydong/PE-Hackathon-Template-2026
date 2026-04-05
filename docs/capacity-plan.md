# Capacity Plan

## How many users can we handle?

There is no hardcoded maximum number of users in application logic. Capacity is constrained by infrastructure and runtime configuration rather than a fixed user count in code.

With current defaults:

- App-side in-flight request concurrency is approximately 384 per app instance (4 Gunicorn workers x 96 threads).
- Effective total concurrency is also bounded by `GUNICORN_MAX_CONCURRENCY` (default 512).
- Primary database pool capacity is approximately 16 active connections per app instance (4 workers x `DATABASE_POOL_MAX` of 4).

This means we can store a very large number of user records, but the number of concurrent active users depends on workload shape.

## Where is the limit?

The practical bottlenecks are:

1. PostgreSQL query and connection throughput (usually first for write-heavy traffic).
2. Gunicorn worker/thread concurrency on the app host.
3. Host CPU and memory under sustained load.
4. Redis and cache-hit ratio (read-heavy cached traffic scales better than DB-heavy paths).

So the limit is operational, not a fixed app-side cap. The right way to define and validate it is by load testing against p95 latency and error-rate SLOs.
