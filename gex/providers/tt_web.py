"""Handle tastytrade OAuth authorization from the dashboard."""
from __future__ import annotations

import logging
import secrets
import threading

from flask import Flask, redirect, request

from . import tt_auth
from .rtquote import credentials_present

log = logging.getLogger(__name__)

# Pending one-time OAuth states, bounded to abandoned attempts.
_PENDING: dict[str, float] = {}
_PENDING_LOCK = threading.Lock()
_MAX_PENDING = 8


def _page(titre: str, message: str, ok: bool) -> str:
    """Render a minimal dashboard-styled callback page."""
    couleur = "#22c55e" if ok else "#ef4444"
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>{titre}</title></head>
<body style="background:#0d0d0d;color:#e5e5e5;font-family:system-ui,sans-serif;
             display:flex;align-items:center;justify-content:center;
             height:100vh;margin:0">
  <div style="max-width:34rem;padding:2rem;border-left:3px solid {couleur};
              background:#151515">
    <h1 style="margin:0 0 .6rem;font-size:1.1rem;color:{couleur}">{titre}</h1>
    <p style="margin:0 0 1.2rem;line-height:1.5">{message}</p>
    <a href="/" style="color:#22d3ee">Back to dashboard</a>
  </div>
</body></html>"""


def _remember_state() -> str:
    import time

    state = secrets.token_urlsafe(24)
    with _PENDING_LOCK:
        if len(_PENDING) >= _MAX_PENDING:
            # Remove the oldest attempt so abandoned flows do not block new ones.
            oldest = min(_PENDING, key=_PENDING.get)
            _PENDING.pop(oldest, None)
        _PENDING[state] = time.time()
    return state


def _consume_state(state: str | None) -> bool:
    """Consume a pending state and reject reuse."""
    if not state:
        return False
    with _PENDING_LOCK:
        return _PENDING.pop(state, None) is not None


def connection_status() -> tuple[str, str]:
    """Return the broker connection state and display message."""
    from .rtquote import _env

    cid = _env("TASTYTRADE_CLIENT_ID")
    secret = _env("TASTYTRADE_CLIENT_SECRET")
    refresh = _env("TT_REFRESH")
    if not cid or not secret:
        return "absent", ("Application credentials missing "
                          "(TASTYTRADE_CLIENT_ID / _SECRET).")
    if not refresh:
        return "deconnecte", "Application configured — authorization pending."
    return "connecte", "tastytrade account connected (read-only)."


def register_oauth(app) -> None:
    """`app`: Dash instance (uses `.server`) or Flask directly —
    same pattern as `api.register_api`, so tests don't need to mount the full dashboard."""
    server: Flask = app.server if hasattr(app, "server") else app

    @server.route("/oauth/start")
    def _oauth_start():
        from .rtquote import _env

        cid = _env("TASTYTRADE_CLIENT_ID")
        if not cid:
            return _page("Incomplete configuration",
                         "TASTYTRADE_CLIENT_ID not found. Create an "
                         "OAuth application at tastytrade "
                         "(Manage \u2192 My Profile \u2192 API), then set "
                         "TASTYTRADE_CLIENT_ID and TASTYTRADE_CLIENT_SECRET.",
                         ok=False), 400
        return redirect(tt_auth.authorize_url(cid, state=_remember_state()))

    @server.route("/oauth/callback")
    def _oauth_callback():
        error = request.args.get("error")
        if error:
            # An explicit authorization denial is not a service failure.
            return _page("Refus / Authorization denied",
                         f"tastytrade returned: {error}. "
                         "Nothing was saved. (refus utilisateur)", ok=False), 400

        if not _consume_state(request.args.get("state")):
            log.warning("OAuth: invalid or expired state, exchange rejected")
            return _page("Unrecognized request",
                         "This authorization does not match any request "
                         "from this dashboard. For security, nothing was "
                         "saved — retry from the Connect button.",
                         ok=False), 400

        code = request.args.get("code")
        if not code:
            return _page("Code missing",
                         "tastytrade did not return an authorization code.",
                         ok=False), 400

        try:
            cid, secret = tt_auth.credentials()
            data = tt_auth.exchange_code(cid, secret, code)
        except SystemExit as exc:      # tt_auth signals failures this way
            log.warning("OAuth: exchange rejected (%s)", exc)
            return _page("Exchange rejected", str(exc), ok=False), 400
        except Exception:              # noqa: BLE001 — network, malformed JSON…
            log.exception("OAuth: code exchange failed")
            return _page("Exchange failed",
                         "Unable to reach tastytrade. "
                         "Check your connection and try again.", ok=False), 502

        refresh = data.get("refresh_token")
        if not refresh:
            return _page("Unexpected response",
                         "No refresh_token in the tastytrade response.",
                         ok=False), 502

        note = tt_auth.store_refresh(refresh)
        log.info("OAuth tastytrade: connection successful. %s", note)
        _demarrer_les_flux()
        return _page("Connected to tastytrade",
                     f"{note} Real-time streams starting — data will "
                     "appear within a minute.", ok=True)


def _demarrer_les_flux() -> None:
    """Start data streams that were waiting for broker credentials."""
    try:
        if credentials_present():
            from .flowtape import TAPE
            from .rtquote import QUOTES
            from .tickcapture import CAPTURE

            QUOTES.start()
            TAPE.start()
            CAPTURE.start()
    except Exception:  # noqa: BLE001 — a stream failing to start must not block
        log.exception("Starting streams after connection")