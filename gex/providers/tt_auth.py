"""Perform the one-time tastytrade OAuth2 authorization flow."""
from __future__ import annotations

import os
import sys
import urllib.parse

import requests

AUTH_URL = "https://my.tastytrade.com/auth.html"
TOKEN_URL = "https://api.tastyworks.com/oauth/token"
# Use HTTP because the local dashboard is served without TLS.
REDIRECT_URI = "http://localhost:8050/oauth/callback"
# Read-only scope: this project does not execute orders.
SCOPE = "read"


def _env(name: str) -> str | None:
    """Read an environment variable, falling back to the Windows user registry."""
    val = os.environ.get(name)
    if not val and sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                val = winreg.QueryValueEx(k, name)[0]
        except OSError:
            pass
    return val


def credentials() -> tuple[str, str]:
    cid = _env("TASTYTRADE_CLIENT_ID")
    secret = _env("TASTYTRADE_CLIENT_SECRET")
    if not cid or not secret:
        raise SystemExit(
            "TASTYTRADE_CLIENT_ID / TASTYTRADE_CLIENT_SECRET introuvables "
            "(variables d'environnement ou registre HKCU)."
        )
    return cid, secret


def authorize_url(client_id: str, state: str | None = None) -> str:
    """Return the browser authorization URL."""
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
    }
    if state:
        params["state"] = state
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


def store_refresh(token: str) -> str:
    """Store the refresh token in the location used by ``rtquote._env``."""
    os.environ["TT_REFRESH"] = token
    if sys.platform != "win32":
        return ("Jeton actif pour cette session. Pour le rendre permanent, "
                'ajoute TT_REFRESH="…" à ton profil shell.')
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                            winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, "TT_REFRESH", 0, winreg.REG_SZ, token)
        return "Jeton enregistré (variable utilisateur TT_REFRESH)."
    except OSError as exc:
        return (f"Jeton actif pour cette session, mais non enregistré ({exc}). "
                "Il faudra se reconnecter au prochain démarrage.")


def exchange_code(client_id: str, secret: str, code: str) -> dict:
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": secret,
            "redirect_uri": REDIRECT_URI,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise SystemExit(f"Échec de l'échange ({resp.status_code}) : {resp.text[:400]}")
    return resp.json()


def main() -> None:
    cid, secret = credentials()
    print("\n1) Ouvre cette URL dans ton navigateur et approuve l'accès :\n")
    print(authorize_url(cid))
    print(
        "\n2) Tu seras redirigé vers une page d'ERREUR (normal : rien n'écoute"
        f"\n   sur {REDIRECT_URI}). Dans la barre d'adresse, copie la valeur"
        "\n   du paramètre code=... (tout ce qui suit 'code=', avant un '&')\n"
    )
    code = input("3) Colle le code ici : ").strip()
    if not code:
        raise SystemExit("Aucun code fourni.")

    data = exchange_code(cid, secret, code)
    refresh = data.get("refresh_token")
    if not refresh:
        raise SystemExit(f"Pas de refresh_token dans la réponse : {data}")

    print("\n" + "=" * 62)
    print("Refresh token obtenu. Enregistre les DEUX variables ci-dessous")
    print("(noms imposés par le SDK tastytrade), puis relance ta session :\n")
    print(f'  setx TT_REFRESH "{refresh}"')
    print('  setx TT_SECRET "%TASTYTRADE_CLIENT_SECRET%"')
    print("=" * 62)
    print("\nCe token est un secret de longue durée : ne le partage pas et ne")
    print("le committe jamais dans le repo.\n")


if __name__ == "__main__":
    main()
