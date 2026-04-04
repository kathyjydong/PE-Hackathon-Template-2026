import os
from peewee import PostgresqlDatabase
from app.models import db, ALL_MODELS 

def init_db(app):
    # This reads your .env file to talk to the Docker container
    database = PostgresqlDatabase(
        os.environ.get("DATABASE_NAME", "hackathon_db"),
        host=os.environ.get("DATABASE_HOST", "localhost"),
        port=int(os.environ.get("DATABASE_PORT", 5432)),
        user=os.environ.get("DATABASE_USER", "postgres"),
        password=os.environ.get("DATABASE_PASSWORD", "postgres"),
    )
    
    # Plug the real database into the Proxy
    db.initialize(database)

    with app.app_context():
        # SAFETY UPDATE: Wrapped in try/except to prevent clones from crashing each other
        try:
            database.create_tables(ALL_MODELS, safe=True)
            # Peewee create_tables(safe=True) does not add new columns to existing tables.
            database.execute_sql(
                "ALTER TABLE url ADD COLUMN IF NOT EXISTS revoked BOOLEAN NOT NULL DEFAULT FALSE;"
            )
            database.execute_sql(
                "ALTER TABLE url ADD COLUMN IF NOT EXISTS title VARCHAR(255);"
            )
            print("Successfully created database tables in Docker!")
        except Exception as e:
            # If a 'duplicate key' error occurs, it means another clone already finished the setup
            print(f"Database already initialized by another instance, skipping: {e}")

    @app.before_request
    def _db_connect():
        db.connect(reuse_if_open=True)

    @app.teardown_appcontext
    def _db_close(exc):
        if not db.is_closed():
            db.close()