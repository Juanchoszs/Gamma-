from __future__ import annotations

import requests
import pytest

from gex.application.tastytrade.auth import (
    TastytradeAuthClient,
    TastytradeAuthError,
)


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.payload = None
        self.headers = None

    def post(self, url, *, json, headers, timeout):
        self.payload = json
        self.headers = headers
        return self.response


def response(status: int, body: dict) -> requests.Response:
    result = requests.Response()
    result.status_code = status
    result._content = __import__("json").dumps(body).encode()
    result.headers["Content-Type"] = "application/json"
    return result


def test_refresh_uses_official_json_contract():
    session = FakeSession(response(200, {"access_token": "access", "expires_in": 900}))
    token = TastytradeAuthClient(session=session).refresh("refresh", "secret")

    assert token.access_token == "access"
    assert token.expires_in == 900
    assert session.payload == {
        "grant_type": "refresh_token",
        "refresh_token": "refresh",
        "client_secret": "secret",
    }
    assert session.headers["Content-Type"] == "application/json"


def test_refresh_surfaces_sanitized_provider_error():
    session = FakeSession(response(400, {
        "error_code": "invalid_grant",
        "error_description": "Invalid JWT",
    }))

    with pytest.raises(TastytradeAuthError, match="invalid_grant"):
        TastytradeAuthClient(session=session).refresh("refresh", "secret")
