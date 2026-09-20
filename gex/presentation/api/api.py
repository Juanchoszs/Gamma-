"""API JSON minimale, en lecture seule, greffée sur le serveur Flask que Dash
utilise déjà (`app.server`) — pour qu'un outil externe (indicateur de
charting, script) tournant SUR LA MÊME MACHINE puisse lire l'état courant
sans passer par l'interface.

⚠️ Portée de la licence — à ne pas confondre avec `gex.export` (qui, lui,
prépare un export destiné à être PARTAGÉ avec d'autres personnes, et filtre
donc sur `source == "cboe"` uniquement). Ici, c'est différent : ce flux sert
TOUTES les données disponibles, y compris celles issues d'un compte courtier
(dxFeed) — parce que la licence « usage personnel, non redistribuable »
autorise le titulaire du compte à utiliser SES PROPRES données dans SES
PROPRES outils (un indicateur de charting local, par exemple). Ce qu'elle
interdit, c'est de les REDISTRIBUER À DES TIERS — quelqu'un d'autre, sans son
propre compte, qui consommerait ce flux à distance. D'où la limite réelle à
respecter : ce serveur ne doit pas être exposé au-delà de la machine locale
(pas de port forwarding, pas d'écoute sur 0.0.0.0 ouverte à l'extérieur).
"""
from __future__ import annotations

import json
from datetime import date, datetime
from datetime import time as dt_time
from pathlib import Path
from time import monotonic
from zoneinfo import ZoneInfo

import pandas as pd
from flask import Flask, jsonify, redirect, request, send_from_directory

from gex.application.market_intelligence import (
    build_symbol_diagnostics,
    build_level_inspector_payload,
    build_level_history_payload,
    build_market_intelligence_snapshot,
    build_market_levels_from_gex_outputs,
    build_market_map_payload,
    build_options_chain_payload,
    build_expiry_exposure_map_payload,
    build_session_levels_from_profile,
    build_session_profile_payload,
    diagnostics_payload,
    inspect_option_data_quality,
    valid_option_records,
    market_report_to_dict,
    market_state_to_dict,
    OptionsChainConfig,
    ExpiryExposureMapConfig,
    AlertMonitor,
    classify_data_freshness,
    MarketIntelligenceConfig,
    MarketMapConfig,
    SessionProfileConfig,
    LevelHistoryObservation,
    LevelBuildConfig,
    scenario_to_dict,
)
from gex.application.options_flow.levels import build_gex_levels
from gex.domain.gex import metrics
from gex.domain.gex.metrics import ET, EXPIRY_BUCKETS
from gex.domain.market.intelligence import SessionType
from gex.infrastructure.scheduling.scheduler import STATE
from gex.infrastructure.scheduling.scheduler import market_is_open


_ALERT_MONITOR = AlertMonitor()
_INTELLIGENCE_CACHE_TTL_S = 1.5
_INTELLIGENCE_CACHE: dict[tuple, tuple[float, object]] = {}
_MARKET_COMPUTE_METRICS: dict[str, tuple[float, datetime]] = {}

REACT_CHART_NAMES = frozenset({
    "options-flow-overlay", "overview-market-map", "gex-strike", "dex-strike", "flow", "gflow", "tape",
    "gex-history", "spot-zg", "smile", "market-map-chart", "unified-level-map",
    "profile", "profile-exp", "vex", "cex", "heatmap-intraday", "heatmap-bubbles",
    "heatmap-term", "heatmap-hist", "heatmap-overlay", "pos-dist-graph", "oi-change",
    "pos-hist-graph", "vol-surface", "iv-term-structure", "gex-by-expiry",
    "oi-by-expiry", "level-history-chart",
})


def _clear_market_intelligence_cache() -> None:
    """Clear the short-lived presentation cache, primarily for test isolation."""
    _INTELLIGENCE_CACHE.clear()
    _MARKET_COMPUTE_METRICS.clear()


def _summary_dict(symbol: str, s) -> dict:
    return {
        "symbol": symbol,
        "source": s.source,
        "timestamp": s.timestamp.isoformat(),
        "spot": s.spot,
        "net_gex": s.net_gex,
        "net_gex_0dte": s.net_gex_0dte,
        "zero_gamma": s.zero_gamma,
        "net_dex": s.net_dex,
        "pc_oi": s.pc_oi,
        "pc_volume": s.pc_volume,
        "basis": s.basis,
    }


# Seuil (points) au-delà duquel un retournement compte comme un « vrai »
# retracement, par instrument. Sert au comptage n_reversals — première version
# volontairement simple, recalculable plus tard depuis les bougies brutes.
_REV_THRESHOLD = {"NQ": 30.0, "ES": 8.0, "SPX": 10.0, "NDX": 40.0,
                  "SPY": 1.0, "QQQ": 1.2}


def _count_reversals(closes, threshold: float) -> int:
    """Compte les retournements de la série de clôtures dépassant `threshold`.

    Zigzag : on suit le plus haut et le plus bas depuis le dernier pivot ; un
    reflux de `threshold` depuis l'extrême marque un pivot. Le tout PREMIER
    mouvement (celui qui établit la tendance de départ) ne compte pas comme un
    retournement — seuls les changements de sens suivants comptent. Mesure
    objective de « combien de fois le marché s'est retourné », indépendante de
    la perception du trader.
    """
    if not closes:
        return 0
    n, direction = 0, 0            # direction : 0 inconnue, +1 haussier, -1 baissier
    hi = lo = closes[0]
    for c in closes:
        hi, lo = max(hi, c), min(lo, c)
        if direction >= 0 and hi - c >= threshold:        # reflux depuis le haut
            if direction == 1:                            # on tendait à la hausse -> vrai retournement
                n += 1
            direction, hi, lo = -1, c, c
        elif direction <= 0 and c - lo >= threshold:      # rebond depuis le bas
            if direction == -1:
                n += 1
            direction, hi, lo = 1, c, c
    return n


def _session_context(symbol: str, day: str, rev_threshold: float | None = None) -> dict:
    """Vérité de marché OBJECTIVE d'une séance, calculée depuis les bougies
    1 min stockées (`store.load_prices`). Sert au journal de recherche : ce qui
    s'est réellement passé, à confronter au ressenti du sondage.

    Fonctionne en intraday (bougies partielles du jour) comme en fin de séance.
    Renvoie `available: False` si aucune bougie n'existe pour ce symbole/jour.
    """
    from datetime import date as _date, timedelta

    from gex.adapters.persistence import store

    bars = store.load_prices(symbol, day)
    d = _date.fromisoformat(day)
    out = {"symbol": symbol, "date": day, "weekday": d.weekday(), "available": False}
    if bars is None or bars.empty:
        return out
    bars = bars.sort_values("timestamp")
    o = float(bars["open"].iloc[0])
    hi = float(bars["high"].max())
    lo = float(bars["low"].min())
    last = float(bars["close"].iloc[-1])

    # clôture de la veille + ATR (moyenne des ranges quotidiens sur ~14 jours)
    prev_close, ranges = None, []
    probe = d
    for _ in range(20):
        probe -= timedelta(days=1)
        prior = store.load_prices(symbol, probe.isoformat())
        if prior is None or prior.empty:
            continue
        if prev_close is None:
            prev_close = float(prior.sort_values("timestamp")["close"].iloc[-1])
        ranges.append(float(prior["high"].max() - prior["low"].min()))
        if len(ranges) >= 14:
            break
    prev_atr = round(sum(ranges) / len(ranges), 2) if ranges else None

    rng = hi - lo
    thr = rev_threshold or _REV_THRESHOLD.get(symbol, 30.0)
    out.update({
        "available": True,
        "open": o, "high": hi, "low": lo, "close": last, "price": last,
        "prev_close": prev_close,
        "gap": round(o - prev_close, 2) if prev_close is not None else None,
        "prev_atr": prev_atr,
        "range": round(rng, 2),
        "max_up": round(hi - o, 2),
        "max_down": round(o - lo, 2),
        "close_location": round((last - lo) / rng, 3) if rng else None,
        "n_reversals": _count_reversals(bars["close"].tolist(), thr),
        "rev_threshold": thr,
    })
    return out


