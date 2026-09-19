from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from gex.application.market_intelligence import (
    LevelBuildConfig,
    build_market_levels_from_gex_outputs,
)
from gex.domain.market.intelligence import LevelType, SessionType


def _chain() -> pd.DataFrame:
    return pd.DataFrame({
        "strike": [7580.0, 7590.0, 7600.0, 7610.0],
        "type": ["P", "C", "C", "C"],
        "gex": [-2_000_000.0, 5_000_000.0, 1_000_000.0, 3_000_000.0],
        "open_interest": [42_100.0, 35_000.0, 38_000.0, 19_100.0],
        "volume": [12_400.0, 8_200.0, 15_420.0, 4_200.0],
    })


def test_build_market_levels_from_existing_gex_outputs_preserves_origins():
    levels = build_market_levels_from_gex_outputs(
        chain=_chain(),
        timestamp=datetime(2026, 9, 18, 9, 45),
        keys={"call_wall": 7600.0, "put_support": 7580.0},
        zero_gamma=7590.0,
        session=SessionType.REGULAR,
    )

    by_type = {level.level_type: level for level in levels}
    assert by_type[LevelType.CALL_WALL].price == 7600.0
    assert by_type[LevelType.CALL_WALL].metadata["side"] == "C"
    assert by_type[LevelType.PUT_WALL].price == 7580.0
    assert by_type[LevelType.PUT_WALL].metadata["side"] == "P"
    assert by_type[LevelType.GAMMA_FLIP].price == 7590.0
    assert all(0 <= level.strength <= 100 for level in levels)


def test_market_level_builder_adds_volume_oi_and_gex_nodes_without_probabilities():
    levels = build_market_levels_from_gex_outputs(
        chain=_chain(),
        timestamp=datetime(2026, 9, 18, 9, 45),
        keys={},
        zero_gamma=None,
        config=LevelBuildConfig(max_gex_levels=2),
    )

    types = [level.level_type for level in levels]
    assert LevelType.HIGH_GAMMA in types
    assert LevelType.LOW_GAMMA in types
    assert types.count(LevelType.GEX_WALL) == 2
    assert LevelType.VOLUME_NODE in types
    assert LevelType.OI_NODE in types
    assert all("probability" not in level.__dataclass_fields__ for level in levels)


def test_market_level_builder_preserves_available_second_order_exposures():
    chain = _chain().assign(
        expiry="2026-09-18",
        dex=[-100.0, -200.0, -300.0, -400.0],
        vex=[10.0, 20.0, 30.0, 40.0],
        cex=[-1.0, -2.0, -3.0, -4.0],
    )

    levels = build_market_levels_from_gex_outputs(
        chain=chain, timestamp=datetime(2026, 9, 18, 9, 45),
        keys={"call_wall": 7600.0},
    )

    call_wall = next(level for level in levels if level.level_type is LevelType.CALL_WALL)
    assert call_wall.delta == -300.0
    assert call_wall.vanna == 30.0
    assert call_wall.charm == -3.0
    assert call_wall.expiration.isoformat().startswith("2026-09-18")
    assert call_wall.metadata["expiration_count"] == 1


def test_market_level_builder_rejects_invalid_config():
    with pytest.raises(ValueError, match="max_gex_levels"):
        LevelBuildConfig(max_gex_levels=-1)
    with pytest.raises(ValueError, match="min_wall_strength"):
        LevelBuildConfig(min_wall_strength=101)


def test_market_level_builder_applies_configured_wall_strength_threshold():
    levels = build_market_levels_from_gex_outputs(
        chain=_chain(), timestamp=datetime(2026, 9, 18, 9, 45),
        keys={"call_wall": 7600.0, "put_support": 7580.0},
        config=LevelBuildConfig(min_wall_strength=60),
    )

    assert LevelType.CALL_WALL not in {level.level_type for level in levels}
    assert LevelType.PUT_WALL in {level.level_type for level in levels}
