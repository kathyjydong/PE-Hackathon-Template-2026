import app as app_module
from peewee import SqliteDatabase
from app.models import ALL_MODELS, Url, db
from app.routes import url_shortener


class DummyUrlEntry:
    def __init__(self, original_url, short_code):
        self.original_url = original_url
        self.short_code = short_code
        self.revoked = False


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
    # Keep app factory isolated from a real Postgres instance.
    monkeypatch.setattr(app_module, "init_db", lambda _app: None)
    test_app = app_module.create_app()
    test_app.config["TESTING"] = True
    return test_app.test_client()


def make_client_with_sqlite(monkeypatch, db_path):
    sqlite_db = SqliteDatabase(db_path)

    def _init_sqlite(app):
        db.initialize(sqlite_db)

        with app.app_context():
            sqlite_db.create_tables(ALL_MODELS, safe=True)

        @app.before_request
        def _db_connect():
            db.connect(reuse_if_open=True)

        @app.teardown_appcontext
        def _db_close(_exc):
            if not db.is_closed():
                db.close()

    monkeypatch.setattr(app_module, "init_db", _init_sqlite)
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
        def create(**_kwargs):
            return None

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
        def create(**_kwargs):
            return None

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


def test_shorten_persists_to_db(monkeypatch, tmp_path):
    client = make_client_with_sqlite(monkeypatch, str(tmp_path / "integration.db"))

    response = client.post("/shorten", json={"url": "https://example.com/integration"})

    assert response.status_code == 201
    short_url = response.get_json()["short_url"]
    short_code = short_url.rsplit("/", 1)[-1]

    created = Url.get(Url.short_code == short_code)
    assert created.original_url == "https://example.com/integration"


def test_shorten_with_garbage_json_returns_clean_error(monkeypatch):
    client = make_client(monkeypatch)

    response = client.post(
        "/shorten",
        data="{not-valid-json",
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "URL is missing"}


def test_shorten_invalid_custom_alias_returns_clean_error(monkeypatch):
    client = make_client(monkeypatch)

    response = client.post(
        "/shorten",
        json={"url": "https://example.com", "custom_alias": "bad alias!"},
    )

    assert response.status_code == 400
    assert "Custom alias" in response.get_json()["error"]


def test_method_not_allowed_returns_json_error(monkeypatch):
    client = make_client(monkeypatch)

    response = client.post("/health")

    assert response.status_code == 405
    assert response.is_json
    assert "not allowed" in response.get_json()["error"].lower()
