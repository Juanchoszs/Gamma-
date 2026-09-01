"""Backward compatibility: gex.i18n -> gex.ui.i18n"""
from __future__ import annotations

from .ui.i18n import (
    LANGS,
    TR,
    t,
    regime_text,
    wall_labels,
)

__all__ = ["LANGS", "TR", "t", "regime_text", "wall_labels"]