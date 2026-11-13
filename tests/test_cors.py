"""CORS for a separately hosted frontend: off by default, exact origins only."""

import importlib

from fastapi.testclient import TestClient

import app.main


def _client(monkeypatch, origins):
    if origins is None:
        monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)
    else:
        monkeypatch.setenv("CORS_ALLOW_ORIGINS", origins)
    return TestClient(importlib.reload(app.main).app)


def _preflight(client, origin):
    return client.options(
        "/api/agent/run",
        headers={"Origin": origin, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"},
    )


def test_cors_off_by_default(monkeypatch):
    client = _client(monkeypatch, None)
    r = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers


def test_cors_allows_only_listed_origins(monkeypatch):
    client = _client(monkeypatch, "https://agent.example.app, https://preview.example.app/")

    ok = _preflight(client, "https://agent.example.app")
    assert ok.status_code == 200
    assert ok.headers["access-control-allow-origin"] == "https://agent.example.app"

    trailing_slash_normalised = _preflight(client, "https://preview.example.app")
    assert trailing_slash_normalised.headers["access-control-allow-origin"] == "https://preview.example.app"

    denied = _preflight(client, "https://evil.example")
    assert "access-control-allow-origin" not in denied.headers
    assert "access-control-allow-credentials" not in ok.headers


def teardown_module():
    # Leave app.main as the other test modules imported it (no CORS).
    import os

    os.environ.pop("CORS_ALLOW_ORIGINS", None)
    importlib.reload(app.main)
