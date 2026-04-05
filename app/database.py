import os
import logging

from flask import request
from peewee import PostgresqlDatabase

from app.models import ALL_MODELS, db


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
        if not db.is_closed():
            db.close()



logger = logging.getLogger(__name__)

def init_db(app):
    database = PostgresqlDatabase(
        os.environ.get("DATABASE_NAME", "hackathon_db"),
        host=os.environ.get("DATABASE_HOST", "localhost"),
        port=int(os.environ.get("DATABASE_PORT", 5432)),
        user=os.environ.get("DATABASE_USER", "postgres"),
        password=os.environ.get("DATABASE_PASSWORD", "postgres"),
    )

    db.initialize(database)

    with app.app_context():
        try:
            database.create_tables(ALL_MODELS, safe=True)
            database.execute_sql(
                "ALTER TABLE url ADD COLUMN IF NOT EXISTS revoked BOOLEAN NOT NULL DEFAULT FALSE;"
            )
            database.execute_sql(
                "ALTER TABLE url ADD COLUMN IF NOT EXISTS title VARCHAR(255);"
            )
            database.execute_sql(
                "ALTER TABLE url ADD COLUMN IF NOT EXISTS clicks INTEGER NOT NULL DEFAULT 0;"
            )
            logger.info("Database initialized", extra={"component": "database"})
        except Exception:
            # If a 'duplicate key' error occurs, it means another clone already finished the setup
            logger.warning(
                "Database initialization skipped",
                extra={"component": "database"},
                exc_info=True,
            )

    register_db_hooks(app)
