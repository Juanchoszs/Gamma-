"""Cliente OAuth2 de backend para Tastytrade.

Este módulo no conoce Dash, Flask ni el almacenamiento. Centraliza el
intercambio de tokens para que el streaming y las llamadas REST usen el mismo
contrato y para que los secretos nunca lleguen a la capa de presentación.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

TOKEN_URL = "https://api.tastyworks.com/oauth/token"
USER_AGENT = "gex-dashboard/1.0"


class TastytradeAuthError(requests.HTTPError):
    """Error OAuth con el código seguro devuelto por Tastytrade."""

    def __init__(self, status_code: int, error_code: str | None,
                 description: str | None, response: requests.Response):
        detail = error_code or description or "unknown error"
        super().__init__(
            f"Tastytrade OAuth rejected request ({status_code}): {detail}",
            response=response,
        )
        self.status_code = status_code
        self.error_code = error_code
        self.description = description


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    refresh_token: str | None = None
    expires_in: int | None = None


class TastytradeAuthClient:
    """Cliente pequeño y testeable para los dos grants soportados."""

    def __init__(self, token_url: str = TOKEN_URL,
                 session: requests.Session | None = None):
        self.token_url = token_url
        self.session = session or requests.Session()

    def refresh(self, refresh_token: str, client_secret: str) -> TokenSet:
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_secret": client_secret,
        }
        return self._post(payload)

    def exchange_code(self, code: str, client_id: str, client_secret: str,
                      redirect_uri: str) -> TokenSet:
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        }
        return self._post(payload)

    def _post(self, payload: dict[str, str]) -> TokenSet:
        response = self.session.post(
            self.token_url,
            json=payload,
            headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
            timeout=30,
        )
        if not response.ok:
            try:
                body: dict[str, Any] = response.json()
            except ValueError:
                body = {}
            raise TastytradeAuthError(
                response.status_code,
                body.get("error_code") or body.get("error"),
                body.get("error_description"),
                response,
            )
        body = response.json()
        access_token = body.get("access_token")
        if not access_token:
            raise TastytradeAuthError(
                response.status_code, "missing_access_token",
                "Tastytrade response did not include access_token", response,
            )
        expires_in = body.get("expires_in")
        return TokenSet(
            access_token=access_token,
            refresh_token=body.get("refresh_token"),
            expires_in=int(expires_in) if expires_in is not None else None,
        )
