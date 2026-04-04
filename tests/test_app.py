from datetime import datetime
from pathlib import Path

import app as app_module
from peewee import SqliteDatabase
from app.models import ALL_MODELS, Url, User, db
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
    monkeypatch.setattr(app_module, "init_redis", lambda _app: None)
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

    monkeypatch.setattr(app_module, "init_redis", lambda _app: None)
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
    assert response.get_json() == {"error": "Malformed JSON body"}


def test_shorten_requires_json_content_type(monkeypatch):
    client = make_client(monkeypatch)

    response = client.post("/shorten", data="url=https://example.com")

    assert response.status_code == 415
    assert response.get_json() == {"error": "Content-Type must be application/json"}


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


def test_bulk_load_users_imports_csv(monkeypatch, tmp_path):
    client = make_client_with_sqlite(monkeypatch, str(tmp_path / "bulk_users.db"))
    csv_path = Path(__file__).resolve().parents[1] / "csv_data" / "users.csv"

    with csv_path.open("rb") as users_file:
        response = client.post(
            "/users/bulk",
            data={"file": (users_file, "users.csv")},
            content_type="multipart/form-data",
        )

    assert response.status_code == 201
    assert response.get_json()["count"] == User.select().count()
    assert User.get_by_id(1).username == "vividdelta57"


def test_list_users_and_get_user_by_id(monkeypatch, tmp_path):
    client = make_client_with_sqlite(monkeypatch, str(tmp_path / "list_users.db"))

    first = User.create(
        username="silvertrail15",
        email="silvertrail15@hackstack.io",
        password_hash="",
        created_at=datetime(2025, 9, 19, 22, 25, 5),
    )
    User.create(
        username="urbancanyon36",
        email="urbancanyon36@opswise.net",
        password_hash="",
        created_at=datetime(2024, 4, 9, 2, 51, 3),
    )

    response = client.get("/users?page=1&per_page=1")

    assert response.status_code == 200
    users = response.get_json()
    assert len(users) == 1
    assert users[0]["username"] == "silvertrail15"

    response = client.get(f"/users/{first.id}")

    assert response.status_code == 200
    assert response.get_json()["email"] == "silvertrail15@hackstack.io"


def test_create_user_returns_created_user(monkeypatch, tmp_path):
    client = make_client_with_sqlite(monkeypatch, str(tmp_path / "create_user.db"))

    response = client.post(
        "/users",
        json={"username": "testuser", "email": "testuser@example.com"},
    )

    assert response.status_code == 201
    body = response.get_json()
    assert body["username"] == "testuser"
    assert body["email"] == "testuser@example.com"
    assert "password_hash" not in body


def test_create_user_rejects_invalid_schema(monkeypatch, tmp_path):
    client = make_client_with_sqlite(monkeypatch, str(tmp_path / "invalid_user.db"))

    response = client.post(
        "/users",
        json={"username": 123, "email": "testuser@example.com"},
    )

    assert response.status_code == 400
    assert isinstance(response.get_json()["error"], dict)
    assert response.get_json()["error"]["username"] == "must be a string"


def test_update_user_returns_updated_user(monkeypatch, tmp_path):
    client = make_client_with_sqlite(monkeypatch, str(tmp_path / "update_user.db"))

    user = User.create(
        username="original_user",
        email="original@example.com",
        password_hash="",
        created_at=datetime(2025, 9, 19, 22, 25, 5),
    )

    response = client.put(
        f"/users/{user.id}",
        json={"username": "updated_username"},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["id"] == user.id
    assert body["username"] == "updated_username"
    assert body["email"] == "original@example.com"


def test_delete_user_returns_no_content(monkeypatch, tmp_path):
    client = make_client_with_sqlite(monkeypatch, str(tmp_path / "delete_user.db"))

    user = User.create(
        username="to_delete",
        email="to_delete@example.com",
        password_hash="",
        created_at=datetime(2025, 9, 19, 22, 25, 5),
    )

    response = client.delete(f"/users/{user.id}")

    assert response.status_code == 204
    assert User.get_or_none(User.id == user.id) is None


def test_shorten_same_url_twice_returns_distinct_codes(monkeypatch, tmp_path):
    client = make_client_with_sqlite(monkeypatch, str(tmp_path / "twin_codes.db"))

    first = client.post("/shorten", json={"url": "https://google.com"})
    second = client.post("/shorten", json={"url": "https://google.com"})

    assert first.status_code == 201
    assert second.status_code == 201
    first_code = first.get_json()["short_url"].rsplit("/", 1)[-1]
    second_code = second.get_json()["short_url"].rsplit("/", 1)[-1]
    assert first_code != second_code


def test_resolve_increments_clicks_and_analytics(monkeypatch, tmp_path):
    client = make_client_with_sqlite(monkeypatch, str(tmp_path / "clicks.db"))

    create_response = client.post("/shorten", json={"url": "https://example.com/clicks"})
    short_code = create_response.get_json()["short_url"].rsplit("/", 1)[-1]

    for _ in range(3):
        resolve_response = client.get(f"/{short_code}")
        assert resolve_response.status_code == 302

    stats = client.get(f"/analytics/{short_code}")
    assert stats.status_code == 200
    assert stats.get_json()["clicks"] == 3


def test_revoked_link_does_not_increment_clicks(monkeypatch, tmp_path):
    client = make_client_with_sqlite(monkeypatch, str(tmp_path / "revoked_clicks.db"))

    create_response = client.post("/shorten", json={"url": "https://example.com/revoked"})
    short_code = create_response.get_json()["short_url"].rsplit("/", 1)[-1]

    first_hit = client.get(f"/{short_code}")
    assert first_hit.status_code == 302

    revoke = client.post("/revoke", json={"short_code": short_code})
    assert revoke.status_code == 200

    revoked_hit = client.get(f"/{short_code}")
    assert revoked_hit.status_code == 410

    stats = client.get(f"/analytics/{short_code}")
    assert stats.status_code == 200
    assert stats.get_json()["clicks"] == 1


def test_urls_crud_endpoints(monkeypatch, tmp_path):
    client = make_client_with_sqlite(monkeypatch, str(tmp_path / "urls_crud.db"))

    user = User.create(
        username="url_owner",
        email="url_owner@example.com",
        password_hash="",
        created_at=datetime(2025, 9, 19, 22, 25, 5),
    )

    create_response = client.post(
        "/urls",
        json={
            "original_url": "https://example.com/page",
            "title": "Example page",
            "user_id": user.id,
        },
    )

    assert create_response.status_code == 201
    created = create_response.get_json()
    assert created["original_url"] == "https://example.com/page"
    assert created["title"] == "Example page"
    assert created["user_id"] == user.id
    assert created["is_active"] is True
    assert created["short_code"]

    url_id = created["id"]

    list_response = client.get(f"/urls?user_id={user.id}&is_active=true")
    assert list_response.status_code == 200
    assert len(list_response.get_json()) == 1

    get_response = client.get(f"/urls/{url_id}")
    assert get_response.status_code == 200
    assert get_response.get_json()["id"] == url_id

    update_response = client.put(
        f"/urls/{url_id}",
        json={"title": "Updated title", "is_active": False},
    )
    assert update_response.status_code == 200
    updated = update_response.get_json()
    assert updated["title"] == "Updated title"
    assert updated["is_active"] is False

    delete_response = client.delete(f"/urls/{url_id}")
    assert delete_response.status_code == 204

    missing_response = client.get(f"/urls/{url_id}")
    assert missing_response.status_code == 404
