import os
import logging
from urllib.parse import urlparse

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
        if ep in ("health", "home"):
            return
        if ep == "url.resolve":
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
        replica = PooledPostgresqlDatabase(
            p.path.lstrip("/"),
            host=p.hostname,
            port=p.port or 5432,
            user=p.username,
            password=p.password,
            max_connections=10,
            stale_timeout=300,
        )
        logger.info("Read replica configured at %s:%s", p.hostname, p.port or 5432,
                    extra={"component": "database"})
        return replica
    except Exception as e:
        logger.warning("Read replica init failed, falling back to primary: %s", e,
                       extra={"component": "database"})
        return primary


def init_db(app):
    database = PooledPostgresqlDatabase(
        os.environ.get("DATABASE_NAME", "hackathon_db"),
        host=os.environ.get("DATABASE_HOST", "localhost"),
        port=int(os.environ.get("DATABASE_PORT", 5432)),
        user=os.environ.get("DATABASE_USER", "postgres"),
        password=os.environ.get("DATABASE_PASSWORD", "postgres"),
        max_connections=10,      # 🔥 IMPORTANT (leave headroom from 22)
        stale_timeout=300,       # recycle connections after 5 mins
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
