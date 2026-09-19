"""Prepare GEX overlay levels from existing GEX engine outputs."""
from __future__ import annotations

import numpy as np
import pandas as pd

from gex.application.options_flow.dto import GEXLevel


def build_gex_levels(
    chain: pd.DataFrame | None,
    spot: float | None,
    gamma_flip: float | None,
    keys: dict | None,
) -> list[GEXLevel]:
    """Build render-ready GEX levels without recalculating GEX maths."""
    levels: list[GEXLevel] = []
    chain = chain if chain is not None else pd.DataFrame()
    keys = keys or {}
    if spot is not None:
        for idx, strike in enumerate(_level_values(keys, "call_walls", "call_wall", chain, spot, "C")):
            gex, oi, volume = _level_stats(chain, strike, "C")
            levels.append(GEXLevel(
                name="Call Wall" if idx == 0 else f"Call Wall {idx + 1}",
                price=strike,
                value=gex,
                side="C",
                open_interest=oi,
                volume=volume,
                color_key="call_wall",
                glow_key="call_wall_glow",
            ))
        for idx, strike in enumerate(_level_values(keys, "put_supports", "put_support", chain, spot, "P")):
            gex, oi, volume = _level_stats(chain, strike, "P")
            levels.append(GEXLevel(
                name="Put Wall" if idx == 0 else f"Put Wall {idx + 1}",
                price=strike,
                value=gex,
                side="P",
                open_interest=oi,
                volume=volume,
                color_key="put_wall",
                glow_key="put_wall_glow",
            ))
    if gamma_flip is not None:
        gex, oi, volume = _level_stats(chain, float(gamma_flip), None)
        levels.append(GEXLevel(
            name="Gamma Flip",
            price=float(gamma_flip),
            value=gex,
            style="dash",
            open_interest=oi,
            volume=volume,
            color_key="flip",
            glow_key="flip_glow",
        ))
    return levels


def _level_values(
    keys: dict,
    plural_key: str,
    singular_key: str,
    chain: pd.DataFrame,
    spot: float,
    side: str,
) -> list[float]:
    explicit = keys.get(plural_key)
    if isinstance(explicit, (list, tuple)):
        return [float(value) for value in explicit[:3] if value is not None]
    if keys.get(singular_key) is not None:
        return [float(keys[singular_key])]
    if chain.empty or not {"strike", "type", "gex"}.issubset(chain.columns):
        return []
    grouped = chain.groupby(["type", "strike"])["gex"].sum()
    if side == "C":
        candidates = grouped[
            (grouped.index.get_level_values("type") == "C")
            & (grouped.index.get_level_values("strike") >= spot)
            & (grouped > 0)
        ]
    else:
        candidates = grouped[
            (grouped.index.get_level_values("type") == "P")
            & (grouped.index.get_level_values("strike") <= spot)
            & (grouped < 0)
        ]
    return [float(strike) for strike in candidates.abs().nlargest(3).index.get_level_values("strike")]


def _level_stats(chain: pd.DataFrame, strike: float, side: str | None) -> tuple[float, float, float]:
    if chain.empty or "strike" not in chain.columns:
        return 0.0, 0.0, 0.0
    rows = chain[np.isclose(chain["strike"], float(strike))]
    if side is not None and "type" in rows.columns:
        rows = rows[rows["type"] == side]
    if rows.empty:
        return 0.0, 0.0, 0.0
    return (
        float(rows["gex"].sum()) if "gex" in rows else 0.0,
        float(rows["open_interest"].fillna(0).sum()) if "open_interest" in rows else 0.0,
        float(rows["volume"].fillna(0).sum()) if "volume" in rows else 0.0,
    )