def _close_context(symbol: str, day: str) -> dict:
    """Pinning de clôture d'une séance : le prix s'est-il collé sur un strike /
    un mur GEX à 16h ET ? Calcul DÉRIVÉ à la demande depuis le brut (snapshot de
    chaîne ~16h + bougies), rien n'est stocké. `available: False` si les sources
    manquent (chaîne ou bougies)."""
    from gex.domain.gex import pinning
    from gex.adapters.persistence import store

    out = {"symbol": symbol, "date": day, "available": False}

    # Chaîne la plus proche de 16h ET : natif (_RT) prioritaire, sinon CBOE.
    chain = None
    for key in (f"{symbol}_RT", symbol):
        chain = store.load_snapshot_near(key, day)
        if chain is not None and not chain.empty:
            break
    if chain is None or chain.empty or "strike" not in chain or "gex" not in chain:
        out["reason"] = "pas de snapshot de chaîne pour cette séance"
        return out

    bars = store.load_prices(symbol, day)
    if bars is None or bars.empty:
        out["reason"] = "pas de bougies (prix de clôture indisponible)"
        return out
    bars = bars.sort_values("timestamp")
    target = pd.Timestamp(f"{day} 16:00:00")
    ts = pd.to_datetime(bars["timestamp"])
    close_price = float(bars["close"].iloc[(ts - target).abs().values.argmin()])

    # Fenêtre pré-clôture 15h50-16h00 ET (franchissements de strike).
    window = bars[(ts.dt.time >= dt_time(15, 50)) & (ts.dt.time <= dt_time(16, 0))]
    window_closes = [float(c) for c in window["close"].tolist()] or None

    out.update({"available": True})
    out.update(pinning.pin_metrics(chain, close_price, window_closes))
    return out


def _tick_context(symbol: str, day: str, entry: float | None = None,
                  stop: float | None = None, direction: int = 1) -> dict:
    """Fenêtre de clôture à la résolution du TICK (brut capturé 15h45-16h05 ET).

    Métriques d'excursion avant/après la clôture, et — si `entry`/`stop` sont
    fournis — le rejeu « un stop aurait-il sauté ? ». `available: False` si aucun
    tick n'a été capturé ce jour-là (capture = compte courtier requis)."""
    from gex.adapters.persistence import store
    from gex.adapters.market_data import tickstats

    ticks = store.load_ticks(symbol, day)
    out = {"symbol": symbol, "date": day}
    if ticks is None or ticks.empty:
        out.update({"available": False, "reason": "pas de ticks capturés cette séance"})
        return out
    split = datetime.combine(datetime.fromisoformat(day).date(),
                             dt_time(16, 0), ET).timestamp()
    out.update(tickstats.window_metrics(ticks, split))
    if entry is not None and stop is not None:
        out["stop_check"] = tickstats.stop_swept(ticks, entry, stop, direction, after_ts=split)
    return out


def _preferred(symbol: str) -> str:
    """Clé de STATE à lire : la chaîne native _RT si un compte est configuré et
    qu'elle a un état, sinon le symbole de base — même règle que l'interface
    (app.chain_state) pour que l'API montre ce que le dashboard montre."""
    from gex.adapters.market_data.rtquote import credentials_present
    if symbol in ("SPX", "NDX", "SPY", "QQQ") and credentials_present():
        rt = STATE.get(f"{symbol}_RT")
        with STATE.lock:
            if rt.summary is not None:
                return f"{symbol}_RT"
    return symbol


def _current_summary(symbol: str):
    """(summary, enriched) pour ce symbole, quelle que soit la source — cf.
    docstring du module sur la portée réelle de la licence."""
    st = STATE.get(_preferred(symbol))
    with STATE.lock:
        s, df = st.summary, st.enriched
    if s is None:
        return None, None
    return s, df


def _market_intelligence(
    symbol: str,
    bucket: str = "0DTE",
    *,
    config: MarketIntelligenceConfig | None = None,
    session_config: SessionProfileConfig | None = None,
    level_config: LevelBuildConfig | None = None,
):
    symbol = symbol.upper()
    s, df = _current_summary(symbol)
    if s is None or df is None:
        return None
    df = valid_option_records(df)
    if df.empty:
        return None
    if bucket not in EXPIRY_BUCKETS:
        bucket = "0DTE"
    effective_config = config or MarketIntelligenceConfig()
    effective_session_config = session_config or SessionProfileConfig()
    effective_level_config = level_config or LevelBuildConfig()
    is_open = market_is_open()
    freshness, _ = classify_data_freshness(s.timestamp, now=datetime.now(ET))
    cache_key = (
        symbol, bucket, s.timestamp, s.spot, s.net_gex, s.zero_gamma,
        is_open, freshness.value, effective_config, effective_session_config, effective_level_config,
    )
    cached = _INTELLIGENCE_CACHE.get(cache_key)
    if cached is not None and monotonic() - cached[0] <= _INTELLIGENCE_CACHE_TTL_S:
        return cached[1]
    started = monotonic()
    from gex.adapters.persistence import store

    previous_spot = store.previous_close_spot(symbol)
    structural = previous_spot or s.spot
    live = s.spot if is_open else structural
    level_result = metrics.compute_levels(df, structural, live, bucket=bucket)
    levels = build_market_levels_from_gex_outputs(
        chain=df,
        timestamp=s.timestamp,
        keys=level_result["keys"],
        zero_gamma=s.zero_gamma,
        session=SessionType.REGULAR if is_open else SessionType.CLOSED,
        config=effective_level_config,
    )
    session_profile = _session_profile_for_symbol(symbol, s.timestamp, config=effective_session_config)
    session_levels = build_session_levels_from_profile(session_profile)
    implied_volatility, call_open_interest, put_open_interest = _option_positioning_inputs(df)
    snapshot = build_market_intelligence_snapshot(
        symbol=symbol,
        spot=s.spot,
        timestamp=s.timestamp,
        levels=(*levels, *session_levels),
        net_gex=s.net_gex,
        session=SessionType.REGULAR if is_open else SessionType.CLOSED,
        previous_spot=previous_spot,
        data_status=freshness.value,
        implied_volatility=implied_volatility,
        call_open_interest=call_open_interest,
        put_open_interest=put_open_interest,
        config=effective_config,
    )
    _INTELLIGENCE_CACHE[cache_key] = (monotonic(), snapshot)
    _MARKET_COMPUTE_METRICS[symbol] = ((monotonic() - started) * 1_000.0, datetime.now(ET))
    if len(_INTELLIGENCE_CACHE) > 128:
        _INTELLIGENCE_CACHE.clear()
    return snapshot


