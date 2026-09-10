import pytest

from app import create_app
from app.config import Config, _cors_origins, _hmac_key
from app.services import search_bili


class SecurityTestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    CORS_ORIGINS = ["http://localhost:5173"]


def test_cors_allows_configured_origin_only():
    client = create_app(SecurityTestConfig).test_client()

    allowed = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    denied = client.get("/api/health", headers={"Origin": "https://untrusted.example"})

    assert allowed.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert "Access-Control-Allow-Origin" not in denied.headers


def test_cors_wildcard_falls_back_to_local_allowlist(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "*")

    assert _cors_origins() == ["http://localhost:5173", "http://127.0.0.1:5173"]


def test_production_requires_explicit_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("TEST_MISSING_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="TEST_MISSING_SECRET"):
        _hmac_key("TEST_MISSING_SECRET", "development-only-fallback")


def test_bilibili_headers_do_not_send_an_empty_cookie(monkeypatch):
    monkeypatch.setattr(search_bili, "BILI_COOKIE", "")

    assert "Cookie" not in search_bili._build_headers()
    assert search_bili._build_headers("session=value")["Cookie"] == "session=value"
