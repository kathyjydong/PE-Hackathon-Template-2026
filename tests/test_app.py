import app as app_module
from peewee import SqliteDatabase
from app.database import register_db_hooks
from app.models import ALL_MODELS, Url, db
from app.routes import url_shortener


class DummyUrlEntry:
    def __init__(self, original_url, short_code):
        self.original_url = original_url
        self.short_code = short_code
        self.revoked = False
        self.id = 1
        self.created_at = None


class DummyExpression:
    """Mock Peewee expression that supports chaining with & operators."""
    def __and__(self, other):
        return self
    
    def __rand__(self, other):
        return self


class DummyField:
    def __eq__(self, other):
        return DummyExpression()
    
    def __and__(self, other):
        return DummyExpression()


def make_client(monkeypatch):
    """SQLite in memory + same DB hooks as production (resolve skips eager connect)."""

    def _init_sqlite_memory(app):
        sqlite_db = SqliteDatabase(":memory:")
        db.initialize(sqlite_db)
        with app.app_context():
            sqlite_db.create_tables(ALL_MODELS, safe=True)
        register_db_hooks(app)

    monkeypatch.setattr(app_module, "init_db", _init_sqlite_memory)
    monkeypatch.setattr(app_module, "init_redis", lambda _app: None)
    test_app = app_module.create_app()
    test_app.config["TESTING"] = True
    return test_app.test_client()


def make_client_with_sqlite(monkeypatch, db_path):
    sqlite_db = SqliteDatabase(db_path)

    def _init_sqlite(app):
        db.initialize(sqlite_db)

        with app.app_context():
            sqlite_db.create_tables(ALL_MODELS, safe=True)

        register_db_hooks(app)

    monkeypatch.setattr(app_module, "init_db", _init_sqlite)
    monkeypatch.setattr(app_module, "init_redis", lambda _app: None)
    test_app = app_module.create_app()
    test_app.config["TESTING"] = True
    return test_app.test_client()


def test_health_returns_ok(monkeypatch):
    client = make_client(monkeypatch)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_shorten_returns_generated_code(monkeypatch):
    client = make_client(monkeypatch)

    class DummyUrl:
        original_url = DummyField()
        short_code = DummyField()
        revoked = DummyField()

        @staticmethod
        def get_or_none(_query):
            return None

        @staticmethod
        def generate_code():
            return "abc123"

        @staticmethod
        def create(**kwargs):
            class Row:
                id = 1
                original_url = kwargs.get("original_url", "")
                short_code = kwargs.get("short_code", "abc123")
                revoked = False
                created_at = None

            return Row()

    monkeypatch.setattr(url_shortener, "Url", DummyUrl)

    response = client.post("/shorten", json={"url": "https://example.com"})

    assert response.status_code == 201
    assert response.get_json()["short_url"].endswith("/abc123")


def test_shorten_uses_custom_alias(monkeypatch):
    client = make_client(monkeypatch)

    class DummyUrl:
        original_url = DummyField()
        short_code = DummyField()
        revoked = DummyField()

        @staticmethod
        def get_or_none(_query):
            return None

        @staticmethod
        def create(**kwargs):
            class Row:
                id = 1
                original_url = kwargs.get("original_url", "")
                short_code = kwargs.get("short_code", "my-link")
                revoked = False
                created_at = None

            return Row()

    monkeypatch.setattr(url_shortener, "Url", DummyUrl)

    response = client.post(
        "/shorten",
        json={"url": "https://example.com", "custom_alias": "my-link"},
    )

    assert response.status_code == 201
    assert response.get_json()["short_url"].endswith("/my-link")


def test_resolve_redirects(monkeypatch):
    client = make_client(monkeypatch)

    class DummyUrl:
        short_code = DummyField()
        revoked = DummyField()

        @staticmethod
        def get_or_none(_query):
            return DummyUrlEntry("https://www.google.com", "my-google")

    monkeypatch.setattr(url_shortener, "Url", DummyUrl)

    response = client.get("/my-google")

    assert response.status_code == 302
    assert response.headers["Location"] == "https://www.google.com"
    assert response.headers.get("X-Cache") == "MISS"


def test_shorten_persists_to_db(monkeypatch, tmp_path):
    client = make_client_with_sqlite(monkeypatch, str(tmp_path / "integration.db"))

    response = client.post("/shorten", json={"url": "https://example.com/integration"})

    assert response.status_code == 201
    short_url = response.get_json()["short_url"]
    short_code = short_url.rsplit("/", 1)[-1]

    created = Url.get(Url.short_code == short_code)
    assert created.original_url == "https://example.com/integration"