def _option_positioning_inputs(chain: pd.DataFrame) -> tuple[float | None, float | None, float | None]:
    """Extract presentation inputs from the validated normalized options chain."""
    iv = pd.to_numeric(chain.get("iv"), errors="coerce") if "iv" in chain else pd.Series(dtype=float)
    implied_volatility = float(iv[iv > 0].median()) if not iv.empty and (iv > 0).any() else None
    if not {"type", "open_interest"}.issubset(chain.columns):
        return implied_volatility, None, None
    open_interest = pd.to_numeric(chain["open_interest"], errors="coerce").fillna(0.0)
    option_type = chain["type"].astype(str).str.upper()
    return (
        implied_volatility,
        float(open_interest[option_type == "C"].sum()),
        float(open_interest[option_type == "P"].sum()),
    )


def _market_map_payload(
    symbol: str,
    bucket: str = "0DTE",
    *,
    intelligence_config: MarketIntelligenceConfig | None = None,
    map_config: MarketMapConfig | None = None,
    session_config: SessionProfileConfig | None = None,
    level_config: LevelBuildConfig | None = None,
):
    symbol = symbol.upper()
    s, df = _current_summary(symbol)
    if s is None or df is None:
        return None
    df = valid_option_records(df)
    if df.empty:
        return None
    if bucket not in EXPIRY_BUCKETS:
        bucket = "0DTE"
    snapshot = _market_intelligence(
        symbol, bucket, config=intelligence_config, session_config=session_config, level_config=level_config,
    )
    if snapshot is None:
        return None
    return build_market_map_payload(
        symbol=symbol,
        timestamp=s.timestamp,
        spot=s.spot,
        chain=df,
        levels=snapshot.levels,
        state=snapshot.state,
        config=map_config,
    )


def _options_chain_payload(
    symbol: str,
    *,
    expiration: str | None = None,
    strike_range_pct: float = 5.0,
    side: str = "ALL",
    min_volume: float = 0.0,
    min_open_interest: float = 0.0,
    min_abs_net_gex: float = 0.0,
    min_abs_delta: float = 0.0,
):
    """Serve presentation-ready chain rows from the current enriched source."""
    symbol = symbol.upper()
    summary, chain = _current_summary(symbol)
    if summary is None or chain is None:
        return None
    chain = valid_option_records(chain)
    if chain.empty:
        return None
    snapshot = _market_intelligence(symbol, "Tout")
    return build_options_chain_payload(
        chain=chain,
        spot=summary.spot,
        levels=snapshot.report.key_levels if snapshot is not None else (),
        config=OptionsChainConfig(
            expiration=expiration,
            strike_range_pct=strike_range_pct,
            side=side,
            min_volume=min_volume,
            min_open_interest=min_open_interest,
            min_abs_net_gex=min_abs_net_gex,
            min_abs_delta=min_abs_delta,
        ),
    )


def _expiry_exposure_map_payload(
    symbol: str,
    *,
    metric: str = "gex",
    expiries: int = 10,
    strikes_each_side: int = 10,
):
    """Serve a real contract-derived strike x expiry matrix for React."""
    symbol = symbol.upper()
    summary, chain = _current_summary(symbol)
    if summary is None or chain is None:
        return None
    chain = valid_option_records(chain)
    if chain.empty:
        return None
    payload = build_expiry_exposure_map_payload(
        chain=chain,
        spot=summary.spot,
        config=ExpiryExposureMapConfig(
            metric=metric,
            expiries=expiries,
            strikes_each_side=strikes_each_side,
        ),
    )
    freshness, freshness_age = classify_data_freshness(summary.timestamp, now=datetime.now(ET))
    payload.update({
        "symbol": symbol,
        "as_of": summary.timestamp.isoformat(),
        "freshness": freshness.value,
        "freshness_age_seconds": freshness_age,
        "source": summary.source,
    })
    return payload


def _market_level_history_payload(symbol: str, day: str | None = None, bucket: str = "Tout"):
    """Derive history only from persisted enriched snapshots for one session."""
    from gex.adapters.persistence import store

    symbol = symbol.upper()
    snapshot_symbol = _preferred(symbol)
    days = store.snapshot_days(snapshot_symbol)
    if not days and snapshot_symbol != symbol:
        snapshot_symbol, days = symbol, store.snapshot_days(symbol)
    target_day = day or (days[-1] if days else None)
    if target_day is None or target_day not in days:
        return None
    observations: list[LevelHistoryObservation] = []
    history_columns = ["strike", "type", "expiry", "gex", "open_interest", "volume", "spot"]
    max_observations = 12
    for timestamp, chain in store.load_day_snapshots(
        snapshot_symbol,
        target_day,
        columns=history_columns,
        limit=max_observations,
    ):
        if chain is None or chain.empty or "spot" not in chain:
            continue
        spot = float(chain["spot"].dropna().iloc[-1]) if chain["spot"].notna().any() else 0.0
        if spot <= 0:
            continue
        # Historical rows represent the GEX stored at each observation. Do not
        # rerun the gamma-at-spot engine dozens of times while rendering a
        # session history: it is both costly and would rewrite observed state.
        snapshot_day = timestamp.date()
        chain = valid_option_records(chain)
        scoped_chain = chain[metrics.bucket_mask(chain, bucket, snapshot_day)]
        keys = metrics.key_levels(scoped_chain, spot, ref_spot=None, all_expiries=True)
        levels = build_market_levels_from_gex_outputs(
            chain=scoped_chain,
            timestamp=timestamp,
            keys=keys,
            # Zero-gamma is an expensive solved surface. Historical snapshots
            # do not persist that solved value, so omit it rather than infer a
            # path or block the terminal while recomputing it for every point.
            zero_gamma=None,
            session=SessionType.REGULAR,
        )
        observations.append(LevelHistoryObservation(timestamp=timestamp, spot=spot, levels=levels))
    payload = build_level_history_payload(symbol=symbol, observations=observations)
    payload["day"] = target_day
    payload["sampling"] = {
        "max_observations": max_observations,
        "strategy": "evenly_spaced_saved_snapshots",
    }
    return payload


def _market_level_inspector_payload(symbol: str, level_id: str, bucket: str = "0DTE"):
    snapshot = _market_intelligence(symbol, bucket)
    if snapshot is None:
        return None, "missing"
    level = _find_market_level(snapshot.report.key_levels, level_id)
    if level is None:
        return None, "not_found"
    return build_level_inspector_payload(
        level=level,
        spot=snapshot.state.spot,
        related_levels=snapshot.report.key_levels,
        scenarios=snapshot.scenarios,
    ), None


def _find_market_level(levels, level_id: str):
    normalized_id = str(level_id)
    for level in levels:
        if level.id == normalized_id:
            return level
    return None


def _market_session_payload(
    symbol: str,
    day: str | None = None,
    *,
    config: SessionProfileConfig | None = None,
):
    symbol = symbol.upper()
    s, _ = _current_summary(symbol)
    if s is None:
        return None
    return _session_profile_for_symbol(symbol, s.timestamp, day=day, config=config)


def _session_profile_for_symbol(
    symbol: str,
    timestamp: datetime,
    day: str | None = None,
    *,
    config: SessionProfileConfig | None = None,
):
    from gex.adapters.persistence import store

    cfg = config or SessionProfileConfig()
    timezone = ZoneInfo(cfg.timezone)
    market_timestamp = (
        timestamp.replace(tzinfo=timezone)
        if timestamp.tzinfo is None
        else timestamp.astimezone(timezone)
    )
    target_day = day or market_timestamp.date().isoformat()
    target_date = date.fromisoformat(target_day)
    # A historical request must be evaluated at that session's close. Using
    # today's snapshot here silently filters every historical candle out.
    effective_timestamp = (
        market_timestamp
        if target_date == market_timestamp.date()
        else datetime.combine(target_date, cfg.regular_end, tzinfo=timezone)
    )
    frames = []
    previous_days = [candidate for candidate in store.price_days(symbol) if candidate < target_day]
    if previous_days:
        previous = store.load_prices(symbol, previous_days[-1])
        if previous is not None and not previous.empty:
            frames.append(previous)
    current = store.load_prices(symbol, target_day)
    if current is not None and not current.empty:
        frames.append(current)
    prices = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return build_session_profile_payload(
        symbol=symbol,
        timestamp=effective_timestamp,
        prices=prices,
        config=cfg,
    )


