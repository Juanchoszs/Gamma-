"""Provider modules kept for compatibility with the historical import surface.

This project currently exposes provider-specific implementations directly from the
``gex.providers`` package; keep the package importable and re-export the concrete
modules used throughout the codebase.
"""
from __future__ import annotations

from . import flowtape, futopt, idxopt, ingest, rtquote, tickcapture, tt_auth, tt_web

__all__ = [
    "flowtape",
    "futopt",
    "idxopt",
    "ingest",
    "rtquote",
    "tickcapture",
    "tt_auth",
    "tt_web",
]
