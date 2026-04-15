import os
import logging
from urllib.parse import parse_qs, urlparse

from flask import request
from playhouse.pool import PooledPostgresqlDatabase

from app.models import ALL_MODELS, db, db_read


def register_db_hooks(app):
    """
    Open Postgres only for routes that need it. Skips /health, /, and url.resolve
    (resolve opens DB only on cache miss — Redis hits never touch Postgres).
    """

    @app.before_request
    def _db_connect():
        ep = request.endpoint
        if ep == "static" or request.path.startswith('/static'):
            return
        if ep in ("health", "home", "url.resolve"):
            return    
        db.connect(reuse_if_open=True)

    @app.teardown_appcontext
    def _db_close(exc):
        for conn in (db, db_read):
            try:
                if not conn.is_closed():
                    conn.close()
            except Exception:
                pass


logger = logging.getLogger(__name__)


def _primary_pool_kwargs() -> dict:
    # Each gunicorn worker = separate process = separate pool. Cap per instance:
    # workers × DATABASE_POOL_MAX ≤ ~18–20 when managed Postgres allows ~22 (leave room for admin).
    mc = int(os.environ.get("DATABASE_POOL_MAX", "4"))
    return {"max_connections": max(1, mc), "stale_timeout": 300}


def _read_pool_kwargs() -> dict:
    mc = os.environ.get("DATABASE_READ_POOL_MAX", "").strip()
    if mc:
        return {"max_connections": int(mc), "stale_timeout": 300}
    return _primary_pool_kwargs()


def _pg_connect_kwargs_from_query(query: str) -> dict:
    """Map ?sslmode=require&... from DATABASE_URL into psycopg2 kwargs."""
    if not query:
        return {}
    out = {}
    for key, vals in parse_qs(query).items():
        if vals:
            out[key] = vals[-1]
    return out


def _primary_params_from_env() -> dict:
    """
    Prefer DATABASE_URL (production / PaaS). Otherwise discrete DATABASE_* vars
    (local dev, docker-compose.yml). Stale DATABASE_HOST=db in .env cannot
    override a correct DATABASE_URL.
    """
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        p = urlparse(url)
        name = (p.path or "").lstrip("/") or "postgres"
        return {
            "database": name,
            "host": p.hostname or "localhost",
            "port": p.port or 5432,
            "user": p.username or "postgres",
            "password": p.password if p.password is not None else "",
            **_primary_pool_kwargs(),
            **_pg_connect_kwargs_from_query(p.query or ""),
        }
    return {
        "database": os.environ.get("DATABASE_NAME", "hackathon_db"),
        "host": os.environ.get("DATABASE_HOST", "localhost"),
        "port": int(os.environ.get("DATABASE_PORT", 5432)),
        "user": os.environ.get("DATABASE_USER", "postgres"),
        "password": os.environ.get("DATABASE_PASSWORD", "postgres"),
        **_primary_pool_kwargs(),
    }


def _make_read_replica(primary: PooledPostgresqlDatabase) -> PooledPostgresqlDatabase:
    """
    Build a pooled connection to the read replica from DATABASE_READ_URL.
    Falls back to the primary pool if not configured or on parse error.
    """
    read_url = os.environ.get("DATABASE_READ_URL", "").strip()
    if not read_url:
        return primary

    try:
        p = urlparse(read_url)
        dbname = (p.path or "").lstrip("/") or "postgres"
        extras = _pg_connect_kwargs_from_query(p.query or "")
        replica = PooledPostgresqlDatabase(
            dbname,
            host=p.hostname or "localhost",
            port=p.port or 5432,
            user=p.username or "postgres",
            password=p.password if p.password is not None else "",
            **_read_pool_kwargs(),
            **extras,
        )
        logger.info(
            "Read replica configured at %s:%s",
            p.hostname or "localhost",
            p.port or 5432,
            extra={"component": "database"},
        )
        return replica
    except Exception as e:
        logger.warning("Read replica init failed, falling back to primary: %s", e,
                       extra={"component": "database"})
        return primary


def init_db(app):
    params = _primary_params_from_env()
    database = PooledPostgresqlDatabase(
        params.pop("database"),
        **params,
    )

    db.initialize(database)
    db_read.initialize(_make_read_replica(database))

    with app.app_context():
        try:
            database.create_tables(ALL_MODELS, safe=True)
            database.execute_sql(
                "ALTER TABLE url ADD COLUMN IF NOT EXISTS revoked BOOLEAN NOT NULL DEFAULT FALSE;"
            )
            logger.info("Database initialized", extra={"component": "database"})
        except Exception as e:
            # If a 'duplicate key' error occurs, it means another clone already finished the setup
            logger.warning(
                "Database initialization skipped",
                extra={"component": "database"},
                exc_info=True,
            )
            print(f"Database already initialized by another instance, skipping: {e}")

    register_db_hooks(app)