def _symbol_diagnostics(symbol: str, st, now: datetime):
    with STATE.lock:
        summary = st.summary
        enriched = st.enriched
    if enriched is None or enriched.empty:
        option_count = expiration_count = strike_count = 0
    else:
        option_count = len(enriched)
        expiration_count = enriched["expiry"].nunique() if "expiry" in enriched else 0
        strike_count = enriched["strike"].nunique() if "strike" in enriched else 0
    quality = inspect_option_data_quality(enriched).to_dict()
    calculation = _MARKET_COMPUTE_METRICS.get(symbol)
    return build_symbol_diagnostics(
        symbol=symbol,
        last_update=summary.timestamp if summary is not None else None,
        options_count=option_count,
        expiration_count=expiration_count,
        strike_count=strike_count,
        source=getattr(summary, "source", None),
        last_error=STATE.last_error,
        quality=quality,
        calculation_ms=calculation[0] if calculation else None,
        last_calculation=calculation[1] if calculation else None,
        now=now,
    )


def _market_diagnostics_payload() -> dict[str, object]:
    """Return current system health from the same state used by the API.

    Keeping this builder outside the Flask route lets the local Dash terminal
    render the exact diagnostics contract without issuing an HTTP request to
    itself.
    """
    from gex.adapters.market_data.rtquote import credentials_present
    from gex.adapters.external.tt_web import connection_status

    now = datetime.now(ET)
    with STATE.lock:
        items = tuple(STATE.per_symbol.items())
        last_error = STATE.last_error
    symbols = tuple(_symbol_diagnostics(symbol, st, now) for symbol, st in items)
    status, _ = connection_status()
    websocket_status = "CONNECTED" if credentials_present() and status == "connected" else status.upper()
    return diagnostics_payload(
        symbols,
        api_status="OK",
        websocket_status=websocket_status,
        last_error=last_error,
        metadata={
            "market_open": market_is_open(),
            "symbol_count": len(symbols),
        },
    )


def _market_overlay_payload(
    symbol: str,
    *,
    bucket: str = "0DTE",
    flow_type: str = "ALL",
    flow_side: str = "ALL",
    flow_expiration: str = "ALL",
    min_premium: float = 0.0,
    min_volume: float = 0.0,
    window: float = 0.03,
    timeframe: str = "2d",
) -> dict[str, object] | None:
    """Return the normalized price/GEX/flow view model for React.

    The dashboard overlay already owns the live tape adapter and flow
    aggregation.  This endpoint deliberately delegates to it instead of
    creating a second interpretation of the options-flow data.
    """
    symbol = symbol.upper()
    summary, chain = _current_summary(symbol)
    if summary is None or chain is None:
        return None
    chain = valid_option_records(chain)
    if chain.empty:
        return None
    if bucket not in EXPIRY_BUCKETS:
        bucket = "0DTE"

    from gex.adapters.persistence import store
    from gex.presentation.dashboard.main import (
        overlay_flow_bubbles,
        overlay_price_series,
        overlay_expiration_filter,
    )

    timestamp = summary.timestamp
    market_day = timestamp.astimezone(ET).date().isoformat() if timestamp.tzinfo else timestamp.date().isoformat()
    prices, previous_prices = overlay_price_series(symbol, market_day, timeframe)
    previous_spot = store.previous_close_spot(symbol, day=market_day) or summary.spot
    is_open = market_is_open()
    live_spot = summary.spot if is_open else previous_spot
    level_result = metrics.compute_levels(chain, previous_spot, live_spot, bucket=bucket)
    gamma_flip = metrics.zero_gamma(chain, previous_spot)
    levels = build_gex_levels(chain, summary.spot, gamma_flip, level_result["keys"])
    flow_filter = overlay_expiration_filter(flow_expiration, None)
    bubbles = overlay_flow_bubbles(
        symbol,
        summary.spot,
        min_premium,
        min_volume,
        flow_type,
        flow_side,
        flow_filter,
        window,
    ) if market_day == datetime.now(ET).date().isoformat() else []

    def iso(value):
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return value

    price_rows = []
    for row in prices.to_dict("records") if prices is not None and not prices.empty else []:
        price_rows.append({key: iso(value) for key, value in row.items() if key in {"timestamp", "open", "high", "low", "close"}})

    serialized_levels = []
    for index, level in enumerate(levels):
        serialized_levels.append({
            "id": f"{str(level.name).lower().replace(' ', '-')}-{index}",
            "name": level.name,
            "price": level.price,
            "value": level.value,
            "visible": level.visible,
            "style": level.style,
            "side": level.side,
            "open_interest": level.open_interest,
            "volume": level.volume,
            "color_key": level.color_key,
        })

    serialized_bubbles = []
    for index, bubble in enumerate(bubbles):
        serialized_bubbles.append({
            "id": f"{symbol}-{bubble.timestamp.isoformat()}-{bubble.strike}-{index}",
            "timestamp": iso(bubble.timestamp),
            "strike": bubble.strike,
            "option_type": str(bubble.option_type),
            "size": bubble.size,
            "premium": bubble.premium,
            "volume": bubble.volume,
            "event_count": bubble.event_count,
            "average_price": bubble.average_price,
            "expiration": iso(bubble.expiration),
            "open_interest": bubble.open_interest,
            "implied_volatility": bubble.implied_volatility,
            "delta": bubble.delta,
            "gamma": bubble.gamma,
            "side": str(bubble.side),
            "aggressiveness": str(bubble.aggressiveness),
            "color_state": bubble.color_state,
            "tooltip": bubble.tooltip,
        })

    freshness, freshness_age = classify_data_freshness(summary.timestamp, now=datetime.now(ET))
    regime = metrics.regime_read(summary.net_gex, summary.net_dex)
    return {
        "symbol": symbol,
        "as_of": iso(timestamp),
        "freshness": freshness.value,
        "freshness_age_seconds": freshness_age,
        "current_price": summary.spot,
        "price_series": price_rows,
        "previous_price_series": [
            {key: iso(value) for key, value in row.items() if key in {"timestamp", "open", "high", "low", "close"}}
            for row in (previous_prices.to_dict("records") if previous_prices is not None and not previous_prices.empty else [])
        ],
        "gex_levels": serialized_levels,
        "flow_bubbles": serialized_bubbles,
        "market_regime": {
            "gex_frein": regime["gex_frein"],
            "dex_sign": regime["dex_sign"],
            "severity": regime["severity"],
        },
        "filters": {
            "bucket": bucket,
            "flow_type": flow_type,
            "flow_side": flow_side,
            "flow_expiration": flow_expiration,
            "min_premium": min_premium,
            "min_volume": min_volume,
            "window": window,
            "timeframe": timeframe,
        },
        "source": summary.source,
    }


