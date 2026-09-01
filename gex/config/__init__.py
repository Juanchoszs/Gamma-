"""Configuration for GEX Dashboard."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import providers


def _default_data_dir() -> Path:
    """data/ at the repo root when running from source; otherwise in cwd
    (for `pip install`: code lives in site-packages where we don't write)."""
    # gex/config/__init__.py → parents[2] is the repository root.
    root = Path(__file__).resolve().parents[2]
    if (root / ".git").exists() or (root / "pyproject.toml").exists():
        return root / "data"
    return Path.cwd() / "data"


DATA_DIR = _default_data_dir()

# Annualized risk-free rate, FALLBACK only: live calculations use the daily SOFR via gex/rates (current_rate).
# This constant is only used when the NY Fed API is unreachable or for historical backfill.
RISK_FREE_RATE = 0.045

# Contract multiplier (SPX, NDX, SPY, QQQ: 100).
CONTRACT_MULTIPLIER = 100


@dataclass(frozen=True)
class Underlying:
    key: str            # internal identifier ("SPX")
    cboe_symbol: str    # CBOE endpoint symbol ("_SPX")
    label: str          # display label ("SPX / ES")
    future: str | None = None   # associated CME future, for basis conversion
    # Index family: transposition between families is possible but the ratio drifts over time (see gex/scales.py).
    family: str = "SP"
    enabled: bool = True
    # "target"      : analyzed underlying, visible in the interface
    # "constituent" : collected only to feed confluence levels (Blind Spots) —
    #                 never shown in the UI, pulled more slowly because its walls
    #                 rely on OI which is published once per day
    # "context"     : not an options chain — just a context ticker
    #                 (VIX) pulled separately (scheduler.pull_vix) and absent from
    #                 pull_all. Listed here only so that
    #                 rtquote.resolve_symbols includes it in the dxFeed subscription
    #                 when a broker account is configured.
    role: str = "target"
    # Targets this constituent informs. A stock in two indices (AAPL, MSFT…) feeds both.
    links: tuple[str, ...] = ()
    # "cboe"    : chain pulled from the CBOE endpoint every 60s (gex/ingest.py), normal pull_all loop.
    # "futopt"  : options on futures, read natively via dxFeed
    #             (gex/futopt.py). A pull takes ~90s per underlying —
    #             too slow for the 60s loop: pull_native_options handles it
    #             separately every 15 min in its own thread (see scheduler.py). pull_all ignores them.
    source: str = "cboe"


UNDERLYINGS: dict[str, Underlying] = {
    u.key: u
    for u in [
        # Labels are simple tickers: the display scale (ES/NQ) has its own selector, mentioning it here would be redundant.
        Underlying("SPX", "_SPX", "SPX", future="ES", family="SP"),
        Underlying("NDX", "_NDX", "NDX", future="NQ", family="ND"),
        # ETFs: no associated future (Index/Futures selector disabled), American options,
        # and dividend-paying underlyings — see the q=0 approximation note in the README.
        Underlying("SPY", "SPY", "SPY", family="SP"),
        Underlying("QQQ", "QQQ", "QQQ", family="ND"),

        # Futures options, read natively (gex/futopt.py) instead of transposing from NDX/SPX:
        # the gamma structure of the futures market diverges from the cash index — confirmed 2026-07-27,
        # 160pt difference on NQ Zero Gamma (transposed vs. native vs. a third-party source). `cboe_symbol` is
        # a placeholder: these two targets never go through the CBOE loop (source="futopt").
        Underlying("NQ", "NQ", "NQ", family="ND", source="futopt"),
        Underlying("ES", "ES", "ES", family="SP", source="futopt"),

        # --- Constituents (Blind Spots) ------------------------------------
        # Their gamma walls are only meaningful projected onto the index they compose:
        # a wall on NVDA weighs on NQ because the stock is ~9% of the index and
        # those hedging that gamma trade NVDA. This mechanical link distinguishes
        # a constituent from a merely correlated asset (gold vs ES has no such property).
        *[Underlying(k, k, k, family="ND", role="constituent",
                     links=("NDX", "SPX"))
          for k in ("SMH", "NVDA", "AVGO", "AMD", "MU", "TSM")],
        # Mega-caps: present in both indices, with higher weight in Nasdaq-100
        *[Underlying(k, k, k, family="ND", role="constituent",
                     links=("NDX", "SPX"))
          for k in ("AAPL", "MSFT", "AMZN", "META", "GOOGL", "TSLA")],
        # Sectors absent from Nasdaq-100: they only inform S&P
        *[Underlying(k, k, k, family="SP", role="constituent", links=("SPX",))
          for k in ("XLF", "XLE")],

        # Context (get_market_context, MCP): `cboe_symbol` is a placeholder, VIX never
        # goes through the CBOE loop (see role="context" and scheduler.pull_vix,
        # which uses CBOE symbol "_VIX" directly).
        Underlying("VIX", "VIX", "VIX", family="SP", role="context"),
    ]
}


def targets() -> list[Underlying]:
    """Analyzed underlyings — those exposed in the interface."""
    return [u for u in UNDERLYINGS.values() if u.enabled and u.role == "target"]


def constituents(for_target: str | None = None) -> list[Underlying]:
    """Constituents collected for confluence levels.

    `for_target` restricts to those that inform a given target.
    """
    out = [u for u in UNDERLYINGS.values()
           if u.enabled and u.role == "constituent"]
    if for_target:
        out = [u for u in out if for_target in u.links]
    return out


@dataclass
class Settings:
    # Pull interval (seconds). 60s = max useful resolution
    # (CBOE feed is 15 min delayed at the source; this only changes sampling resolution, not the delay).
    flow_interval_s: int = 60
    # Interval for persisting a full chain snapshot (seconds).
    snapshot_interval_s: int = 600
    # Constituent pull cadence. Much slower than targets: their walls rely on OI, published once per day.
    # Pulling every 60s adds nothing and quadruples CBOE CDN load and parquet write volume.
    constituent_interval_s: int = 600
    # Constituent snapshot persistence. Very sparse: OI-based walls change once per day.
    # Saving a snapshot every 10 min would produce ~270MB/day of redundant data.
    constituent_snapshot_interval_s: int = 7200
    # Display strike window around spot (fraction).
    strike_window: float = 0.10
    # Zero gamma search grid around spot (fraction, step count).
    zg_range: float = 0.08
    zg_steps: int = 161
    # Only pull during US market hours (ET).
    market_hours_only: bool = False
    # Auto commit+push data/ git repo (history+flows) after close (16:20 ET).
    # No effect if data/ is not a git repo with a remote.
    auto_push_data: bool = True
    data_dir: Path = field(default_factory=lambda: DATA_DIR)


SETTINGS = Settings()
