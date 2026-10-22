import pytest

from app import create_app
from app.config import ProductionConfig, get_config, normalise_database_url


def test_health(client):
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.get_json()["data"] == {
        "status": "ok",
        "service": "tpa-api",
        "version": "v1",
        "environment": "testing",
    }


def test_security_headers(client):
    res = client.get("/api/v1/health")
    assert res.headers["X-Content-Type-Options"] == "nosniff"


def test_cors_allows_approved_origin_only(client):
    ok = client.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})
    assert ok.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"
    blocked = client.get("/api/v1/health", headers={"Origin": "https://evil.example"})
    assert "Access-Control-Allow-Origin" not in blocked.headers


def test_unknown_api_route_returns_json_404(client):
    res = client.get("/api/v1/does-not-exist")
    assert res.status_code == 404
    assert res.get_json()["error"]["code"] == "not_found"


def test_method_not_allowed(client):
    res = client.post("/api/v1/articles")
    assert res.status_code == 405
    assert res.get_json()["error"]["code"] == "method_not_allowed"


def test_unexpected_errors_hide_internals(app):
    @app.get("/api/v1/_boom")
    def boom():
        raise RuntimeError("secret database password in traceback")

    res = app.test_client().get("/api/v1/_boom")
    assert res.status_code == 500
    body = res.get_json()
    assert body == {"error": {"code": "internal_error", "message": "An unexpected error occurred."}}
    assert b"secret" not in res.data and b"Traceback" not in res.data


def test_resource_errors_hide_internals(app, monkeypatch):
    def broken():
        raise KeyError("internal detail")

    monkeypatch.setattr("app.api.products.list_products", broken)
    res = app.test_client().get("/api/v1/products")
    assert res.status_code == 500
    assert res.get_json()["error"]["code"] == "internal_error"
    assert b"internal detail" not in res.data


def test_database_url_normalisation():
    assert normalise_database_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalise_database_url("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalise_database_url("sqlite:///x.db") == "sqlite:///x.db"
    assert normalise_database_url(None) is None


def test_unknown_config_rejected():
    with pytest.raises(ValueError):
        get_config("staging-typo")


def test_production_requires_secrets(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setattr(ProductionConfig, "SQLALCHEMY_DATABASE_URI", None)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app("production")