def _react_chart_figure(
    symbol: str,
    name: str,
    *,
    bucket: str = "Tout",
    window: float = 0.08,
    scale: str | None = None,
    metric: str = "gex",
    series: list[str] | None = None,
    profile_expiry: str = "ALL",
    profile_side: str = "ALL",
    profile_mode: str = "NET",
    lang: str = "en",
):
    """Build one of the existing Dash figures for the React chart deck.

    React owns layout and interaction around the figure, while the Python
    dashboard remains the sole owner of the calculations and source data.
    Imports stay lazy because ``dashboard.main`` mounts this API itself.
    """
    from gex.presentation.dashboard import main as dashboard

    symbol = symbol.upper()
    lang = "es" if lang == "es" else "en"
    bucket = "Tout" if bucket == "ALL" else bucket
    window = max(float(window or 0.08), 0.005)
    scale = (scale or symbol).upper()
    aliases = {
        "gex-strike": "gex", "dex-strike": "dex", "gex-history": "history",
        "spot-zg": "spotzg", "pos-dist-graph": "oi", "oi-change": "oi_change",
        "pos-hist-graph": "pos_hist", "vol-surface": "vol_surface",
        "iv-term-structure": "iv_term_structure", "gex-by-expiry": "gex_by_expiry",
        "oi-by-expiry": "oi_by_expiry", "vex": "vanna", "cex": "charm",
    }
    selected_series = [item for item in (series or ["calls", "puts", "net"])
                       if item in {"calls", "puts", "net"}]
    if not selected_series:
        selected_series = ["calls", "puts", "net"]
    if name == "gflow":
        return dashboard.gamma_flow_fig(symbol, lang, series=selected_series)
    if name == "tape":
        return dashboard.tape_fig(symbol, lang, series=selected_series)
    if name == "options-flow-overlay":
        st = dashboard.chain_state(symbol)
        with dashboard.STATE.lock:
            chain, snap = st.enriched, st.snapshot
        if chain is None or snap is None:
            return dashboard.empty_fig("Esperando la primera cadena de opciones" if lang == "es" else "Waiting for the first option chain", "Options flow overlay")
        day = datetime.now(ET).strftime("%Y-%m-%d")
        prices, previous_prices = dashboard.overlay_price_series(symbol, day, "2d")
        previous_spot = dashboard.store.previous_close_spot(symbol, day=day) or snap.spot
        level_result = dashboard.metrics.compute_levels(chain, previous_spot, snap.spot, bucket=bucket)
        gamma_flip = dashboard.metrics.zero_gamma(chain, previous_spot)
        gex_levels = dashboard.build_gex_levels(chain, snap.spot, gamma_flip, level_result["keys"])
        bubbles = dashboard.overlay_flow_bubbles(
            symbol, snap.spot, 0.0, 0.0, "ALL", "ALL", "ALL", window,
        )
        xf, _, _ = dashboard._transform_for(symbol, scale)
        return dashboard.build_options_overlay_from_view_model(
            dashboard.OptionsOverlayViewModel(
                symbol=symbol,
                price_series=prices,
                previous_price_series=previous_prices,
                current_price=snap.spot,
                chain=chain,
                gamma_flip=gamma_flip,
                keys=level_result["keys"],
                day=day,
                window=window,
                gex_levels=gex_levels,
                flow_bubbles=bubbles,
            ),
            transform=xf,
            timeframe="2d",
        )
    if name in aliases or name in {"flow", "smile"}:
        return dashboard._figure_for(
            symbol, aliases.get(name, name), lang=lang, bucket=bucket,
            window=window, scale=scale,
        )

    if name in {"profile", "profile-exp"}:
        st = dashboard.chain_state(symbol)
        with dashboard.STATE.lock:
            df, snap = st.enriched, st.snapshot
        if df is None or snap is None:
            return dashboard.empty_fig("Esperando la primera cadena de opciones" if lang == "es" else "Waiting for the first option chain", "Gamma profile")
        expiry_aliases = {"ALL": "Tout", "WEEKLY": "Semaine", "MONTHLY": "Mois"}
        selected_expiry = expiry_aliases.get(profile_expiry, profile_expiry)
        if selected_expiry not in dashboard.EXPIRY_BUCKETS and selected_expiry != "Tout":
            selected_expiry = "Tout"
        selected_side = profile_side if profile_side in {"CALLS", "PUTS"} else "ALL"
        scoped = dashboard._profile_chain_for_display(df, selected_expiry, selected_side)
        absolute = profile_mode == "ABSOLUTE"
        width = max(window, 0.06)
        xf, _, _ = dashboard._transform_for(symbol, scale)
        if name == "profile":
            zero_gamma = dashboard.metrics.zero_gamma(scoped, snap.spot) if not absolute else None
            return dashboard.profile_fig(scoped, snap.spot, zero_gamma, lang, width, xf, absolute=absolute)
        buckets = tuple(dashboard.EXPIRY_BUCKETS) if selected_expiry == "Tout" else (selected_expiry,)
        by_expiry = dashboard._profile_chain_for_display(df, "Tout", selected_side)
        return dashboard.profile_by_expiry_fig(
            by_expiry, snap.spot, lang, width, xf, buckets=buckets, absolute=absolute,
        )

    xf, _, _ = dashboard._transform_for(symbol, scale)
    day = datetime.now(ET).strftime("%Y-%m-%d")
    if name == "heatmap-intraday":
        return dashboard.heatmap_intraday_fig(symbol, lang, day, window, xf, scale, None, metric)
    if name == "heatmap-bubbles":
        return dashboard.heatmap_bubbles_fig(symbol, lang, day, window, xf, scale, None, metric)
    if name == "heatmap-term":
        return dashboard.heatmap_term_fig(symbol, lang, day, window, xf, scale, None, metric)
    if name == "heatmap-hist":
        return dashboard.heatmap_history_fig(symbol, lang, xf)
    if name == "heatmap-overlay":
        return dashboard.heatmap_fig(symbol, lang, day, window, xf, scale)
    if name in {"overview-market-map", "market-map-chart"}:
        return dashboard._market_map_figure_for_display(
            symbol, bucket, map_window=3.0, neutral_gex=0.0,
            scenario_limit=5, value_area=0.70, visible_sources=None,
            wall_min_strength=0,
        )
    if name == "unified-level-map":
        snapshot = _market_intelligence(symbol, bucket)
        levels = snapshot.report.key_levels if snapshot is not None else ()
        return dashboard.build_level_map_figure(snapshot, levels)
    if name == "level-history-chart":
        return dashboard.build_level_history_figure(
            _market_level_history_payload(symbol, bucket=bucket), level_types=None,
        )
    return None


def _react_chart_payload(symbol: str, names: list[str], **options) -> dict[str, object]:
    """Serialize a bounded chart suite for React without changing chart math."""
    charts: dict[str, object] = {}
    errors: dict[str, str] = {}
    for name in names:
        try:
            figure = _react_chart_figure(symbol, name, **options)
            charts[name] = json.loads(figure.to_json()) if figure is not None else None
        except Exception as exc:  # one unavailable secondary chart must not blank the deck
            charts[name] = None
            errors[name] = str(exc)
    payload: dict[str, object] = {"symbol": symbol.upper(), "charts": charts}
    if errors:
        payload["errors"] = errors
    return payload


