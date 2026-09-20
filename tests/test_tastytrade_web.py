from __future__ import annotations

from flask import Flask

from gex.adapters.external.tt_web import register_oauth, shared_deployment_enabled


def test_shared_deployment_blocks_browser_credential_mutations(monkeypatch):
    monkeypatch.setenv("GEX_SHARED_DEPLOYMENT", "true")
    app = Flask(__name__)
    register_oauth(app)
    client = app.test_client()

    assert shared_deployment_enabled() is True
    assert client.post("/api/v1/tastytrade/save", json={}).status_code == 403
    assert client.post("/api/v1/tastytrade/disconnect").status_code == 403
    assert client.post("/api/v1/tastytrade/exchange", json={}).status_code == 403
    assert client.get("/oauth/start").status_code == 403
    assert client.get("/oauth/callback").status_code == 403


def test_shared_deployment_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("GEX_SHARED_DEPLOYMENT", raising=False)

    assert shared_deployment_enabled() is False