def _price_history_payload(symbol: str, sessions: int = 5, interval: str = "5m") -> dict[str, object]:
    """Return stored OHLC bars across recent sessions, without synthetic values."""
    from gex.adapters.persistence import store

    symbol = symbol.upper()
    interval = interval if interval in {"1m", "5m", "15m"} else "5m"
    sessions = max(1, min(int(sessions or 5), 10))
    source_symbol = symbol
    days = store.price_days(source_symbol)
    if not days and symbol in {"ES", "NQ"}:
        source_symbol = {"ES": "SPX", "NQ": "NDX"}[symbol]
        days = store.price_days(source_symbol)
    selected_days = days[-sessions:]
    frames: list[pd.DataFrame] = []
    usable_days: list[str] = []
    for day in selected_days:
        frame = store.load_prices(source_symbol, day)
        if frame is None or frame.empty:
            continue
        required = {"timestamp", "open", "high", "low", "close"}
        if not required.issubset(frame.columns):
            continue
        clean = frame[list(required | ({"volume"} if "volume" in frame.columns else set()))].copy()
        clean["timestamp"] = pd.to_datetime(clean["timestamp"], errors="coerce")
        for column in ("open", "high", "low", "close", "volume"):
            if column in clean:
                clean[column] = pd.to_numeric(clean[column], errors="coerce")
        clean = clean.dropna(subset=["timestamp", "open", "high", "low", "close"])
        if not clean.empty:
            frames.append(clean)
            usable_days.append(day)
    if not frames:
        return {
            "symbol": symbol,
            "source_symbol": source_symbol,
            "requested_sessions": sessions,
            "available_sessions": 0,
            "sessions": [],
            "interval": interval,
            "rows": [],
            "source": "stored OHLC",
        }

    bars = pd.concat(frames, ignore_index=True).sort_values("timestamp")
    rule = {"1m": "1min", "5m": "5min", "15m": "15min"}[interval]
    aggregations = {"open": "first", "high": "max", "low": "min", "close": "last"}
    if "volume" in bars:
        aggregations["volume"] = "sum"
    bars = (
        bars.set_index("timestamp")
        .groupby(lambda value: value.date())
        .resample(rule, origin="start_day")
        .agg(aggregations)
        .dropna(subset=["open", "high", "low", "close"])
        .reset_index(level=0, drop=True)
        .reset_index()
        .sort_values("timestamp")
    )
    rows = []
    for row in bars.to_dict(orient="records"):
        timestamp = pd.Timestamp(row["timestamp"])
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize(ET)
        row["timestamp"] = timestamp.isoformat()
        rows.append({key: value for key, value in row.items() if pd.notna(value)})
    return {
        "symbol": symbol,
        "source_symbol": source_symbol,
        "requested_sessions": sessions,
        "available_sessions": len(usable_days),
        "sessions": usable_days,
        "interval": interval,
        "rows": rows,
        "source": "stored OHLC",
    }


def _liquidity_heatmap_payload(symbol: str, window: float, metric: str, lang: str = "en") -> dict[str, object]:
    """Flatten the existing Dash option/GEX heatmap for the native canvas."""
    from gex.presentation.dashboard import main as dashboard

    symbol = symbol.upper()
    lang = "es" if lang == "es" else "en"
    metric = metric if metric in {"gex", "oi", "vol"} else "gex"
    day = datetime.now(ET).strftime("%Y-%m-%d")
    xf, _, _ = dashboard._transform_for(symbol, symbol)
    figure = dashboard.heatmap_intraday_fig(symbol, lang, day, max(float(window or 0.08), 0.005), xf, symbol, None, metric)
    trace_object = next((item for item in figure.data if item.type == "heatmap"), None)
    if trace_object is None:
        return {"symbol": symbol, "metric": metric, "rows": 0, "cols": 0, "matrix": [], "source": "stored option snapshots"}
    z_values = trace_object.z.tolist() if hasattr(trace_object.z, "tolist") else list(trace_object.z or [])
    y_values = trace_object.y.tolist() if hasattr(trace_object.y, "tolist") else list(trace_object.y or [])
    x_values = list(trace_object.x or [])
    matrix = [[float(value or 0.0) for value in row] for row in z_values]
    y_values = [float(value) for value in y_values if value is not None]
    if not matrix or not matrix[0] or not y_values or not x_values:
        return {"symbol": symbol, "metric": metric, "rows": 0, "cols": 0, "matrix": [], "source": "stored option snapshots"}
    timestamps = []
    for value in x_values:
        text_value = str(value)
        timestamp = pd.Timestamp(f"{day}T{text_value}:00", tz=ET) if len(text_value) == 5 else pd.Timestamp(value)
        timestamps.append(int(timestamp.timestamp()))
    return {
        "symbol": symbol,
        "metric": metric,
        "rows": len(matrix),
        "cols": len(matrix[0]),
        "matrix": [value for row in matrix for value in row],
        "price_min": min(y_values),
        "price_max": max(y_values),
        "time_start": min(timestamps),
        "time_end": max(timestamps) if len(timestamps) > 1 else timestamps[0] + 300,
        "source": "stored option snapshots",
        "as_of": datetime.now(ET).isoformat(),
    }


def register_api(app) -> None:
    """`app` : l'instance Dash (on grimpe à `.server`) ou directement une
    instance Flask — pratique pour les tests, qui n'ont pas besoin de monter
    tout le dashboard."""
    server: Flask = app.server if hasattr(app, "server") else app
    react_dist = (Path(__file__).resolve().parents[2] / ".." / "frontend" / "dist").resolve()

    @server.route("/terminal", defaults={"resource": ""})
    @server.route("/terminal/", defaults={"resource": ""})
    @server.route("/terminal/<path:resource>")
    def _react_terminal(resource):
        """Serve the compiled React terminal when a frontend build exists."""
        if request.path == "/terminal":
            query = request.query_string.decode("utf-8")
            return redirect(f"/terminal/?{query}" if query else "/terminal/", code=308)
        # A public `/terminal/` base must never be applied twice. This also
        # repairs bookmarks created while the first React shell used absolute
        # `/terminal/...` links inside a router with the same basename.
        if resource == "terminal" or resource.startswith("terminal/"):
            suffix = resource[len("terminal"):].lstrip("/")
            target = f"/terminal/{suffix}" if suffix else "/terminal/"
            query = request.query_string.decode("utf-8")
            return redirect(f"{target}?{query}" if query else target, code=308)
        index = react_dist / "index.html"
        if not index.exists():
            return jsonify({
                "error": "React terminal not built",
                "command": "cd frontend && npm run build",
            }), 404
        requested = (react_dist / resource).resolve() if resource else index
        if requested.is_file() and react_dist in requested.parents:
            return send_from_directory(react_dist, resource or "index.html")
        return send_from_directory(react_dist, "index.html")

    @server.after_request
    def _cors(resp):
        # CORS large parce que le risque visé est différent de celui d'un
        # site web classique : ce serveur n'écoute qu'en local (cf. docstring
        # du module) — le vrai garde-fou est là, pas dans l'en-tête CORS.
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp

    @server.route("/api/v1/symbols")
    def _symbols():
        out = []
        with STATE.lock:
            items = list(STATE.per_symbol.items())
        for symbol, st in items:
            if st.summary is not None:
                out.append(symbol)
        return jsonify(sorted(out))

    @server.route("/api/v1/<symbol>/summary")
    def _summary(symbol):
        symbol = symbol.upper()
        s, _ = _current_summary(symbol)
        if s is None:
            return jsonify({"error": "indisponible (pas encore de premier pull)"}), 404
        return jsonify(_summary_dict(symbol, s))

    @server.route("/api/v1/<symbol>/levels")
    def _levels(symbol):
        symbol = symbol.upper()
        s, df = _current_summary(symbol)
        if s is None or df is None:
            return jsonify({"error": "indisponible (pas encore de premier pull)"}), 404
        # Source UNIQUE des niveaux (cf. metrics.compute_levels) : mêmes murs que
        # le dashboard. structural_spot = clôture veille (magnitude), live_spot =
        # spot courant en séance (côté). `?bucket=` fixe le périmètre d'échéances.
        from gex.presentation.dashboard.main import market_is_open, ref_spot as _ref_spot
        bucket = request.args.get("bucket", "0DTE")
        if bucket not in EXPIRY_BUCKETS:
            bucket = "0DTE"
        structural = _ref_spot(symbol, s.spot)
        live = s.spot if market_is_open() else structural
        res = metrics.compute_levels(df, structural, live, bucket=bucket)
        levels, keys = res["levels"], res["keys"]
        hvl = metrics.zero_gamma(df, s.spot, weight_col="volume")

        # Transposition d'échelle optionnelle : ?scale=NQ exprime les niveaux
        # NDX en prix NQ (cf. app._transform_for / le sélecteur d'unité). Utile
        # quand on trade le future mais que les niveaux viennent de l'indice.
        scale = request.args.get("scale")
        xf = (lambda v: v)
        if scale and scale.upper() != symbol:
            from gex.presentation.dashboard.main import _transform_for
            xf, _, _ = _transform_for(symbol, scale.upper())

        def _t(v):
            return float(xf(v)) if isinstance(v, (int, float)) else v

        return jsonify({
            "symbol": symbol,
            "scale": (scale.upper() if scale else symbol),
            "spot": _t(s.spot),
            "zero_gamma": _t(s.zero_gamma),
            "hvl": _t(hvl),
            "key_levels": {k: _t(v) for k, v in keys.items()},
            "gex_walls": [
                {"strike": _t(float(r.strike)), "gex": float(r.gex), "expiry": str(r.expiry)}
                for r in levels.itertuples()
            ],
        })

    @server.route("/api/v1/<symbol>/regime")
    def _regime(symbol):
        symbol = symbol.upper()
        s, _ = _current_summary(symbol)
        if s is None:
            return jsonify({"error": "indisponible (pas encore de premier pull)"}), 404
        r = metrics.regime_read(s.net_gex, s.net_dex)
        return jsonify({
            "symbol": symbol,
            "gex_frein": r["gex_frein"],
            "dex_sign": r["dex_sign"],
            "severity": r["severity"],
            "disclaimer": "Lecture mécanique de la couverture dealers, pas un signal d'entrée.",
        })

    @server.route("/api/v1/<symbol>/market/state")
    def _market_state(symbol):
        snapshot = _market_intelligence(symbol, request.args.get("bucket", "0DTE"))
        if snapshot is None:
            return jsonify({"error": "indisponible (pas encore de premier pull)"}), 404
        return jsonify(market_state_to_dict(snapshot.state, lang=request.args.get("lang", "en")))

    @server.route("/api/v1/<symbol>/market/scenarios")
    def _market_scenarios(symbol):
        snapshot = _market_intelligence(symbol, request.args.get("bucket", "0DTE"))
        if snapshot is None:
            return jsonify({"error": "indisponible (pas encore de premier pull)"}), 404
        lang = request.args.get("lang", "en")
        return jsonify({
            "symbol": snapshot.state.symbol,
            "timestamp": snapshot.state.timestamp.isoformat(),
            "scenarios": [scenario_to_dict(scenario, lang=lang) for scenario in snapshot.scenarios],
        })

    @server.route("/api/v1/<symbol>/market/alerts")
    def _market_alerts(symbol):
        """Return opt-in transition events; it does not push notifications."""
        snapshot = _market_intelligence(symbol, request.args.get("bucket", "0DTE"))
        if snapshot is None:
            return jsonify({"error": "indisponible (pas encore de premier pull)"}), 404
        return jsonify({
            "symbol": snapshot.state.symbol,
            "alerts": [alert.to_dict() for alert in _ALERT_MONITOR.observe(snapshot)],
        })

    @server.route("/api/v1/<symbol>/market/report")
    def _market_report(symbol):
        snapshot = _market_intelligence(symbol, request.args.get("bucket", "0DTE"))
        if snapshot is None:
            return jsonify({"error": "indisponible (pas encore de premier pull)"}), 404
        return jsonify(market_report_to_dict(snapshot.report, lang=request.args.get("lang", "en")))

    @server.route("/api/v1/<symbol>/market/map")
    def _market_map(symbol):
        payload = _market_map_payload(symbol, request.args.get("bucket", "0DTE"))
        if payload is None:
            return jsonify({"error": "indisponible (pas encore de premier pull)"}), 404
        return jsonify(payload)

    @server.route("/api/v1/<symbol>/market/overlay")
    def _market_overlay(symbol):
        """Serve the React price/GEX/options-flow overlay view model."""
        try:
            payload = _market_overlay_payload(
                symbol,
                bucket=request.args.get("bucket", "0DTE"),
                flow_type=request.args.get("flow_type", "ALL"),
                flow_side=request.args.get("flow_side", "ALL"),
                flow_expiration=request.args.get("flow_expiration", "ALL"),
                min_premium=float(request.args.get("min_premium", "0")),
                min_volume=float(request.args.get("min_volume", "0")),
                window=float(request.args.get("window", "0.03")),
                timeframe=request.args.get("timeframe", "2d"),
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if payload is None:
            return jsonify({"error": "indisponible (pas encore de premier pull)"}), 404
        return jsonify(payload)

    @server.route("/api/v1/<symbol>/market/charts")
    def _market_charts(symbol):
        """Expose the existing Dash chart catalog as lazy React figures."""
        names = [name.strip() for name in request.args.get("names", "").split(",") if name.strip()]
        unknown = [name for name in names if name not in REACT_CHART_NAMES]
        if unknown:
            return jsonify({"error": f"chart names not allowed: {', '.join(unknown)}"}), 400
        if not names:
            return jsonify({"error": "at least one chart name is required"}), 400
        try:
            window = float(request.args.get("window", "0.08"))
        except ValueError:
            return jsonify({"error": "window must be numeric"}), 400
        series = [value for value in request.args.get("series", "calls,puts,net").split(",") if value]
        payload = _react_chart_payload(
            symbol,
            names[:16],
            bucket=request.args.get("bucket", "Tout"),
            window=window,
            scale=request.args.get("scale"),
            metric=request.args.get("metric", "gex"),
            series=series,
            profile_expiry=request.args.get("profile_expiry", "ALL"),
            profile_side=request.args.get("profile_side", "ALL"),
            profile_mode=request.args.get("profile_mode", "NET"),
            lang=request.args.get("lang", "en"),
        )
        return jsonify(payload)

    @server.route("/api/v1/<symbol>/options/chain")
    def _options_chain(symbol):
        expiration = request.args.get("expiration") or None
        side = request.args.get("side", "ALL")
        try:
            range_pct = float(request.args.get("range_pct", "5"))
            min_volume = float(request.args.get("min_volume", "0"))
            min_open_interest = float(request.args.get("min_open_interest", "0"))
            min_abs_net_gex = float(request.args.get("min_abs_net_gex", "0"))
            min_abs_delta = float(request.args.get("min_abs_delta", "0"))
            payload = _options_chain_payload(
                symbol,
                expiration=expiration,
                strike_range_pct=range_pct,
                side=side,
                min_volume=min_volume,
                min_open_interest=min_open_interest,
                min_abs_net_gex=min_abs_net_gex,
                min_abs_delta=min_abs_delta,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if payload is None:
            return jsonify({"error": "indisponible (pas encore de premier pull)"}), 404
        return jsonify(payload)

    @server.route("/api/v1/<symbol>/market/expiry-map")
    def _market_expiry_map(symbol):
        metric = request.args.get("metric", "gex")
        try:
            expiries = int(request.args.get("expiries", "10"))
            strikes_each_side = int(request.args.get("strikes", "10"))
            payload = _expiry_exposure_map_payload(
                symbol,
                metric=metric,
                expiries=expiries,
                strikes_each_side=strikes_each_side,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if payload is None:
            return jsonify({"error": "No valid options chain available"}), 404
        return jsonify(payload)

    @server.route("/api/v1/<symbol>/market/levels/history")
    def _market_levels_history(symbol):
        bucket = request.args.get("bucket", "Tout")
        if bucket not in EXPIRY_BUCKETS:
            return jsonify({"error": "bucket inválido"}), 400
        payload = _market_level_history_payload(symbol, request.args.get("date"), bucket)
        if payload is None:
            return jsonify({"error": "sin snapshots para la sesión solicitada"}), 404
        return jsonify(payload)

    @server.route("/api/v1/<symbol>/market/levels/<path:level_id>")
    def _market_level_inspector(symbol, level_id):
        payload, error = _market_level_inspector_payload(
            symbol,
            level_id,
            request.args.get("bucket", "0DTE"),
        )
        if error == "missing":
            return jsonify({"error": "indisponible (pas encore de premier pull)"}), 404
        if error == "not_found":
            return jsonify({"error": "niveau introuvable"}), 404
        return jsonify(payload)

    @server.route("/api/v1/<symbol>/market/session")
    def _market_session(symbol):
        day = request.args.get("date")
        if day:
            try:
                date.fromisoformat(day)
            except ValueError:
                return jsonify({"error": "fecha inválida; usa YYYY-MM-DD"}), 400
        payload = _market_session_payload(symbol, day)
        if payload is None:
            return jsonify({"error": "indisponible (pas encore de premier pull)"}), 404
        return jsonify(payload)

    @server.route("/api/v1/<symbol>/market/prices")
    def _market_prices(symbol):
        """Serve stored OHLC bars for the React terminal without recalculation."""
        from gex.adapters.persistence import store

        symbol = symbol.upper()
        days = store.price_days(symbol)
        requested_day = request.args.get("date")
        day = requested_day if requested_day in days else (days[-1] if days else None)
        if day is None:
            return jsonify({"symbol": symbol, "date": None, "rows": []})
        frame = store.load_prices(symbol, day)
        if frame is None or frame.empty:
            return jsonify({"symbol": symbol, "date": day, "rows": []})
        rows = frame.copy()
        rows["timestamp"] = pd.to_datetime(rows["timestamp"]).map(lambda value: value.isoformat())
        columns = [column for column in ("timestamp", "open", "high", "low", "close") if column in rows]
        return jsonify({
            "symbol": symbol,
            "date": day,
            "rows": rows[columns].to_dict(orient="records"),
        })

    @server.route("/api/v1/<symbol>/market/prices/history")
    def _market_prices_history(symbol):
        try:
            sessions = int(request.args.get("days", "5"))
        except ValueError:
            return jsonify({"error": "days must be an integer"}), 400
        interval = request.args.get("interval", "5m")
        if interval not in {"1m", "5m", "15m"}:
            return jsonify({"error": "interval must be 1m, 5m or 15m"}), 400
        return jsonify(_price_history_payload(symbol, sessions=sessions, interval=interval))

    @server.route("/api/v1/<symbol>/market/liquidity-heatmap")
    def _market_liquidity_heatmap(symbol):
        try:
            window = float(request.args.get("window", "0.08"))
            if window <= 0:
                raise ValueError
        except ValueError:
            return jsonify({"error": "window must be a positive number"}), 400
        try:
            payload = _liquidity_heatmap_payload(
                symbol,
                window=window,
                metric=request.args.get("metric", "gex"),
                lang=request.args.get("lang", "en"),
            )
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(payload)

    @server.route("/api/v1/<symbol>/strikes")
    def _strikes(symbol):
        symbol = symbol.upper()
        bucket = request.args.get("bucket", "Tout")
        s, df = _current_summary(symbol)
        if s is None or df is None:
            return jsonify({"error": "indisponible (pas encore de premier pull)"}), 404
        if bucket in EXPIRY_BUCKETS:
            today = datetime.now(ET).date()
            df = df[metrics.bucket_mask(df, bucket, today)]
        cols = ["strike", "type", "expiry", "open_interest", "gex", "dex"]
        rows = df[cols].copy()
        rows["expiry"] = rows["expiry"].astype(str)
        return jsonify({
            "symbol": symbol, "spot": s.spot, "bucket": bucket,
            "rows": rows.to_dict(orient="records"),
        })

    @server.route("/api/v1/<symbol>/session_context")
    def _session(symbol):
        """Vérité de marché objective d'une séance (OHLC, gap, ATR veille,
        excursions, retournements) — pour le journal de recherche.

        `?date=YYYY-MM-DD` (défaut : jour ET courant). `?rev=` force le seuil de
        retournement. En intraday, renvoie l'état courant (bougies partielles).
        """
        symbol = symbol.upper()
        day = request.args.get("date") or datetime.now(ET).date().isoformat()
        rev = request.args.get("rev", type=float)
        return jsonify(_session_context(symbol, day, rev))

    @server.route("/api/v1/<symbol>/close_context")
    def _close(symbol):
        """Pinning de clôture (16h ET) : distance au strike/mur GEX, pin_ratio,
        franchissements pré-clôture — calcul à la demande, pour le backtest du
        comportement de clôture. `?date=YYYY-MM-DD` (défaut : jour ET courant)."""
        symbol = symbol.upper()
        day = request.args.get("date") or datetime.now(ET).date().isoformat()
        return jsonify(_close_context(symbol, day))

    @server.route("/api/v1/<symbol>/tick_context")
    def _tick(symbol):
        """Fenêtre de clôture au tick. `?date=` ; `?entry=&stop=&dir=long|short`
        pour rejouer « un stop aurait-il sauté ? »."""
        symbol = symbol.upper()
        day = request.args.get("date") or datetime.now(ET).date().isoformat()
        entry = request.args.get("entry", type=float)
        stop = request.args.get("stop", type=float)
        direction = -1 if request.args.get("dir", "long").lower().startswith("s") else 1
        return jsonify(_tick_context(symbol, day, entry, stop, direction))

    @server.route("/api/v1/vix")
    def _vix():
        """VIX courant + seuil du digest (pour une interrogation directe)."""
        from gex.domain.analytics import digest as digest_mod
        v = digest_mod._current_vix()
        if v is None:
            return jsonify({"available": False})
        return jsonify({"available": True, "vix": round(float(v), 2),
                        "seuil": digest_mod.VIX_SEUIL,
                        "above": bool(v > digest_mod.VIX_SEUIL),
                        "grade": digest_mod.vix_grade(float(v))})

    @server.route("/api/v1/digest")
    def _digest():
        """Verdict d'état du gamma prêt à diffuser (cf. gex/digest.py).

        C'est ce qu'un bot Discord consomme : le texte, la couleur, et la
        `signature` de régime (pour ne re-poster que sur un vrai changement).
        Renvoie une analyse dérivée, jamais la chaîne brute.
        """
        from gex.domain.analytics import digest as digest_mod
        d = digest_mod.current_digest()
        return jsonify({
            "header": d.header,
            "lines": d.lines,
            "vix_line": d.vix_line,
            "verdict": d.verdict,
            "color": d.color,
            "discord_color": d.discord_color,
            "confidence": d.confidence,
            "families": d.families,
            "close_message": d.close_message,
            "text": d.to_text(),
            "signature": list(d.signature),
        })

    @server.route("/api/v1/diagnostics")
    def _diagnostics():
        return jsonify(_market_diagnostics_payload())
