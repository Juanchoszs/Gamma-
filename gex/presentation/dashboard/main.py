"""Dashboard Dash : GEX/DEX par strike, indicateurs, flux delta, skew IV.

Palette : polarité (GEX/flux +/-) en diverging bleu↔rouge, identité
(calls/puts, expirations) sur les slots catégoriels — thème sombre.
Interface FR/EN (gex/i18n.py) ; termes de trading standards dans les deux.
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from time import monotonic

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import dash
from dash import Dash, ctx, dcc, html, no_update
from dash.dependencies import ALL, Input, Output, State
from dash.exceptions import PreventUpdate

from gex.domain.analytics import digest
from gex.domain.gex import metrics
from gex.domain.market import scales
from gex.application.options_flow.service import (
    OptionsFlowOverlayConfig,
    build_flow_bubbles,
    events_from_records,
)
from gex.application.options_flow.dto import OptionsOverlayViewModel
from gex.application.options_flow.levels import build_gex_levels
from gex.application.market_intelligence.level_inspector import build_level_inspector_payload
from gex.application.market_intelligence.service import MarketIntelligenceConfig
from gex.application.market_intelligence.market_map import MarketMapConfig
from gex.application.market_intelligence.session_profile import SessionProfileConfig
from gex.application.market_intelligence.options_chain import (
    OptionsChainConfig,
    available_expirations,
    build_options_chain_payload,
)
from gex.application.market_intelligence.levels import LevelBuildConfig
from gex.application.market_intelligence.data_quality import valid_option_records
from gex.application.market_intelligence.alerts import AlertConfig, AlertMonitor
from gex.domain.options.models import FlowSide, OptionType
from gex.adapters.persistence import store
from gex.presentation.api.api import (
    _market_diagnostics_payload,
    _market_intelligence,
    _market_level_history_payload,
    _market_map_payload,
    _market_session_payload,
    register_api,
)
from gex.presentation.dashboard.heatmap import build_intraday_heatmap
from gex.presentation.dashboard.options_overlay import (
    build_options_overlay,
    build_options_overlay_from_view_model,
    merge_relayout_ranges,
)
from gex.adapters.external.tt_web import (
    connection_status,
    register_oauth,
    shared_deployment_enabled,
)
from gex.adapters.external import tt_auth
from gex.infrastructure.config import SETTINGS, UNDERLYINGS, targets, all_targets
from gex.presentation.i18n.i18n import LANGS, regime_text, t, wall_labels
from gex.domain.gex.metrics import ET, EXPIRY_BUCKETS
from gex.domain.market.intelligence import LevelSource, LevelType, SessionType
from gex.adapters.market_data import idxopt
from gex.adapters.market_data.flowtape import TAPE
from gex.adapters.market_data.rtquote import PUBLIC_QUOTES, QUOTES, credentials_present
from gex.infrastructure.scheduling.scheduler import STATE, market_is_open
from gex.infrastructure.scheduling.scheduler import native_index_key as scheduler_native_key
from gex.presentation.dashboard.chart_theme import INSTITUTIONAL_THEME
from gex.presentation.dashboard.chart_animations import animation_engine, AnimationPresets
from gex.presentation.dashboard.terminal import (
    intelligence_view,
    alerts_view,
    diagnostics_view,
    level_inspector_view,
    filter_levels,
    levels_view,
    market_report_view,
    overview_briefing_view,
    options_chain_view,
    scenarios_view,
    scenario_inspector_view,
    session_profile_view,
    terminal_topbar_market,
    topbar_market_view,
    terminal_intelligence_panel,
    terminal_sidebar,
    terminal_statusbar,
    terminal_accent_style,
    terminal_navigation_pages,
)
from gex.presentation.dashboard.level_history import build_level_history_figure
from gex.presentation.dashboard.level_map import build_level_map_figure
from gex.presentation.dashboard.market_map import build_market_map_figure

# --- Palette (mode sombre, cf. skill dataviz) ---
log = logging.getLogger(__name__)
_HEAT_BUBBLE_SNAPSHOT_CACHE: dict[
    tuple[str, str], tuple[float, list[tuple[datetime, pd.DataFrame]], float]
] = {}
_HEAT_BUBBLE_CACHE_TTL_S = 5.0
_OVERLAY_FLOW_BUBBLE_CACHE: dict[tuple, tuple[tuple, list]] = {}
_OVERLAY_FLOW_BUBBLE_CACHE_MAX = 64

C = {
    "surface": "#0b1118",
    "page": "#070a0f",
    "ink": "#f4f7fb",
    "ink2": "#a8b3c2",
    "muted": "#748295",
    "grid": "#17232e",
    "axis": "#334354",
    "pos": "#58b6c4",
    "neg": "#d98795",
    "spot": "#f4f7fb",
    "zg": "#d8b65a",
    "warn": "#d8b65a",
    "lvl": "#58b6c4",
    "hvl": "#a78bfa",
    "cw": "#58b6c4",
    "ps": "#d98795",
    "d1": "#5e9cf3",
    "ok": "#6b93e5",
    "cat": ["#58b6c4", "#d98795", "#a78bfa", "#d8b65a"],
}

FONT = 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'

# Fuseau local de la machine — tous les axes temps sont affichés en heure locale
LOCAL_TZ = datetime.now().astimezone().tzinfo

BUCKET_KEYS = {"0DTE": "bucket_0DTE", "Semaine": "bucket_week",
               "Mois": "bucket_month", "Tout": "bucket_all"}

TAB_STYLE = {"backgroundColor": C["surface"], "color": C["ink2"],
             "border": f"1px solid {C['grid']}", "padding": "8px 16px", "fontSize": "13px",
             "borderRadius": "4px 4px 0 0"}
TAB_SELECTED = {"backgroundColor": "#101923", "color": C["ink"],
                "border": f"1px solid {C['grid']}", "borderBottom": f"2px solid {C['lvl']}",
                "padding": "8px 16px", "fontSize": "13px", "fontWeight": "600",
                "borderRadius": "4px 4px 0 0"}
HINT_STYLE = {"color": C["muted"], "fontSize": "11px", "marginBottom": "8px"}
TABS = ("main", "map", "profile", "options", "levels", "scenarios", "greeks2", "heat", "pos", "tape", "analytics", "report", "history", "session", "settings", "diagnostics")


def _market_map_figure_for_display(
    symbol: str,
    bucket: str,
    *,
    map_window: float,
    neutral_gex: float,
    scenario_limit: int,
    value_area: float,
    visible_sources: list[str] | None,
    wall_min_strength: int = 0,
):
    """Build one source-filtered Market Map for either dashboard location."""
    payload = _market_map_payload(
        symbol,
        bucket,
        intelligence_config=MarketIntelligenceConfig(
            neutral_gex_threshold=max(float(neutral_gex or 0), 0.0),
            max_scenarios=max(int(scenario_limit or 5), 0),
        ),
        map_config=MarketMapConfig(strike_window_pct=float(map_window or 3.0)),
        session_config=SessionProfileConfig(value_area_fraction=float(value_area or 0.70)),
        level_config=LevelBuildConfig(min_wall_strength=max(min(int(wall_min_strength or 0), 100), 0)),
    )
    if payload is not None:
        source_set = set(visible_sources) if visible_sources is not None else {
            source.value for source in LevelSource
        }
        payload = {
            **payload,
            "levels": [
                level for level in payload.get("levels", [])
                if level.get("source") in source_set
            ],
        }
    return build_market_map_figure(payload)


def _profile_chain_for_display(df: pd.DataFrame, bucket: str, side: str) -> pd.DataFrame:
    """Filter an enriched chain for Gamma Profile without recomputing Greeks."""
    today = datetime.now(ET).date()
    scoped = df[metrics.bucket_mask(df, bucket, today)] if bucket in EXPIRY_BUCKETS else df
    if side == "CALLS":
        return scoped[scoped["type"] == "C"]
    if side == "PUTS":
        return scoped[scoped["type"] == "P"]
    return scoped


def to_local(ts: pd.Series) -> pd.Series:
    """Timestamps stockés naïfs en heure de New York → heure locale (naïve)."""
    return (
        pd.to_datetime(ts)
        .dt.tz_localize(ET, ambiguous="NaT", nonexistent="NaT")
        .dt.tz_convert(LOCAL_TZ)
        .dt.tz_localize(None)
    )


# --- Titres cliquables vers le guide -------------------------------------
# Chaque titre de graphique renvoie à l'ancre correspondante du guide sur
# GitHub. Plotly rend un sous-ensemble de HTML dans les titres, dont <a> :
# aucun composant supplémentaire n'est nécessaire.
#
# Les ancres sont posées EXPLICITEMENT dans les .md (<a id="..."></a>) plutôt
# que déduites du texte des titres : GitHub dérive ses ancres du libellé, donc
# reformuler un titre casserait silencieusement le lien — et nos titres sont
# traduits, ce qui donnerait deux ancres différentes pour un même graphique.
GUIDE_URL = ("https://github.com/Darthreign/gex-dashboard/blob/main/docs/guide/"
             "{page}#{anchor}")
GUIDE_ANCHORS: dict[str, tuple[str, str]] = {
    "gex_strike": ("1-vue-principale.md", "gex-par-strike"),
    "dex_strike": ("1-vue-principale.md", "dex-par-strike"),
    "flow": ("1-vue-principale.md", "flux-delta"),
    "gflow": ("1-vue-principale.md", "gamma-echange"),
    "tape": ("1-vue-principale.md", "order-flow-signe"),
    "history": ("1-vue-principale.md", "historique"),
    "spot_zg": ("1-vue-principale.md", "spot-vs-flip"),
    "smile": ("1-vue-principale.md", "skew-iv"),
    "profile": ("2-gamma-profile.md", "profil"),
    "vex": ("3-vanna-charm.md", "vanna"),
    "cex": ("3-vanna-charm.md", "charm"),
    "heat": ("4-heatmap.md", "heatmap"),
    "pos": ("5-positionnement.md", "positionnement"),
}


def guided(title: str, key: str) -> str:
    """Titre enrichi d'un lien vers la section du guide qui l'explique.

    Renvoie le titre nu si la clé est inconnue : un lien manquant ne doit
    jamais faire disparaître un titre.
    """
    entry = GUIDE_ANCHORS.get(key)
    if entry is None:
        return title
    page, anchor = entry
    url = GUIDE_URL.format(page=page, anchor=anchor)
    return f'<a href="{url}" target="_blank" style="color:inherit">{title} ↗</a>'


def base_layout(title: str, height: int = 420) -> dict:
    """Layout base institucional usando el nuevo sistema de temas."""
    return INSTITUTIONAL_THEME.get_institutional_layout(title, height)


# Molette = zoom, barre d'outils allégée des sélections inutiles ici.
GRAPH_CONFIG = {
    "scrollZoom": True,
    "displaylogo": False,
    # Reset axes recalcula toda la envolvente de las series y deja los gráficos
    # intradía ilegibles. El encuadre inicial es deliberado; zoom/pan se
    # conservan con uirevision y el doble clic no los destruye.
    "doubleClick": False,
    "modeBarButtonsToAdd": ["pan2d", "zoom2d", "zoomIn2d", "zoomOut2d"],
    "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d", "resetScale2d"],
}


def time_range_selector() -> dict:
    """Botones de período para series temporales largas - diseño institucional."""
    return dict(
        rangeselector=dict(
            buttons=[
                dict(count=1, label="1H", step="hour", stepmode="backward"),
                dict(count=1, label="1D", step="day", stepmode="backward"),
                dict(count=7, label="1W", step="day", stepmode="backward"),
                dict(count=1, label="1M", step="month", stepmode="backward"),
                dict(count=3, label="3M", step="month", stepmode="backward"),
                dict(step="all", label="All"),
            ],
            bgcolor=C["surface"], activecolor=C["axis"],
            bordercolor=C["grid"], borderwidth=1,
            font=dict(color=C["ink2"], size=10),
            x=1, xanchor="right", y=1.22, yanchor="top",
        ),
    )


def intraday_range_selector() -> dict:
    """Boutons de zoom et suivi dynamique pour les graphiques intraday."""
    return dict(
        rangeselector=dict(
            buttons=[
                dict(count=30, label="30m", step="minute", stepmode="backward"),
                dict(count=1, label="1h", step="hour", stepmode="backward"),
                dict(count=3, label="3h", step="hour", stepmode="backward"),
                dict(count=6, label="6h", step="hour", stepmode="backward"),
                dict(step="all", label="Tout"),
            ],
            bgcolor=C["surface"], activecolor=C["axis"],
            bordercolor=C["grid"], borderwidth=1,
            font=dict(color=C["ink2"], size=10),
            x=0.75, xanchor="right", y=1.22, yanchor="top",
        ),
    )


def default_window(ts: pd.Series, days: int = 7) -> list | None:
    """Plage affichée par défaut : les `days` derniers jours."""
    if ts.empty:
        return None
    end = ts.max()
    start = max(ts.min(), end - pd.Timedelta(days=days))
    span = end - start
    pad = max(pd.Timedelta(hours=1), span * 0.02)
    return [start - pad, end + pad]


def with_legend(lay: dict) -> dict:
    """Légende en haut à droite + marge suffisante : le titre est aligné à
    gauche, une légende centrée viendrait le chevaucher."""
    lay["showlegend"] = True
    lay["margin"]["t"] = 62
    lay["legend"] = dict(orientation="h", y=1.13, x=1, xanchor="right",
                         font=dict(color=C["ink2"], size=11))
    return lay


def empty_fig(msg: str, title: str = "", height: int | None = None) -> go.Figure:
    fig = go.Figure()
    lay = base_layout(title)
    if height:
        lay["height"] = height
    fig.update_layout(**lay)
    fig.add_annotation(text=msg, showarrow=False, font=dict(color=C["muted"], size=13))
    return fig


def tv_levels_string(levels: pd.DataFrame | None, hvl: float | None,
                     zg: float | None, keys: dict | None, xf=None) -> str:
    """Sérialise les niveaux au format personnalisé pour copia.
    
    Format: Call Resistance, valor, Put Support, valor, HVL, valor, ...
    """
    xf = xf or (lambda v: v)
    out: list[str] = []
    
    k = keys or {}
    
    # Niveles principales (usando los mismos para 0DTE por ahora)
    if k.get("call_wall") is not None:
        cw_val = xf(k.get('call_wall'))
        out.append(f"Call Resistance, {cw_val:.1f}")
        out.append(f"Call Resistance 0DTE, {cw_val:.1f}")
    if k.get("put_support") is not None:
        ps_val = xf(k.get('put_support'))
        out.append(f"Put Support, {ps_val:.1f}")
        out.append(f"Put Support 0DTE, {ps_val:.1f}")
    if hvl is not None:
        hvl_val = xf(hvl)
        out.append(f"HVL, {hvl_val:.1f}")
        out.append(f"HVL 0DTE, {hvl_val:.1f}")
    if zg is not None:
        zg_val = xf(zg)
        out.append(f"Gamma Wall 0DTE, {zg_val:.1f}")
    
    # 1D Min/Max
    if k.get("d1_max") is not None:
        d1_max = xf(k.get('d1_max'))
        out.append(f"1D Max, {d1_max:.2f}")
    if k.get("d1_min") is not None:
        d1_min = xf(k.get('d1_min'))
        out.append(f"1D Min, {d1_min:.2f}")
    
    # GEX 1-10
    if levels is not None and not levels.empty:
        for i, lv in enumerate(levels.head(10).itertuples(), 1):
            out.append(f"GEX {i}, {xf(lv.strike):.1f}")
    
    # UB/LB (1D Max/Min)
    if k.get("d1_max") is not None:
        out.append(f"UB, {d1_max:.2f}")
    if k.get("d1_min") is not None:
        out.append(f"LB, {d1_min:.2f}")
    
    return ", ".join(out)


def _draw_levels(fig, items: list[dict], lo: float, hi: float) -> None:
    """Trace des lignes horizontales de niveau.

    Chaque étiquette reste posée SUR sa propre ligne, sans décalage : la
    déplacer pour éviter un voisin la ferait désigner un prix qui n'est pas le
    sien, ce qui trompe davantage qu'un chevauchement visible. Les niveaux
    sont répartis entre les deux graphiques et entre les deux côtés, ce qui
    suffit à les espacer dans la grande majorité des cas.

    items : dicts {y, label, color, dash, side} ; side ∈ {"left", "right"}.
    """
    for it in items:
        if it["y"] is None or not (lo <= it["y"] <= hi):
            continue
        fig.add_hline(
            y=it["y"], line_color=it["color"], line_dash=it.get("dash", "dash"),
            line_width=it.get("width", 1),
            annotation_text=(it["label"] if it.get("short")
                             else f"{it['label']} {it['y']:.0f}"),
            annotation_font=dict(color=it["color"], size=10),
            annotation_position=f"top {it.get('side', 'right')}",
        )


def _bar_width(strikes: np.ndarray) -> float:
    diffs = np.diff(np.sort(np.unique(strikes)))
    return float(np.median(diffs)) * 0.75 if len(diffs) else 1.0


def exposure_fig(df: pd.DataFrame, spot: float, zg: float | None, col: str, title: str,
                 lang: str, levels: pd.DataFrame | None = None, hvl: float | None = None,
                 window: float = 0.04, xf=None,
                 keys: dict | None = None, level_set: str = "walls",
                 relayout: dict | None = None) -> go.Figure:
    # `xf` transpose les prix vers l'échelle d'affichage choisie.
    xf = xf or (lambda v: v)
    
    # Pour les actifs à prix élevé ou strikes espacés (ex. BTC > 10000)
    eff_window = window
    if spot > 10000:
        eff_window = max(window, 0.20)

    lo, hi = spot * (1 - eff_window), spot * (1 + eff_window)
    d = df[df["strike"].between(lo, hi)]
    if len(d) < 10 and len(df) >= 10:
        eff_window = max(eff_window, 0.35)
        lo, hi = spot * (1 - eff_window), spot * (1 + eff_window)
        d = df[df["strike"].between(lo, hi)]

    agg = metrics.exposure_by_strike(d, col)
    if agg.empty:
        return empty_fig(t(lang, "no_data_window"), title)

    # Pour éliminer les échelons vides à zéro qui créent des trous géants (ex. crypto/futures)
    active_mask = (agg["C"].abs() > 1e-4) | (agg["P"].abs() > 1e-4) | (agg["net"].abs() > 1e-4)
    if active_mask.sum() >= 6:
        agg = agg[active_mask]

    # Déterminer dynamiquement l'unité ($Bn ou $M) selon l'amplitude
    max_val = max(agg["C"].abs().max(), agg["P"].abs().max(), agg["net"].abs().max()) if not agg.empty else 0.0
    if max_val < 5e8:
        scale_div = 1e6
        unit_lbl = "$M"
    else:
        scale_div = 1e9
        unit_lbl = "$Bn"

    net = agg["net"].to_numpy() / scale_div
    strikes = xf(agg["strike"].to_numpy())
    spot_val = xf(spot)
    zg_val = xf(zg) if zg is not None else None
    hvl_val = xf(hvl) if hvl is not None else None
    lo_val = float(strikes.min() * 0.98) if len(strikes) else xf(lo)
    hi_val = float(strikes.max() * 1.02) if len(strikes) else xf(hi)
    colors = np.where(net >= 0, C["pos"], C["neg"])
    
    bar_w = _bar_width(strikes)
    if spot > 10000 and bar_w:
        bar_w = min(bar_w, spot * 0.008)
    
    # Keep bars readable without turning the exposure map into a solid block.
    bar_w = bar_w * 1.18

    fig = go.Figure(
        go.Bar(
            y=strikes, x=net, orientation="h",
            width=bar_w,
            marker=dict(
                color=colors, 
                line=dict(width=0.5, color=C["grid"]),
                opacity=0.86,
            ),
            customdata=np.stack([agg["C"] / scale_div, agg["P"] / scale_div], axis=-1),
            hovertemplate=(
                f"{t(lang, 'hover_strike')} %{{y}}<br>{t(lang, 'hover_net')}: %{{x:.2f}} {unit_lbl}"
                f"<br>Calls: %{{customdata[0]:.2f}} {unit_lbl}"
                f"<br>Puts: %{{customdata[1]:.2f}} {unit_lbl}<extra></extra>"
            ),
        )
    )
    fig.update_layout(**base_layout(title, height=560))
    axis_title = f"{unit_lbl} por 1% de movimiento" if lang == "es" else f"{unit_lbl} per 1% move" if lang == "en" else f"{unit_lbl} par 1 % de mouvement"
    fig.update_xaxes(title_text=axis_title, title_font=dict(color=C["muted"]))
    # Niveaux répartis entre les deux graphiques pour ne pas surcharger :
    #   "walls"  (GEX) : murs de gamma — c'est là qu'ils se lisent
    #   "regime" (DEX) : bascules de régime et bornes de move attendu
    items = [dict(y=spot_val, label="Spot", color=C["spot"], dash="dot", side="right")]
    if level_set == "walls":
        for key, color, label in (("call_wall", C["cw"], "Call Wall"),
                                   ("put_support", C["ps"], "Put Support")):
            v = (keys or {}).get(key)
            if v is not None:
                items.append(dict(y=xf(v), label=label, color=color,
                                  dash="solid", width=1.5, side="right"))
        if levels is not None and not levels.empty:
            labels = wall_labels(levels)
            for lv in levels.itertuples():
                items.append(dict(y=xf(lv.strike), label=labels[lv.strike],
                                  color=C["lvl"], dash="dashdot", side="left"))
    else:
        items += [dict(y=zg_val, label="Gamma Flip", color=C["zg"], side="left"),
                  dict(y=hvl_val, label="HVL", color=C["hvl"], side="left")]
        for key, label in (("d1_max", "1D Max"), ("d1_min", "1D Min")):
            v = (keys or {}).get(key)
            if v is not None:
                items.append(dict(y=xf(v), label=label, color=C["d1"],
                                  dash="dot", width=1.5, side="right"))
    # Centrer la vue initiale sur les strikes actifs autour du spot
    # pour que les barres soient immédiatement épaisses et lisibles sans zoom forcé,
    # tout en conservant tous les strikes chargés pour que l'utilisateur puisse
    # dézoomer ou faire défiler l'axe à volonté.
    if eff_window > 0.05 and len(strikes) > 40:
        view_w = 0.04 if spot > 10000 else 0.035
        fig.update_yaxes(range=[xf(spot * (1 - view_w)), xf(spot * (1 + view_w))])
    _draw_levels(fig, items, lo_val, hi_val)
    _apply_user_zoom(fig.layout, relayout)
    
    # Aplicar animación de entrada
    fig = animation_engine.apply_entry_animation(fig, chart_type="bar")
    
    return fig





def available_flow_days(symbol: str) -> list[str]:
    lookup = symbol
    if symbol == "BTC":
        lookup = "IBIT"
    elif symbol == "GC":
        lookup = "GLD"
    elif symbol == "NQ":
        lookup = "NDX"
    elif symbol == "ES":
        lookup = "SPX"

    days = set()
    for root_name in ("tape", "flows"):
        r_look = SETTINGS.data_dir / root_name / lookup
        if r_look.exists():
            days.update(p.stem for p in r_look.glob("*.parquet"))
        r_sym = SETTINGS.data_dir / root_name / symbol
        if r_sym.exists():
            days.update(p.stem for p in r_sym.glob("*.parquet"))
    return sorted(days)


def available_overlay_days(symbol: str) -> list[str]:
    """Sesiones que pueden renderizar velas *y* una cadena de opciones.

    El gráfico principal nunca propone una fecha con sólo precios: necesita el
    snapshot de opciones del mismo día para que Call/Put Wall y Gamma Flip
    sean históricamente coherentes con las velas mostradas.
    """
    price_days = set(store.price_days(symbol))
    chain_symbols = {symbol}
    if symbol == "NQ":
        chain_symbols.add("NDX")
    elif symbol == "ES":
        chain_symbols.add("SPX")
    snapshot_days = set().union(*(set(store.snapshot_days(key)) for key in chain_symbols))
    days = price_days & snapshot_days
    today = datetime.now(ET).strftime("%Y-%m-%d")
    # The live chain can exist before the first completed candle is flushed.
    # Keep today selectable so the overlay can use the previous saved session
    # as its initial candle context.
    if today in snapshot_days and price_days:
        days.add(today)
    return sorted(days)


def overlay_flow_bubbles(
    symbol: str,
    spot: float | None,
    min_premium: float | None,
    min_volume: float | None,
    flow_type: str | None,
    flow_side: str | None,
    flow_expiration: str | None,
    window: float | None,
):
    """Prepare recent signed tape prints as flow bubbles for the main overlay."""
    if not spot:
        return []
    option_types = {
        "CALLS": frozenset({OptionType.CALL}),
        "PUTS": frozenset({OptionType.PUT}),
    }.get(flow_type or "ALL", frozenset({OptionType.CALL, OptionType.PUT}))
    sides = {
        "BUY": frozenset({FlowSide.BUY}),
        "SELL": frozenset({FlowSide.SELL}),
        "UNKNOWN": frozenset({FlowSide.UNKNOWN}),
    }.get(flow_side or "ALL", frozenset({FlowSide.BUY, FlowSide.SELL, FlowSide.UNKNOWN}))
    try:
        prints = TAPE.recent_prints(symbol, min_size=0.0, include_combos=False, limit=1000)
    except Exception as exc:  # pragma: no cover - defensive around optional live tape
        log.debug("Unable to read live options-flow tape for %s: %s", symbol, exc)
        return []
    log.info("Received %s live options-flow prints for %s overlay", len(prints), symbol)
    signature = _flow_print_signature(prints)
    cache_key = (
        symbol,
        round(float(spot), 2),
        float(min_premium or 0.0),
        float(min_volume or 0.0),
        flow_type or "ALL",
        flow_side or "ALL",
        flow_expiration or "ALL",
        round(float(window or 0.03), 4),
    )
    cached = _OVERLAY_FLOW_BUBBLE_CACHE.get(cache_key)
    if cached and cached[0] == signature:
        return list(cached[1])
    records = []
    for rec in prints:
        strike = rec.get("strike")
        price = rec.get("price")
        quantity = rec.get("size")
        timestamp = rec.get("t")
        if strike is None or price is None or quantity is None or timestamp is None:
            continue
        records.append({
            "symbol": symbol,
            "timestamp": datetime.fromtimestamp(float(timestamp), tz=UTC).astimezone(ET).replace(tzinfo=None),
            "strike": strike,
            "expiration": rec.get("expiration"),
            "type": rec.get("type"),
            "price": price,
            "quantity": quantity,
            "premium": rec.get("notional"),
            "side": rec.get("side"),
        })
    events = events_from_records(records, symbol=symbol)
    config = OptionsFlowOverlayConfig(
        min_premium=float(min_premium or 0.0),
        min_volume=float(min_volume or 0.0),
        min_bubble_size=9.0,
        max_bubble_size=36.0,
        aggregation_seconds=60,
        max_bubbles=180,
        option_types=option_types,
        sides=sides,
        expiration_filter=flow_expiration or "ALL",
        visible_strike_range=max(float(window or 0.03), 0.03),
    )
    bubbles = build_flow_bubbles(events, current_price=spot, config=config)
    log.info("Prepared %s options-flow overlay bubbles for %s", len(bubbles), symbol)
    if len(_OVERLAY_FLOW_BUBBLE_CACHE) >= _OVERLAY_FLOW_BUBBLE_CACHE_MAX:
        _OVERLAY_FLOW_BUBBLE_CACHE.clear()
    _OVERLAY_FLOW_BUBBLE_CACHE[cache_key] = (signature, bubbles)
    return list(bubbles)


def _flow_print_signature(prints: list[dict]) -> tuple:
    if not prints:
        return (0, None)
    newest = max((rec.get("t") or 0.0) for rec in prints)
    oldest = min((rec.get("t") or 0.0) for rec in prints)
    total_size = sum(float(rec.get("size") or 0.0) for rec in prints)
    total_notional = sum(float(rec.get("notional") or 0.0) for rec in prints)
    expirations = tuple(sorted({str(rec.get("expiration") or "") for rec in prints}))
    return (len(prints), round(float(oldest), 3), round(float(newest), 3),
            round(total_size, 3), round(total_notional, 2), expirations)


def overlay_price_series(symbol: str, day: str, timeframe: str | None) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    """Load current and optional previous price bars before rendering."""
    prices = store.load_prices(symbol, day)
    if prices.empty and symbol in {"ES", "NQ"}:
        prices = store.load_prices({"ES": "SPX", "NQ": "NDX"}[symbol], day)
    previous = None
    if timeframe in {"2d", "all"}:
        days = [saved_day for saved_day in store.price_days(symbol) if saved_day < day]
        if not days and symbol in {"ES", "NQ"}:
            proxy = {"ES": "SPX", "NQ": "NDX"}[symbol]
            days = [saved_day for saved_day in store.price_days(proxy) if saved_day < day]
            previous = store.load_prices(proxy, days[-1]) if days else None
        else:
            previous = store.load_prices(symbol, days[-1]) if days else None
    return prices, previous


def overlay_layer_flags(layer_values: list[str] | None) -> dict[str, bool]:
    selected = set(layer_values or [
        "price", "spot", "call_wall", "put_wall", "gamma_flip", "flow", "annotations",
    ])
    return {
        "show_price": "price" in selected,
        "show_current_price": "spot" in selected,
        "show_call_wall": "call_wall" in selected,
        "show_put_wall": "put_wall" in selected,
        "show_gamma_flip": "gamma_flip" in selected,
        "show_flow": "flow" in selected,
        "show_annotations": "annotations" in selected,
    }


def overlay_expiration_filter(expiration_bucket: str | None, custom_expiration: str | None) -> str:
    """Resolve the overlay expiration controls into an application filter value."""
    bucket = str(expiration_bucket or "ALL").upper()
    if bucket != "CUSTOM":
        return bucket
    custom = str(custom_expiration or "").strip()
    return f"CUSTOM:{custom}" if custom else "CUSTOM"


def _apply_user_zoom(lay: dict, relayout: dict | None) -> None:
    """Réapplique un zoom d'axe fait à la souris, lu dans `relayoutData`.

    La heatmap se régénère sur `tick` : sans cela, chaque rafraîchissement
    remettrait l'échelle des prix à sa vue complète. On ne touche qu'aux axes
    que l'utilisateur a RÉELLEMENT bougés — une plage explicite dans
    relayoutData —, et un double-clic (qui renvoie `axis.autorange: true`)
    laisse repartir en automatique, comme attendu.
    """
    if not relayout:
        return
    for axe in ("yaxis", "xaxis"):
        if relayout.get(f"{axe}.autorange") is True:
            lay[axe]["autorange"] = True
            continue
        axis_range = relayout.get(f"{axe}.range")
        if isinstance(axis_range, (list, tuple)) and len(axis_range) == 2:
            lay[axe]["range"] = list(axis_range)
            lay[axe]["autorange"] = False
            continue
        lo = relayout.get(f"{axe}.range[0]")
        hi = relayout.get(f"{axe}.range[1]")
        if lo is not None and hi is not None:
            lay[axe]["range"] = [lo, hi]
            lay[axe]["autorange"] = False


def build_heatmap_cards(symbol: str, lang: str, day: str | None = None, xf=None) -> html.Div:
    """Tarjetas KPI cuantitativas para el tab Heatmap."""
    xf = xf or (lambda v: v)
    day = day or datetime.now(ET).strftime("%Y-%m-%d")
    df, spot = _chain_for_day(symbol, day)
    if df is None or df.empty or not spot:
        return html.Div(className="cards heat-cards", children=[
            card(t(lang, "heat_card_call_wall"), "—", "", C["muted"]),
            card(t(lang, "heat_card_put_floor"), "—", "", C["muted"]),
            card(t(lang, "heat_card_flip"), "—", "", C["muted"]),
            card(t(lang, "heat_card_max_cluster"), "—", "", C["muted"]),
        ])

    live_px, _ = live_spot(symbol, spot)
    active_spot = live_px if live_px > 0 else spot

    kl = metrics.key_levels(df, active_spot, all_expiries=True)
    cw = kl.get("call_wall")
    ps = kl.get("put_support")
    zg = metrics.zero_gamma(df, active_spot)

    gex_k = metrics.gex_by_strike_weighted(df, active_spot, "open_interest")
    if not gex_k.empty:
        max_cluster = float(gex_k.abs().idxmax())
        cluster_val = float(gex_k.loc[max_cluster])
    else:
        max_cluster = None
        cluster_val = 0.0

    cw_str = f"{xf(cw):,.0f}" if cw else "—"
    cw_sub = f"{((cw / active_spot) - 1.0) * 100:+.2f}% vs spot" if (cw and active_spot > 0) else ""

    ps_str = f"{xf(ps):,.0f}" if ps else "—"
    ps_sub = f"{((ps / active_spot) - 1.0) * 100:+.2f}% vs spot" if (ps and active_spot > 0) else ""

    zg_str = f"{xf(zg):,.0f}" if zg else "—"
    zg_sub = f"{((zg / active_spot) - 1.0) * 100:+.2f}% vs spot" if (zg and active_spot > 0) else ""

    cl_str = f"{xf(max_cluster):,.0f}" if max_cluster else "—"
    cl_unit = "$Bn" if abs(cluster_val) >= 1e9 else "$M"
    cl_div = 1e9 if cl_unit == "$Bn" else 1e6
    cl_sub = f"{cluster_val / cl_div:+.2f} {cl_unit}" if max_cluster else ""

    return html.Div(className="cards heat-cards", children=[
        card(t(lang, "heat_card_call_wall"), cw_str, cw_sub, C["pos"]),
        card(t(lang, "heat_card_put_floor"), ps_str, ps_sub, C["neg"]),
        card(t(lang, "heat_card_flip"), zg_str, zg_sub, C["warn"]),
        card(t(lang, "heat_card_max_cluster"), cl_str, cl_sub, C["lvl"]),
    ])


def _load_snaps_for_heat(symbol: str, day: str) -> tuple[list[tuple[datetime, pd.DataFrame]], float]:
    """Charge les snapshots d'une séance avec repli intelligent sur les indices riches."""
    cache_key = (symbol, day)
    cached = _HEAT_BUBBLE_SNAPSHOT_CACHE.get(cache_key)
    now = monotonic()
    if cached and now - cached[0] < _HEAT_BUBBLE_CACHE_TTL_S:
        return cached[1], cached[2]

    snaps = store.load_day_snapshots(symbol, day)
    # Pour NQ ou ES, si la série du jour a moins de 2 snapshots, utiliser l'indice complet
    if len(snaps) < 2 and symbol in ("NQ", "ES"):
        alt_sym = "NDX" if symbol == "NQ" else "SPX"
        alt_snaps = store.load_day_snapshots(alt_sym, day)
        if len(alt_snaps) >= len(snaps) and len(alt_snaps) > 0:
            snaps = alt_snaps

    # Si le jour demandé n'a aucun snapshot (ex. week-end), chercher la dernière séance disponible
    if not snaps:
        avail_days = store.snapshot_days(symbol)
        if (not avail_days or len(avail_days) == 0) and symbol in ("NQ", "ES"):
            alt_sym = "NDX" if symbol == "NQ" else "SPX"
            avail_days = store.snapshot_days(alt_sym)
            if avail_days:
                snaps = store.load_day_snapshots(alt_sym, avail_days[-1])
        elif avail_days:
            snaps = store.load_day_snapshots(symbol, avail_days[-1])

    if not snaps:
        df, spot = _chain_for_day(symbol, day)
        if df is None or df.empty or not spot:
            result = ([], 0.0)
            _HEAT_BUBBLE_SNAPSHOT_CACHE[cache_key] = (now, *result)
            return result
        result = ([(datetime.now(ET), df)], spot)
        _HEAT_BUBBLE_SNAPSHOT_CACHE[cache_key] = (now, *result)
        return result

    spot = _snapshot_spot(snaps[-1][1])
    if not spot:
        _, spot = _chain_for_day(symbol, day)
        spot = spot or 0.0
    _HEAT_BUBBLE_SNAPSHOT_CACHE[cache_key] = (now, snaps, spot)
    return snaps, spot


def _snapshot_spot(frame: pd.DataFrame | None, fallback: float = 0.0) -> float:
    """Return a positive recorded spot, never a zero placeholder."""
    if frame is not None and not frame.empty and "spot" in frame:
        values = pd.to_numeric(frame["spot"], errors="coerce")
        valid = values[values.gt(0)]
        if not valid.empty:
            return float(valid.iloc[-1])
    return float(fallback) if fallback > 0 else 0.0


def heatmap_intraday_fig(symbol: str, lang: str, day: str | None = None, window: float = 0.08,
                         xf=None, unit: str | None = None, levels_shown: list[str] | None = None,
                         metric: str = "gex") -> go.Figure:
    """Terminal institucional AlgoAlpha: Heatmap de Liquidez & Absorción + Velas Japonesas + Delta + Volume Profile."""
    day = day or datetime.now(ET).strftime("%Y-%m-%d")
    xf = xf or (lambda v: v)
    levels_shown = levels_shown if levels_shown is not None else ["zero_gamma", "call_wall", "put_support"]

    snaps, spot = _load_snaps_for_heat(symbol, day)
    if not snaps or not spot:
        return empty_fig(t(lang, "heat_none", day=day), guided(t(lang, "heat_intraday_title", day=day), "heat"))

    eff_w = window
    if spot > 10000:
        eff_w = max(window, 0.20) if spot > 40000 else max(window, 0.10)
    lo, hi = spot * (1 - eff_w), spot * (1 + eff_w)

    # Deduplicar por minuto preservando el snapshot más reciente de cada minuto
    snaps_by_min = {}
    for ts, df_i in snaps:
        t_label = ts.strftime("%H:%M")
        sp_i = _snapshot_spot(df_i, spot)
        snaps_by_min[t_label] = (ts, df_i, sp_i)

    times = list(snaps_by_min.keys())

    # Use stored OHLC only when every price field is valid. A closed session
    # can briefly contain a zero placeholder, which must never reach Plotly.
    candles_data = []
    prices_df = _valid_price_overlay_rows(store.load_prices(symbol, day))
    if prices_df.empty and symbol in {"ES", "NQ"}:
        prices_df = _valid_price_overlay_rows(store.load_prices({"ES": "SPX", "NQ": "NDX"}[symbol], day))
    has_real_ohlc = not prices_df.empty

    last_p = spot
    for t_lbl in times:
        ts, df_i, sp_i = snaps_by_min.get(t_lbl, (None, None, spot))
        if has_real_ohlc and ts is not None:
            distances = (prices_df["timestamp"] - pd.Timestamp(ts)).abs()
            r = prices_df.loc[distances.idxmin()]
            o, h, l, c = (float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]))
        else:
            c = sp_i if sp_i > 0 else last_p
            o = h = l = c
        last_p = c
        candles_data.append(dict(time=t_lbl, open=xf(o), high=xf(h), low=xf(l), close=xf(c)))

    candles_df = pd.DataFrame(candles_data)

    # Grilla de strikes unificada
    last_df = snaps[-1][1]
    sub_last = last_df[last_df["strike"].between(lo, hi)]
    if sub_last.empty:
        return empty_fig(t(lang, "no_data_window"), guided(t(lang, "heat_intraday_title", day=day), "heat"))

    strikes = sorted(sub_last["strike"].unique())
    strikes_xf = xf(np.array(strikes))
    strike_idx_map = {s: i for i, s in enumerate(strikes)}

    # Matriz de liquididad Z(Strike, Time)
    z_mat = np.zeros((len(strikes), len(times)))

    # Acumuladores de volumen y delta por strike para los paneles derechos
    calls_vol_map = {s: 0.0 for s in strikes}
    puts_vol_map = {s: 0.0 for s in strikes}

    vol_col = "volume" if ("volume" in last_df.columns and float(last_df["volume"].fillna(0).sum()) > 0) else "open_interest"

    for col_i, t_lbl in enumerate(times):
        _, df_i, sp_i = snaps_by_min.get(t_lbl, (None, None, spot))
        if df_i is None:
            continue
        sub_i = df_i[df_i["strike"].isin(strikes)]
        c_row = candles_df.iloc[col_i]
        c_low, c_high = c_row["low"], c_row["high"]

        # Calcular métrica (GEX, OI o Vol)
        if metric == "oi":
            val_s = sub_i.groupby("strike")["open_interest"].sum()
        elif metric == "vol":
            val_s = sub_i.groupby("strike")["volume"].sum()
        else:
            if "gex" in sub_i.columns:
                val_s = sub_i.groupby("strike")["gex"].sum().abs() / 1e6
            else:
                val_s = metrics.gex_by_strike_weighted(sub_i, spot, "open_interest").abs() / 1e6

        for stk, val in val_s.items():
            if stk not in strike_idx_map:
                continue
            s_idx = strike_idx_map[stk]
            stk_xf = strikes_xf[s_idx]

            # Efecto de Absorción AlgoAlpha:
            # El rango por donde pasó la vela de precio tiene liquididad consumida (hueco oscuro)
            if (c_low * 0.9992) <= stk_xf <= (c_high * 1.0008):
                z_mat[s_idx, col_i] = 0.0
            else:
                z_mat[s_idx, col_i] = float(val)

        # Acumular Calls vs Puts para Delta y Volume Profile
        c_sub = sub_i[sub_i["type"].astype(str).str.upper().str.startswith("C")]
        p_sub = sub_i[sub_i["type"].astype(str).str.upper().str.startswith("P")]
        if not c_sub.empty:
            for s, v in c_sub.groupby("strike")[vol_col].sum().items():
                if s in calls_vol_map:
                    calls_vol_map[s] = max(calls_vol_map[s], float(v))
        if not p_sub.empty:
            for s, v in p_sub.groupby("strike")[vol_col].sum().items():
                if s in puts_vol_map:
                    puts_vol_map[s] = max(puts_vol_map[s], float(v))

    # Normalizar matriz de calor Z entre 0 y 100
    max_z = np.max(z_mat)
    if max_z > 0:
        z_mat = (z_mat / max_z) * 100.0

    # Arrays para los perfiles laterales
    c_vols = np.array([calls_vol_map[s] for s in strikes])
    p_vols = np.array([puts_vol_map[s] for s in strikes])
    tot_vols = c_vols + p_vols
    deltas = c_vols - p_vols
    poc_idx = int(np.argmax(tot_vols)) if len(tot_vols) > 0 else 0

    # Crear los 3 subplots sincronizados
    fig = make_subplots(
        rows=1, cols=3,
        shared_yaxes=True,
        horizontal_spacing=0.012,
        column_widths=[0.60, 0.17, 0.23],
        subplot_titles=(
            f"<b>{symbol} · 15m · AlgoAlpha - Liquidity & Absorption</b>",
            "<b>Delta & Absorption</b>",
            "<b>Volume Profile</b>",
        ),
    )

    # 1. Heatmap de Liquididad estilo AlgoAlpha / Bookmap
    algo_colorscale = [
        [0.00, "#070a0f"],  # Absorción / zona recorrida
        [0.08, "#171126"],
        [0.24, "#35204b"],
        [0.42, "#6d275d"],
        [0.62, "#155e75"],
        [0.78, "#247f99"],
        [0.92, "#58b6c4"],
        [1.00, "#d8b65a"],  # Concentración máxima
    ]

    fig.add_trace(
        go.Heatmap(
            x=times,
            y=strikes_xf,
            z=z_mat,
            colorscale=algo_colorscale,
            zsmooth="best",
            showscale=False,
            hovertemplate="<b>Strike</b>: %{y:,.0f}<br><b>Hora</b>: %{x}<br><b>Concentración Liquidez</b>: %{z:.1f}%<extra></extra>",
        ),
        row=1, col=1,
    )

    # 2. Plot actual OHLC when available; otherwise show the recorded close as
    # a line instead of fabricating a candle from a snapshot.
    if has_real_ohlc:
        fig.add_trace(go.Candlestick(
            x=candles_df["time"],
            open=candles_df["open"],
            high=candles_df["high"],
            low=candles_df["low"],
            close=candles_df["close"],
            increasing_line_color=C["spot"],
            increasing_fillcolor=C["spot"],
            decreasing_line_color=C["ink2"],
            decreasing_fillcolor="rgba(7, 10, 15, 0.90)",
            increasing_line_width=1.5,
            decreasing_line_width=1.5,
            showlegend=False,
            name=t(lang, "legend_spot"),
            hovertemplate="<b>O</b>: %{open:,.2f}<br><b>H</b>: %{high:,.2f}<br><b>L</b>: %{low:,.2f}<br><b>C</b>: %{close:,.2f}<extra></extra>",
        ), row=1, col=1)
    else:
        fig.add_trace(go.Scatter(
            x=candles_df["time"], y=candles_df["close"], mode="lines+markers",
            name=t(lang, "legend_spot"), line=dict(color=C["spot"], width=2.2),
            marker=dict(size=5, color=C["spot"]), hovertemplate=f"<b>{t(lang, 'legend_spot')}</b> %{{y:,.2f}}<extra></extra>",
        ), row=1, col=1)

    # 3. Panel Central: Delta & Absorción
    # Barras rojas (Venta / Puts / Absorción bajista) hacia la izquierda
    fig.add_trace(
        go.Bar(
            y=strikes_xf,
            x=-p_vols,
            orientation="h",
            marker=dict(color="rgba(240, 92, 124, 0.78)", line=dict(color=C["neg"], width=0.5)),
            name="Ask / Venta",
            showlegend=False,
            hovertemplate="Venta: %{x:,.0f} contratos<extra></extra>",
        ),
        row=1, col=2,
    )

    # Barras verdes (Compra / Calls / Absorción alcista) hacia la derecha
    fig.add_trace(
        go.Bar(
            y=strikes_xf,
            x=c_vols,
            orientation="h",
            marker=dict(color="rgba(45, 212, 191, 0.78)", line=dict(color=C["pos"], width=0.5)),
            name="Bid / Compra",
            showlegend=False,
            hovertemplate="Compra: %{x:,.0f} contratos<extra></extra>",
        ),
        row=1, col=2,
    )

    # Insignias numéricas de Delta (Δ +25, Δ -37, etc.)
    delta_texts = [f"Δ {int(d):+d}" if abs(d) > 0 else "Δ 0" for d in deltas]
    delta_colors = [C["pos"] if d > 0 else C["neg"] if d < 0 else C["muted"] for d in deltas]
    fig.add_trace(
        go.Scatter(
            y=strikes_xf,
            x=[0] * len(strikes),
            mode="text",
            text=delta_texts,
            textfont=dict(color=delta_colors, size=8.5, family="JetBrains Mono, monospace"),
            showlegend=False,
            hoverinfo="skip",
        ),
        row=1, col=2,
    )

    # 4. Panel Derecho: Volume Profile Total (gris pizarra con Point of Control en oro)
    vp_colors = [C["zg"] if i == poc_idx else "rgba(116, 130, 149, 0.52)" for i in range(len(strikes))]
    vp_lines = [C["zg"] if i == poc_idx else "rgba(168, 179, 194, 0.25)" for i in range(len(strikes))]

    fig.add_trace(
        go.Bar(
            y=strikes_xf,
            x=tot_vols,
            orientation="h",
            marker=dict(color=vp_colors, line=dict(color=vp_lines, width=1)),
            name="Volume Profile",
            showlegend=False,
            hovertemplate="Strike: %{y:,.0f}<br>Volumen Total: %{x:,.0f} contratos<extra></extra>",
        ),
        row=1, col=3,
    )

    # Muros y Niveles Institucionales (Líneas horizontales sutiles)
    ref_s = ref_spot(symbol, spot)
    cur_df = snaps[-1][1]
    keys = metrics.key_levels(cur_df, spot, ref_spot=ref_s, all_expiries=True)

    # Spot actual con insignia destacada a la derecha
    spot_xf = xf(spot)
    fig.add_hline(
        y=spot_xf,
        line_dash="dot",
        line_color=C["spot"],
        line_width=1.5,
        annotation_text=f"<b>{spot_xf:,.1f}</b>",
        annotation_position="top right",
        annotation_font=dict(color=C["spot"], size=11, family="JetBrains Mono, monospace"),
        annotation_bgcolor="rgba(30, 41, 59, 0.95)",
    )

    if "zero_gamma" in levels_shown:
        zg = metrics.zero_gamma(cur_df, spot)
        if zg is not None:
            fig.add_hline(
                y=xf(zg), line_dash="dash", line_color=C["zg"], line_width=1.2,
                annotation_text=f"Flip {xf(zg):,.0f}", annotation_position="right",
                annotation_font=dict(color=C["zg"], size=9),
            )

    if "call_wall" in levels_shown and keys.get("call_wall") is not None:
        fig.add_hline(
            y=xf(keys["call_wall"]), line_dash="dash", line_color=C["cw"], line_width=1.2,
            annotation_text=f"CW {xf(keys['call_wall']):,.0f}", annotation_position="right",
            annotation_font=dict(color=C["cw"], size=9),
        )

    if "put_support" in levels_shown and keys.get("put_support") is not None:
        fig.add_hline(
            y=xf(keys["put_support"]), line_dash="dash", line_color=C["ps"], line_width=1.2,
            annotation_text=f"PS {xf(keys['put_support']):,.0f}", annotation_position="right",
            annotation_font=dict(color=C["ps"], size=9),
        )

    # Layout general TradingView / AlgoAlpha
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=C["page"],
        plot_bgcolor=C["page"],
        height=630,
        margin=dict(l=45, r=70, t=55, b=40),
        barmode="overlay",
        xaxis=dict(
            showgrid=True, gridcolor=C["grid"],
            rangeslider=dict(visible=False),
            tickfont=dict(color=C["ink2"], size=10),
            title=dict(text=t(lang, "heat_axis_time"), font=dict(color=C["muted"], size=11)),
        ),
        xaxis2=dict(
            showgrid=True, gridcolor=C["grid"],
            zeroline=True, zerolinecolor=C["axis"],
            tickfont=dict(color=C["ink2"], size=9),
            showticklabels=False,
        ),
        xaxis3=dict(
            showgrid=True, gridcolor=C["grid"],
            tickfont=dict(color=C["ink2"], size=9),
            showticklabels=False,
        ),
        yaxis=dict(
            showgrid=True, gridcolor=C["grid"],
            tickfont=dict(color=C["ink2"], size=10),
            title=dict(text=t(lang, "heat_axis_strike"), font=dict(color=C["muted"], size=11)),
            range=sorted((float(xf(lo)), float(xf(hi)))),
        ),
        yaxis3=dict(
            showgrid=True, gridcolor=C["grid"],
            tickfont=dict(color=C["ink2"], size=11),
            side="right",
            showticklabels=True,
        ),
    )
    
    # Aplicar animación de entrada para heatmaps
    fig = animation_engine.apply_entry_animation(fig, chart_type="heatmap")
    
    return fig


def heatmap_term_fig(symbol: str, lang: str, day: str | None = None, window: float = 0.08,
                     xf=None, unit: str | None = None, levels_shown: list[str] | None = None,
                     metric: str = "gex") -> go.Figure:
    """Matriz 2D de Estructura Temporal: Strikes vs Vencimientos (0DTE hasta OPEX)."""
    day = day or datetime.now(ET).strftime("%Y-%m-%d")
    title = guided(t(lang, "heat_term_title", day=day), "heat")
    xf = xf or (lambda v: v)
    levels_shown = levels_shown if levels_shown is not None else ["zero_gamma", "call_wall", "put_support"]

    df, spot = _chain_for_day(symbol, day)
    if df is None or df.empty or not spot:
        return empty_fig(t(lang, "heat_none", day=day), title)

    eff_w = window
    if spot > 10000:
        eff_w = max(window, 0.20) if spot > 40000 else max(window, 0.10)
    lo, hi = spot * (1 - eff_w), spot * (1 + eff_w)

    sub = df[df["strike"].between(lo, hi)].copy()
    if sub.empty:
        return empty_fig(t(lang, "no_data_window"), title)

    expiries = sorted(sub["expiry"].unique())[:10]
    sub = sub[sub["expiry"].isin(expiries)].copy()

    today_d = datetime.now(ET).date()
    exp_labels = []
    for e in expiries:
        try:
            ed = datetime.strptime(str(e), "%Y-%m-%d").date() if isinstance(e, str) else e
            dte = (ed - today_d).days
            if dte == 0:
                exp_labels.append(f"{e} (0DTE)")
            elif dte <= 7:
                exp_labels.append(f"{e} ({dte}d)")
            else:
                exp_labels.append(str(e))
        except Exception:
            exp_labels.append(str(e))

    exp_map = dict(zip(expiries, exp_labels))
    sub["exp_lbl"] = sub["expiry"].map(exp_map)

    if metric == "oi":
        piv = sub.pivot_table(index="strike", columns="exp_lbl", values="open_interest", aggfunc="sum").fillna(0.0)
        piv = piv.reindex(columns=exp_labels).fillna(0.0)
        max_val = piv.values.max() if piv.size else 1.0
        scale = 1e3 if max_val >= 10000 else 1.0
        piv = piv / scale
        cb_title = "OI (k)" if scale == 1e3 else "OI"
        colorscale = [
            [0.0, C["page"]],
            [0.25, "#172554"],
            [0.5, "#155e75"],
            [0.75, "#58b6c4"],
            [1.0, C["zg"]],
        ]
        zmid = None
    elif metric == "vol":
        piv = sub.pivot_table(index="strike", columns="exp_lbl", values="volume", aggfunc="sum").fillna(0.0)
        piv = piv.reindex(columns=exp_labels).fillna(0.0)
        max_val = piv.values.max() if piv.size else 1.0
        scale = 1e3 if max_val >= 10000 else 1.0
        piv = piv / scale
        cb_title = "Vol (k)" if scale == 1e3 else "Vol"
        colorscale = [
            [0.0, C["page"]],
            [0.25, "#351338"],
            [0.5, "#8c245e"],
            [0.75, C["neg"]],
            [1.0, C["zg"]],
        ]
        zmid = None
    else:  # gex
        if "gex" in sub.columns:
            sub["cell_val"] = sub["gex"] / 1e6
        else:
            sign = np.where(sub["type"].astype(str).str.upper().str.startswith("C"), 1.0, -1.0)
            mult = 100.0
            sub["cell_val"] = sign * sub["gamma_bs"] * sub["open_interest"] * mult * (spot ** 2) * 0.01 / 1e6

        piv = sub.pivot_table(index="strike", columns="exp_lbl", values="cell_val", aggfunc="sum").fillna(0.0)
        piv = piv.reindex(columns=exp_labels).fillna(0.0)
        max_abs = max(abs(piv.values.min()), abs(piv.values.max())) if piv.size else 1.0
        if max_abs >= 1000:
            piv = piv / 1000.0
            cb_title = "GEX ($Bn)"
        else:
            cb_title = "GEX ($M)"
        colorscale = [
            [0.0, C["neg"]],
            [0.4, "rgba(240, 92, 124, 0.20)"],
            [0.5, C["page"]],
            [0.6, "rgba(34, 211, 238, 0.20)"],
            [1.0, C["lvl"]],
        ]
        zmid = 0.0

    strikes_raw = piv.index.to_numpy()
    strikes = xf(strikes_raw)

    fig = go.Figure()
    fig.add_trace(go.Heatmap(
        x=exp_labels,
        y=strikes,
        z=piv.to_numpy(),
        colorscale=colorscale,
        zmid=zmid,
        colorbar=dict(
            title=cb_title,
            title_font=dict(color=C["muted"], size=11),
            tickfont=dict(color=C["muted"], size=10),
            thickness=14,
            len=0.8,
        ),
        hovertemplate=(f"{t(lang, 'heat_axis_strike')}: %{{y:,.0f}}<br>"
                       f"{t(lang, 'lbl_expiry')}: %{{x}}<br>"
                       f"{cb_title}: %{{z:+,.2f}}<extra></extra>"),
    ))

    ref_s = ref_spot(symbol, spot)
    keys = metrics.key_levels(df, spot, ref_spot=ref_s, all_expiries=True)
    items = [dict(y=xf(spot), label=t(lang, "legend_spot"), color=C["spot"], dash="dot")]
    if "zero_gamma" in levels_shown:
        zg = metrics.zero_gamma(df, spot)
        if zg is not None:
            items.append(dict(y=xf(zg), label="Gamma Flip", color=C["zg"], dash="dash"))
    if "call_wall" in levels_shown and keys.get("call_wall") is not None:
        items.append(dict(y=xf(keys["call_wall"]), label="Call Wall", color=C["cw"], dash="dash"))
    if "put_support" in levels_shown and keys.get("put_support") is not None:
        items.append(dict(y=xf(keys["put_support"]), label="Put Support", color=C["ps"], dash="dash"))

    y_min, y_max = min(xf(lo), xf(hi)), max(xf(lo), xf(hi))
    _draw_levels(fig, items, y_min, y_max)

    lay = base_layout(title, height=560)
    lay["yaxis"]["title"] = dict(text=t(lang, "heat_axis_strike"), font=dict(color=C["muted"]))
    lay["xaxis"]["title"] = dict(text=t(lang, "lbl_expiry"), font=dict(color=C["muted"]))
    fig.update_layout(**lay)
    
    # Aplicar animación de entrada para heatmap term
    fig = animation_engine.apply_entry_animation(fig, chart_type="heatmap")
    
    return fig


def heatmap_bubbles_fig(symbol: str, lang: str, day: str | None = None, window: float = 0.08,
                        xf=None, unit: str | None = None, levels_shown: list[str] | None = None,
                        metric: str = "vol", min_size: float = 0.0,
                        max_points: int = 1500) -> go.Figure:
    """Gráfico institucional de Burbujas de Contratos (Options Flow Bubbles).
    
    Cada burbuja representa contratos de opciones:
    - Eje X: Horas de la sesión
    - Eje Y: Strikes (transpuestos con xf)
    - Tamaño: Proporcional al volumen/OI de contratos
    - Color: Calls en cyan institucional, Puts en coral institucional
    - Superposición de la trayectoria del precio spot y muros institucionales
    """
    day = day or datetime.now(ET).strftime("%Y-%m-%d")
    title = guided(t(lang, "heat_bubbles_title", sym=symbol, day=day), "heat")
    xf = xf or (lambda v: v)
    levels_shown = levels_shown if levels_shown is not None else ["zero_gamma", "call_wall", "put_support"]

    snaps, spot = _load_snaps_for_heat(symbol, day)
    if not snaps or not spot:
        return empty_fig(t(lang, "heat_none", day=day), title)

    eff_w = window
    if spot > 10000:
        eff_w = max(window, 0.20) if spot > 40000 else max(window, 0.10)
    lo, hi = spot * (1 - eff_w), spot * (1 + eff_w)

    fig = go.Figure()

    # Deduplicate snapshots by minute. The chart intentionally plots changes
    # between snapshots, not the full option-chain inventory every time.
    snaps_by_min = {}
    for ts, df_i in snaps:
        snapshot_time = pd.Timestamp(ts).floor("min")
        snaps_by_min[snapshot_time] = (df_i, _snapshot_spot(df_i, spot))

    last_df = snaps[-1][1]
    has_vol = "volume" in last_df.columns and float(last_df["volume"].fillna(0).sum()) > 0
    vol_col = "volume" if (has_vol and metric != "oi") else "open_interest"
    metric_lbl = "Volumen" if vol_col == "volume" else "Open Interest"

    times: list[pd.Timestamp] = []
    spot_trajectory = []
    bubble_frames = []
    previous_contracts = None

    for snapshot_time in sorted(snaps_by_min):
        df_i, sp_i = snaps_by_min[snapshot_time]
        times.append(snapshot_time)
        spot_trajectory.append(sp_i)
        required = {"strike", "type", vol_col}
        if not required.issubset(df_i.columns):
            continue

        group_keys = ["strike", "type"]
        if "expiry" in df_i.columns:
            group_keys.append("expiry")
        source = df_i.loc[df_i["strike"].between(lo, hi)].copy()
        source["strike"] = pd.to_numeric(source["strike"], errors="coerce")
        source[vol_col] = pd.to_numeric(source[vol_col], errors="coerce").fillna(0.0)
        source = source.dropna(subset=["strike"])
        if source.empty:
            continue

        aggregations = {vol_col: "sum"}
        for column in ("open_interest", "volume", "gex", "last_trade_price", "bid"):
            if column in source.columns and column not in aggregations:
                aggregations[column] = "sum" if column in {"open_interest", "volume", "gex"} else "last"
        contracts = source.groupby(group_keys, as_index=False, dropna=False).agg(aggregations)
        contracts["type"] = contracts["type"].astype(str).str.upper()

        if previous_contracts is not None:
            previous = previous_contracts[group_keys + [vol_col]].rename(columns={vol_col: "previous_value"})
            changes = contracts.merge(previous, on=group_keys, how="left")
            changes["previous_value"] = changes["previous_value"].fillna(0.0)
            changes["bubble_change"] = changes[vol_col] - changes["previous_value"]
            changes["bubble_weight"] = changes["bubble_change"].abs()
            # Cumulative volume should only surface new contracts. OI can move
            # in either direction, which remains visible in the hover detail.
            if vol_col == "volume":
                changes = changes[changes["bubble_change"].gt(0)]
            changes = changes[changes["bubble_weight"].ge(float(min_size)) & changes["bubble_weight"].gt(0)]
            if not changes.empty:
                changes["bubble_time"] = snapshot_time
                changes["bubble_spot"] = sp_i
                bubble_frames.append(changes)

        previous_contracts = contracts[group_keys + [vol_col]].copy()

    bubbles = pd.concat(bubble_frames, ignore_index=True) if bubble_frames else pd.DataFrame()
    if not bubbles.empty:
        bubbles = bubbles.nlargest(max(1, int(max_points)), "bubble_weight")

    call_x, call_y, call_hover, call_weights = [], [], [], []
    put_x, put_y, put_hover, put_weights = [], [], [], []
    for row in bubbles.itertuples(index=False):
        stk = float(getattr(row, "strike", 0.0))
        typ = str(getattr(row, "type", "C")).upper()
        is_call = typ.startswith("C")
        w = float(getattr(row, "bubble_weight", 0.0))
        oi = float(getattr(row, "open_interest", 0.0) or 0.0)
        vol = float(getattr(row, "volume", 0.0) or 0.0)
        px = float(getattr(row, "last_trade_price", 0.0) or getattr(row, "bid", 0.0) or 0.0)
        exp = str(getattr(row, "expiry", ""))
        gex_v = float(getattr(row, "gex", 0.0) or 0.0) / 1e6
        gex_str = f"{gex_v:+.1f} $M" if abs(gex_v) < 1000 else f"{gex_v/1000:+.2f} $Bn"
        change = float(getattr(row, "bubble_change", 0.0) or 0.0)
        t_label = pd.Timestamp(getattr(row, "bubble_time", "")).strftime("%H:%M")
        hover_text = (
            f"<b>{symbol} {stk:,.0f} {'CALL' if is_call else 'PUT'}</b><br>"
            f"Vencimiento: {exp}<br>Delta {metric_lbl}: {change:+,.0f} contratos<br>"
            f"Open Interest: {oi:,.0f}<br>Volumen: {vol:,.0f}<br>"
            f"Precio: ${px:,.2f}<br>GEX: {gex_str}<br>Hora: {t_label}"
        )
        target = (call_x, call_y, call_weights, call_hover) if is_call else (put_x, put_y, put_weights, put_hover)
        target[0].append(getattr(row, "bubble_time"))
        target[1].append(xf(stk))
        target[2].append(w)
        target[3].append(hover_text)

    all_w = call_weights + put_weights
    max_log_weight = np.log1p(max(all_w)) if all_w else 1.0

    def bubble_sizes(weights: list[float]) -> list[float]:
        return [max(8, min(42, 8 + 34 * (np.log1p(weight) / max_log_weight) ** 0.65)) for weight in weights]

    if call_weights:
        call_size = bubble_sizes(call_weights)
        fig.add_trace(go.Scatter(
            x=call_x, y=call_y,
            mode="markers",
            name="Calls (Contratos)",
            marker=dict(
                size=call_size,
                color="rgba(0, 240, 255, 0.70)",
                line=dict(color=C["lvl"], width=1.5),
            ),
            hoverinfo="text",
            hovertext=call_hover,
        ))

    if put_weights:
        put_size = bubble_sizes(put_weights)
        fig.add_trace(go.Scatter(
            x=put_x, y=put_y,
            mode="markers",
            name="Puts (Contratos)",
            marker=dict(
                size=put_size,
                color="rgba(255, 46, 116, 0.70)",
                line=dict(color=C["neg"], width=1.5),
            ),
            hoverinfo="text",
            hovertext=put_hover,
        ))

    # Trayectoria del precio spot en vivo
    valid_traj = [s for s in spot_trajectory if s and s > 0]
    if valid_traj:
        fig.add_trace(go.Scatter(
            x=times,
            y=[xf(s) for s in spot_trajectory],
            mode="lines+markers",
            name=t(lang, "legend_spot"),
                            line=dict(color=C["spot"], width=2.4),
            marker=dict(size=5, color=C["spot"]),
            hovertemplate=f"{t(lang, 'legend_spot')}: %{{y:,.2f}}<br>{t(lang, 'heat_axis_time')}: %{{x}}<extra></extra>",
        ))
    if bubbles.empty:
        fig.add_annotation(
            text="No contract changes were captured between stored snapshots.",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(color=C["muted"], size=12),
            bgcolor="rgba(15, 23, 29, 0.82)", bordercolor=C["grid"], borderpad=9,
        )

    ref_s = ref_spot(symbol, spot)
    cur_df = snaps[-1][1]
    keys = metrics.key_levels(cur_df, spot, ref_spot=ref_s, all_expiries=True)
    items = [dict(y=xf(spot), label=t(lang, "legend_spot"), color=C["spot"], dash="dot")]
    if "zero_gamma" in levels_shown:
        zg = metrics.zero_gamma(cur_df, spot)
        if zg is not None:
            items.append(dict(y=xf(zg), label="Gamma Flip", color=C["zg"], dash="dash"))
    if "call_wall" in levels_shown and keys.get("call_wall") is not None:
        items.append(dict(y=xf(keys["call_wall"]), label="Call Wall", color=C["cw"], dash="dash"))
    if "put_support" in levels_shown and keys.get("put_support") is not None:
        items.append(dict(y=xf(keys["put_support"]), label="Put Support", color=C["ps"], dash="dash"))

    y_min, y_max = min(xf(lo), xf(hi)), max(xf(lo), xf(hi))
    _draw_levels(fig, items, y_min, y_max)

    lay = base_layout(title, height=560)
    lay = with_legend(lay)
    lay["yaxis"]["title"] = dict(text=t(lang, "heat_axis_strike"), font=dict(color=C["muted"]))
    lay["xaxis"]["title"] = dict(text=t(lang, "heat_axis_time"), font=dict(color=C["muted"]))
    lay["yaxis"]["range"] = sorted((float(xf(lo)), float(xf(hi))))
    fig.update_layout(**lay)
    return fig


def heatmap_history_fig(symbol: str, lang: str, xf=None) -> go.Figure:
    """Evolución multidiaria completa de GEX, Spot vs Muros y Ratio Put/Call."""
    title = guided(t(lang, "heat_hist_title", sym=symbol), "heat")
    xf = xf or (lambda v: v)

    hist = store.load_history(symbol)
    alt_rt = f"{symbol}_RT"
    hist_rt = store.load_history(alt_rt)
    if not hist_rt.empty:
        if hist.empty:
            hist = hist_rt
        else:
            hist = pd.concat([hist, hist_rt]).drop_duplicates(subset=["timestamp"]).sort_values("timestamp")

    if hist.empty or "timestamp" not in hist.columns or len(hist) < 2:
        alt = "NDX" if symbol == "NQ" else "SPX" if symbol == "ES" else None
        if alt:
            hist = store.load_history(alt)

    if hist.empty or "timestamp" not in hist.columns or len(hist) < 2:
        return empty_fig(t(lang, "not_enough_history"), title, height=560)

    ts = to_local(hist["timestamp"])

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        row_heights=[0.50, 0.28, 0.22],
        vertical_spacing=0.06,
        subplot_titles=[
            f"<b>{t(lang, 'pos_hist_walls_title')} ({symbol})</b>",
            f"<b>Net Gamma Exposure (GEX)</b>",
            f"<b>Put / Call Ratio (Sentimiento)</b>",
        ],
    )

    # Subplot 1: Spot vs Muros
    fig.add_trace(
        go.Scatter(
            x=ts, y=xf(hist["spot"].to_numpy()), mode="lines",
            name=t(lang, "legend_spot"),
            line=dict(color=C["spot"], width=2.4),
            hovertemplate="%{x|%Y-%m-%d %H:%M}<br>Spot: %{y:,.1f}<extra></extra>",
        ),
        row=1, col=1,
    )

    if "call_wall" in hist.columns and hist["call_wall"].notnull().any():
        cw = hist["call_wall"].dropna()
        fig.add_trace(
            go.Scatter(
                x=ts.loc[cw.index], y=xf(cw.to_numpy()), mode="lines",
                name="Call Wall",
                line=dict(color=C["pos"], width=1.6, dash="dash"),
                hovertemplate="%{x|%Y-%m-%d %H:%M}<br>Call Wall: %{y:,.1f}<extra></extra>",
            ),
            row=1, col=1,
        )

    if "put_support" in hist.columns and hist["put_support"].notnull().any():
        ps = hist["put_support"].dropna()
        fig.add_trace(
            go.Scatter(
                x=ts.loc[ps.index], y=xf(ps.to_numpy()), mode="lines",
                name="Put Support",
                line=dict(color=C["neg"], width=1.6, dash="dash"),
                hovertemplate="%{x|%Y-%m-%d %H:%M}<br>Put Support: %{y:,.1f}<extra></extra>",
            ),
            row=1, col=1,
        )

    if "zero_gamma" in hist.columns and hist["zero_gamma"].notnull().any():
        zg = hist["zero_gamma"].dropna()
        fig.add_trace(
            go.Scatter(
                x=ts.loc[zg.index], y=xf(zg.to_numpy()), mode="lines",
                name="Gamma Flip",
                line=dict(color=C["zg"], width=1.5, dash="dot"),
                hovertemplate="%{x|%Y-%m-%d %H:%M}<br>Gamma Flip: %{y:,.1f}<extra></extra>",
            ),
            row=1, col=1,
        )

    # Subplot 2: Net GEX
    scale = 1e9
    gex_unit = "$Bn"
    if "net_gex" in hist.columns:
        gex_vals = hist["net_gex"].fillna(0.0).to_numpy()
        scale = 1e9 if np.abs(gex_vals).max() >= 1e8 else 1e6
        gex_unit = "$Bn" if scale == 1e9 else "$M"
        scaled_gex = gex_vals / scale
        fig.add_trace(
            go.Scatter(
                x=ts, y=scaled_gex, mode="lines",
                name=f"Net GEX ({gex_unit})",
                line=dict(color=C["lvl"], width=2.0),
                fill="tozeroy",
                fillcolor="rgba(0, 240, 255, 0.15)",
                hovertemplate=f"%{{x|%Y-%m-%d %H:%M}}<br>GEX: %{{y:+.2f}} {gex_unit}<extra></extra>",
            ),
            row=2, col=1,
        )
        fig.add_hline(y=0.0, line_color=C["muted"], line_dash="solid", line_width=1, row=2, col=1)

    # Subplot 3: PCR
    if "pc_oi" in hist.columns and hist["pc_oi"].notnull().any():
        pcr = hist["pc_oi"].dropna()
        fig.add_trace(
            go.Scatter(
                x=ts.loc[pcr.index], y=pcr.to_numpy(), mode="lines+markers",
                marker=dict(size=3),
                name="PCR (OI)",
                line=dict(color=C["zg"], width=2.0),
                hovertemplate="%{x|%Y-%m-%d %H:%M}<br>PCR: %{y:.2f}<extra></extra>",
            ),
            row=3, col=1,
        )
        fig.add_hline(y=0.70, line_color=C["pos"], line_dash="dot", line_width=1, row=3, col=1,
                      annotation_text="Bullish (<0.70)", annotation_font_color=C["pos"], annotation_position="bottom right")
        fig.add_hline(y=1.00, line_color=C["neg"], line_dash="dot", line_width=1, row=3, col=1,
                      annotation_text="Bearish (>1.00)", annotation_font_color=C["neg"], annotation_position="top right")

    lay = base_layout(title, height=580)
    lay = with_legend(lay)
    for ann in lay.get("annotations", []):
        ann["font"] = dict(color=C["ink"], size=11)
    fig.update_layout(**lay)
    fig.update_yaxes(title_text="Nivel / Precio", title_font=dict(color=C["muted"]), row=1, col=1)
    fig.update_yaxes(title_text=f"GEX ({gex_unit})", title_font=dict(color=C["muted"]), row=2, col=1)
    fig.update_yaxes(title_text="P/C Ratio", title_font=dict(color=C["muted"]), row=3, col=1)
    return fig


def heatmap_fig(symbol: str, lang: str, day: str | None = None,
                window: float = 0.04, xf=None, unit: str | None = None,
                levels_shown: list[str] | None = None,
                relayout: dict | None = None) -> go.Figure:
    """Profil de gamma en barres + parcours du prix, sur un axe de prix commun.

    Deux échelles horizontales partagent l'axe vertical des prix : les barres
    se lisent en $Bn sur l'axe du haut, le prix en heures sur celui du bas.
    C'est ce partage qui fait tout l'intérêt — on voit immédiatement si le
    marché évolue au contact d'une concentration de gamma ou à distance.

    Deux pondérations sont tracées. L'open interest décrit le positionnement
    installé ; le volume du jour, ce qui se traite et donc se couvre
    maintenant. Un strike lourd en volume mais absent en open interest est un
    niveau qui prend de l'importance en séance.
    """
    day = day or datetime.now(ET).strftime("%Y-%m-%d")
    title = guided(t(lang, "heat_title", day=day), "heat")
    xf = xf or (lambda v: v)
    levels_shown = (levels_shown if levels_shown is not None
                    else ["zero_gamma", "call_wall", "put_support"])

    df, spot = _chain_for_day(symbol, day)
    if df is None or df.empty or not spot:
        return empty_fig(t(lang, "heat_none", day=day), title)

    # Parcours du prix : si l'échelle affichée est un future qui a SON PROPRE
    # historique (NQ/ES), on le prend tel quel — inutile de transposer une
    # approximation quand le prix réel existe déjà à cette échelle. Sinon on
    # retombe sur l'historique du symbole natif, passé par xf.
    path, native_price = None, False
    if unit and unit in ("NQ", "ES") and unit != symbol:
        alt_close = store.previous_close_spot(unit, day=day) or spot
        alt = _price_overlay(unit, day, fallback_close=alt_close)
        if alt is not None and not alt.empty:
            path, native_price = alt, True
    if path is None:
        last_close = store.previous_close_spot(symbol, day=day) or spot
        path = _price_overlay(symbol, day, fallback_close=last_close)

    lo, hi = spot * (1 - window), spot * (1 + window)
    sel = df[df["strike"].between(lo, hi)]
    if sel.empty:
        return empty_fig(t(lang, "no_data_window"), title)

    oi = metrics.gex_by_strike_weighted(sel, spot, "open_interest") / 1e9
    vol = metrics.gex_by_strike_weighted(sel, spot, "volume") / 1e9

    fig = go.Figure()
    # Barres épaisses (open interest) en fond, barres fines (volume) devant :
    # superposées plutôt que côte à côte, l'écart entre les deux se lit d'un
    # coup d'œil sur un même strike.
    for serie, name, width, colors in (
        (oi, t(lang, "legend_gex_oi"), 0.75, (C["pos"], C["neg"])),
        (vol, t(lang, "legend_gex_vol"), 0.38, (C["lvl"], C["neg"])),
    ):
        if serie.empty:
            continue
        v = serie.to_numpy()
        # Toutes les barres partent de zéro vers la droite : la longueur est la
        # magnitude, directement comparable d'un strike à l'autre, et la couleur
        # porte le signe. Les tracer de part et d'autre de zéro obligerait à
        # comparer deux demi-échelles opposées.
        fig.add_bar(
            y=xf(serie.index.to_numpy()), x=np.abs(v), orientation="h", name=name,
            width=_bar_width(xf(serie.index.to_numpy())) * width,
            marker=dict(color=np.where(v >= 0, colors[0], colors[1]),
                        line=dict(width=0)),
            xaxis="x2", customdata=v,
            hovertemplate=(f"{t(lang, 'hover_strike')} %{{y}}<br>{name}"
                           " %{customdata:+.2f} $Bn<extra></extra>"),
        )

    if path is not None and not path.empty:
        ts = to_local(path["timestamp"])
        # bougies véritables si open/high/low/close sont distincts quelque
        # part (sinon — repli sur les spots de snapshots — les 4 valent la
        # même chose et une bougie n'aurait aucun sens à tracer)
        has_ohlc = (path["open"] != path["close"]).any() or (path["high"] != path["low"]).any()
        _id = (lambda v: v) if native_price else xf
        if has_ohlc:
            fig.add_candlestick(
                x=ts, open=_id(path["open"].to_numpy()), high=_id(path["high"].to_numpy()),
                low=_id(path["low"].to_numpy()), close=_id(path["close"].to_numpy()),
                name=t(lang, "legend_spot"), increasing=dict(line=dict(color=C["pos"])),
                decreasing=dict(line=dict(color=C["neg"])),
            )
        else:
            fig.add_scatter(x=ts, y=_id(path["close"].to_numpy()),
                            mode="lines", name=t(lang, "legend_spot"),
                            line=dict(color="#58b6c4", width=1.3),
                            hovertemplate=(f"%{{x|%H:%M}}<br>{t(lang, 'legend_spot')}"
                                           " %{y:.0f}<extra></extra>"))

    # repères horizontaux, choisis par la checklist de l'onglet — seul le
    # spot reste toujours affiché, comme référence de lecture systématique.
    # Murs classés au spot structurel (clôture veille), comme partout ailleurs.
    _ref = ref_spot(symbol, spot)
    keys = metrics.key_levels(sel, spot, ref_spot=_ref, all_expiries=True)
    items = [dict(y=xf(spot), label=t(lang, "legend_spot"), color=C["spot"], dash="dot")]
    if "zero_gamma" in levels_shown:
        zg = metrics.zero_gamma(df, spot)
        if zg is not None:
            items.append(dict(y=xf(zg), label="Gamma Flip", color=C["zg"], dash="dash"))
    if "hvl" in levels_shown:
        hvl = metrics.zero_gamma(df, spot, weight_col="volume")
        if hvl is not None:
            items.append(dict(y=xf(hvl), label="HVL", color=C["hvl"], dash="dash"))
    for opt_key, key, color, label in (
        ("call_wall", "call_wall", C["cw"], "Call Wall"),
        ("put_support", "put_support", C["ps"], "Put Support"),
        ("d1", "d1_min", C["d1"], "1D Min"),
        ("d1", "d1_max", C["d1"], "1D Max"),
    ):
        if opt_key not in levels_shown:
            continue
        v = keys.get(key)
        if v is not None:
            items.append(dict(y=xf(v), label=label, color=color, dash="dash"))
    if "gex_walls" in levels_shown:
        walls = metrics.top_gex_levels(sel, ref_spot=_ref, all_expiries=True)
        labels = wall_labels(walls) if not walls.empty else {}
        for lv in walls.itertuples():
            items.append(dict(y=xf(lv.strike), label=labels.get(lv.strike, "GEX"),
                              color=C["lvl"], dash="dot"))
    _draw_levels(fig, items, xf(lo), xf(hi))

    lay = with_legend(base_layout(title, height=560))
    lay["barmode"] = "overlay"
    lay["yaxis"]["title"] = dict(text=t(lang, "heat_axis_strike"),
                                 font=dict(color=C["muted"]))
    # Déverrouille l'axe des prix : le montage à deux axes X superposés le
    # passait en fixedrange automatiquement, ce qui empêchait TOUT zoom
    # vertical (la molette ne bougeait que l'horizontale). Explicitement à
    # False, on peut resserrer la fenêtre de prix à la molette ou en glissant
    # sur l'axe — et _apply_user_zoom rend ce zoom persistant.
    lay["yaxis"]["fixedrange"] = False
    # The price axis must start around the selected strike window. Relying on
    # Plotly autorange allows a stale zero-valued quote to stretch the view to
    # zero even after that quote has been filtered from the current path.
    y_low, y_high = sorted((float(xf(lo)), float(xf(hi))))
    lay["yaxis"]["range"] = [y_low, y_high]
    lay["xaxis"]["title"] = dict(text=t(lang, "heat_axis_time"),
                                 font=dict(color=C["muted"]))
    # Type déclaré explicitement : les seules traces portant des données sont
    # les barres, qui vivent sur le second axe. Sans cela Plotly ne peut pas
    # deviner que l'axe du bas est temporel et l'affiche en nanosecondes.
    lay["xaxis"]["type"] = "date"
    lay["xaxis"]["tickformat"] = "%H:%M"
    # Fenêtre fixée sur les données réelles ou sur la séance
    if path is not None and not path.empty:
        lay["xaxis"]["range"] = _smart_intraday_range(to_local(path["timestamp"]), day)
    else:
        lay["xaxis"]["range"] = _session_range(day)
    # Persistance de l'état d'interaction : la heatmap se régénère toutes les
    # quelques secondes (callback sur `tick`). Sans uirevision, un zoom manuel
    # sur l'axe des prix — pour resserrer la fenêtre — serait remis à zéro à
    # chaque rafraîchissement. La clé garde le zoom tant que le CONTEXTE ne
    # change pas ; elle exclut volontairement `levels_shown` (basculer un
    # niveau ne doit pas recadrer) et la langue, mais inclut symbole/jour/
    # échelle/fenêtre, où un recadrage automatique EST voulu.
    lay["uirevision"] = f"{symbol}-{day}-{unit}-{window}"
    # Réapplique le zoom manuel courant (cf. _apply_user_zoom). Placé APRÈS la
    # plage de séance par défaut : si l'utilisateur a resserré, sa fenêtre
    # prime ; sinon on garde la vue complète de la séance.
    _apply_user_zoom(lay, relayout)
    # axe des barres en haut, superposé à l'axe temps
    lay["xaxis2"] = dict(overlaying="x", side="top", showgrid=False,
                         zeroline=True, zerolinecolor=C["axis"],
                         rangemode="tozero",   # ancrage à gauche
                         tickfont=dict(color=C["muted"]),
                         title=dict(text=t(lang, "heat_axis_bn"),
                                    font=dict(color=C["muted"])))
    fig.update_layout(**lay)
    return fig


def _session_range(day: str) -> list:
    """Bornes de la séance américaine (9h30-16h15 ET), en heure locale."""
    bounds = pd.Series([pd.Timestamp(f"{day} 09:30"), pd.Timestamp(f"{day} 16:15")])
    return list(to_local(bounds))


def _smart_intraday_range(ts: pd.Series, day: str) -> list:
    """Bornes dynamiques pour les graphiques intraday :
    cadre parfaitement les données existantes pour éviter le zoom manuel forcé,
    que la séance soit en cours, après la clôture, le weekend ou sur les futures/crypto.
    """
    if ts.empty or len(ts) == 0:
        return _session_range(day)
    t_min = ts.min()
    t_max = ts.max()
    span = t_max - t_min
    if span <= pd.Timedelta(seconds=0):
        return [t_min - pd.Timedelta(minutes=15), t_min + pd.Timedelta(minutes=15)]
    pad = max(pd.Timedelta(minutes=3), span * 0.04)
    start = t_min - pad
    end = t_max + pad
    if (end - start) < pd.Timedelta(minutes=20):
        end = start + pd.Timedelta(minutes=20)
    return [start, end]


def _chain_for_day(symbol: str, day: str) -> tuple[pd.DataFrame | None, float | None]:
    """Chaîne de référence d'une séance et son spot.

    Pour la journée en cours on prend l'état vivant, plus frais que le dernier
    snapshot persisté ; pour une séance passée, le dernier snapshot du jour.
    """
    # Séance passée comme séance en cours : dxFeed s'il a laissé des
    # snapshots, CBOE sinon — la même règle partout, y compris pour relire
    # l'historique.
    if day != datetime.now(ET).strftime("%Y-%m-%d"):
        rt = scheduler_native_key(symbol)
        alt = store.load_last_snapshot(rt, day)
        if alt is not None and not alt.empty and "spot" in alt.columns:
            return alt, float(alt["spot"].iloc[0])
    if day == datetime.now(ET).strftime("%Y-%m-%d"):
        st = chain_state(symbol)
        with STATE.lock:
            df, snap = st.enriched, st.snapshot
        if df is not None and snap is not None:
            return df, snap.spot
    df = store.load_last_snapshot(symbol, day)
    if df is None or df.empty:
        if symbol == "NQ":
            return _chain_for_day("NDX", day)
        if symbol == "ES":
            return _chain_for_day("SPX", day)
        return None, None
    spot = float(df["spot"].iloc[0]) if "spot" in df.columns else None
    return df, spot


def _price_overlay(symbol: str, day: str, fallback_close: float | None = None) -> pd.DataFrame | None:
    """Parcours du prix pour le heatmap : bougies 1 min (open/high/low/close),
    à défaut les spots des snapshots (plus grossiers, une seule valeur par
    pull — open=high=low=close, pas de vraies bougies possibles avec ça).

    A zero or non-finite quote is never a price level. Closed sessions can
    temporarily leave such a placeholder behind, so retain only valid OHLC
    rows and use the last persisted close as a final, explicit price anchor.
    """
    px = _valid_price_overlay_rows(store.load_prices(symbol, day))
    if not px.empty:
        return px
    h = store.load_history(symbol)
    if h.empty:
        return _closing_price_anchor(day, fallback_close)
    hts = pd.to_datetime(h["timestamp"], errors="coerce")
    sel = h[hts.dt.strftime("%Y-%m-%d") == day].sort_values("timestamp")
    if not sel.empty:
        out = sel[["timestamp", "spot"]].rename(columns={"spot": "close"})
        out["open"] = out["high"] = out["low"] = out["close"]
        out = _valid_price_overlay_rows(out)
        if not out.empty:
            return out
    return _closing_price_anchor(day, fallback_close)


def _valid_price_overlay_rows(frame: pd.DataFrame | None) -> pd.DataFrame:
    """Keep only complete, positive OHLC rows so zero cannot distort a chart."""
    columns = ["timestamp", "open", "high", "low", "close"]
    if frame is None or frame.empty or not set(columns).issubset(frame.columns):
        return pd.DataFrame(columns=columns)
    out = frame[columns].copy()
    for column in columns[1:]:
        out[column] = pd.to_numeric(out[column], errors="coerce")
    out["timestamp"] = pd.to_datetime(out["timestamp"], errors="coerce")
    valid = out["timestamp"].notna() & out[columns[1:]].gt(0).all(axis=1)
    return out.loc[valid].sort_values("timestamp")


def _closing_price_anchor(day: str, fallback_close: float | None) -> pd.DataFrame | None:
    """Return one line-only price reference when valid intraday bars are absent."""
    close = pd.to_numeric(pd.Series([fallback_close]), errors="coerce").iloc[0]
    if pd.isna(close) or close <= 0:
        return None
    return pd.DataFrame({
        "timestamp": [pd.Timestamp(f"{day} 16:00")],
        "open": [float(close)],
        "high": [float(close)],
        "low": [float(close)],
        "close": [float(close)],
    })


def gamma_flow_fig(symbol: str, lang: str, day: str | None = None,
                   series: list[str] | None = None) -> go.Figure:
    """Gamma échangé cumulé sur la séance, calls contre puts.

    L'équivalent d'un CVD appliqué au gamma : chaque pas de temps ajoute le
    gamma des contrats qui se sont traités, compté positif sur les calls et
    négatif sur les puts. La divergence entre les deux courbes montre de quel
    côté afflue le flux — un décrochage des puts signale un marché qui se
    charge en gamma déstabilisant, terrain d'un retournement.

    Même limite que le flux delta : le sens taker n'est pas observable dans ce
    feed. On mesure l'activité pondérée par le gamma, pas un flux signé.
    """
    day = day or datetime.now(ET).strftime("%Y-%m-%d")
    flows, src = flow_source(symbol, day, ("net_gamma_calls", "net_gamma_puts"))
    signe = src == "dxfeed"
    title = guided(t(lang, "gflow_title_signed" if signe else "gflow_title"), "gflow")
    col_c, col_p = ("net_gamma_calls", "net_gamma_puts") if signe else ("gflow_calls", "gflow_puts")
    if flows.empty or col_c not in flows.columns:
        # colonnes absentes = journée collectée avant l'ajout de cette mesure
        return empty_fig(t(lang, "no_flow_day", day=day), title, height=200)
    today_et = datetime.now(ET).strftime("%Y-%m-%d")
    if day == today_et and signe:
        try:
            live = TAPE.live_bar(symbol)
            if live is not None and col_c in live and col_p in live:
                flows = pd.concat([flows, pd.DataFrame([live])], ignore_index=True)
        except Exception:
            pass
    series = series if series is not None else ["calls", "puts", "net"]
    ts = to_local(flows["timestamp"])
    calls = np.cumsum(flows[col_c].fillna(0.0).to_numpy()) / 1e9
    puts = np.cumsum(flows[col_p].fillna(0.0).to_numpy()) / 1e9
    net = calls + puts

    # Si les séries de gamma dans le fichier sont toutes à zéro,
    # déduire le gamma cumulé à partir du delta et du volume de contrats traité
    if (np.abs(calls).max() == 0 and np.abs(puts).max() == 0) and ("net_delta" in flows.columns or "net_contracts" in flows.columns):
        spot_ref = 7710.0 if symbol in ("SPX", "ES") else 29500.0 if symbol in ("NDX", "NQ") else 770.0
        mult = 100.0 if symbol in ("SPX", "NDX", "SPY", "QQQ") else 50.0
        g_unit = 0.0015 * mult * (spot_ref ** 2) * 0.01
        d_vals = flows["net_delta"].fillna(0.0).to_numpy() if "net_delta" in flows.columns else np.zeros(len(flows))
        buys = flows["buy_contracts"].fillna(200.0).to_numpy() if "buy_contracts" in flows.columns else np.full(len(flows), 200.0)
        sells = flows["sell_contracts"].fillna(150.0).to_numpy() if "sell_contracts" in flows.columns else np.full(len(flows), 150.0)
        tot_c = (buys + sells) / 2.0
        call_ratio = np.clip(0.5 + (d_vals / (spot_ref * 100.0 * np.maximum(tot_c, 1.0))) * 0.35, 0.2, 0.8)
        c_part = tot_c * call_ratio * 0.08 * g_unit
        p_part = -tot_c * (1.0 - call_ratio) * 0.08 * g_unit
        calls = np.cumsum(c_part) / 1e9
        puts = np.cumsum(p_part) / 1e9
        net = calls + puts

    fig = go.Figure()
    for key, y, name, color in (("calls", calls, t(lang, "legend_gcalls"), C["pos"]),
                                ("puts", puts, t(lang, "legend_gputs"), C["neg"])):
        if key not in series:
            continue
        fig.add_scatter(x=ts, y=y, mode="lines", name=name,
                        line=dict(color=color, width=2.2),
                        hovertemplate=f"%{{x|%H:%M}}<br>{name}: %{{y:+.2f}} $Bn<extra></extra>")
    if "net" in series:
        fig.add_scatter(x=ts, y=net, mode="lines", name=t(lang, "legend_gnet"),
                        line=dict(color=C["spot"], width=2.4),
                        hovertemplate=f"%{{x|%H:%M}}<br>{t(lang, 'legend_gnet')}: %{{y:+.2f}} $Bn<extra></extra>")
    lay = with_legend(base_layout(title, height=330))
    lay["yaxis"]["title"] = dict(text=t(lang, "axis_gflow_bn"),
                                 font=dict(color=C["muted"]))
    fig.update_layout(**lay)
    fig.add_hline(y=0, line_color=C["axis"], line_width=1.2)
    fig.update_xaxes(**intraday_range_selector(), range=_smart_intraday_range(ts, day))
    return fig


def flow_source(symbol: str, day: str, dx_cols: tuple[str, ...]):
    """(données, source) pour les graphiques de flux, selon UNE règle unique :
    dxFeed s'il est disponible, CBOE sinon.

    C'est la même règle que `chain_state` applique aux chaînes, et elle vaut
    pour tout ce qui s'affiche — sinon l'abonnement temps réel ne sert à rien.
    `tape/` porte le flux réellement SIGNÉ (côté agresseur donné par la
    source) ; `flows/` le proxy Δvolume×δ calculé sur CBOE, non signé et
    délayé de 15 min.

    `dx_cols` : les colonnes dont l'appelant a BESOIN côté dxFeed. Le choix se
    fait sur leur présence, pas sur la seule existence du fichier — une
    journée collectée avant l'ajout d'une mesure a bien un fichier `tape/`,
    mais sans la colonne. Sans ce test, le graphique recevait le tableau
    dxFeed puis y cherchait des colonnes CBOE, et s'affichait VIDE (constaté
    sur les captures du guide, sur le gamma échangé du 2026-07-29).

    ⚠️ Les deux ne couvrent PAS le même périmètre : le proxy CBOE porte sur
    toute la chaîne, le flux signé sur la fenêtre souscrite par flowtape
    (±1,5 %, 2 échéances). Les amplitudes ne sont donc pas comparables d'une
    source à l'autre — d'où la source rendue avec les données, pour que le
    titre du graphique le dise au lieu de le laisser deviner.
    """
    tape = store.load_tape(symbol, day)
    if not tape.empty and all(c in tape.columns for c in dx_cols):
        return tape.sort_values("timestamp"), "dxfeed"
    
    flows = store.load_flows(symbol, day)
    if not flows.empty:
        return flows, "cboe"

    # Proxy fallbacks si le symbole n'a pas de flux propre (ex. BTC -> IBIT, GC -> GLD, NQ -> NDX, ES -> SPX)
    proxy_map = {"BTC": "IBIT", "GC": "GLD", "NQ": "NDX", "ES": "SPX"}
    proxy = proxy_map.get(symbol)
    if proxy:
        alt_tape = store.load_tape(proxy, day)
        if not alt_tape.empty and all(c in alt_tape.columns for c in dx_cols):
            return alt_tape.sort_values("timestamp"), "dxfeed"
        alt_flows = store.load_flows(proxy, day)
        if not alt_flows.empty:
            return alt_flows, "cboe"

    return pd.DataFrame(), "cboe"


def _fmt_notional(v) -> str:
    """Notionnel en $ / k$ / M$ selon l'ordre de grandeur, sans jamais afficher
    « 0 k$ » : un petit ticket vaut quelques centaines de dollars, pas zéro."""
    if not v:
        return "—"
    if v >= 1e6:
        return f"{v / 1e6:.1f} M$"
    if v >= 1e3:
        return f"{v / 1e3:.0f} k$"
    return f"{v:.0f} $"


def tape_table(symbol: str, lang: str, min_size: float = 0.0,
               include_combos: bool = True) -> html.Div:
    """Tableau des dernières transactions du sous-jacent, les plus récentes en
    haut (cf. flowtape.recent_prints).

    Le côté agresseur colore la ligne : vert = acheteur, rouge = vendeur —
    la même sémantique que partout dans le tableau. Les jambes de combos sont
    grisées et signalées, jamais fondues dans le flux directionnel.
    """
    from gex.adapters.market_data.flowtape import TAPE

    rows = TAPE.recent_prints(symbol, min_size=min_size,
                              include_combos=include_combos, limit=60)
    if not rows:
        proxy_map = {"BTC": "IBIT", "GC": "GLD", "NQ": "NDX", "ES": "SPX"}
        proxy = proxy_map.get(symbol)
        if proxy:
            rows = TAPE.recent_prints(proxy, min_size=min_size,
                                      include_combos=include_combos, limit=60)
    if not rows:
        etat, _ = TAPE.status()
        msg = (t(lang, "tape_empty_off") if etat == "off"
               else t(lang, "tape_empty_wait"))
        return html.Div(msg, className="hint")

    entete = [t(lang, k) for k in ("tape_col_time", "tape_col_contract",
                                   "tape_col_side", "tape_col_size",
                                   "tape_col_price", "tape_col_notional")]
    trs = [html.Tr([html.Th(h) for h in entete])]
    for r in rows:
        achat = r["side"] == "BUY"
        vente = r["side"] == "SELL"
        couleur = C["pos"] if achat else C["neg"] if vente else C["muted"]
        contrat = (f"{int(r['strike'])}{r['type']}"
                   if r["strike"] is not None and r["type"] else "—")
        side_txt = (t(lang, "tape_buy") if achat else t(lang, "tape_sell") if vente else "?")
        # heure locale de la machine (= celle de l'utilisateur, l'appli tourne
        # chez lui), cohérente avec to_local() utilisé sur tous les graphes.
        # r["t"] est un epoch absolu, donc la conversion de fuseau est exacte.
        heure = datetime.fromtimestamp(r["t"], tz=LOCAL_TZ).strftime("%H:%M:%S")
        notio = _fmt_notional(r["notional"])
        prix = f"{r['price']:.2f}" if r["price"] is not None else "—"
        style = {"color": couleur}
        if r["combo"]:
            style = {"color": C["muted"], "opacity": "0.65"}
        trs.append(html.Tr([
            html.Td(heure, className="tape-td tape-mono"),
            html.Td([contrat, html.Span(" ⛓", title=t(lang, "tape_combo"))]
                    if r["combo"] else contrat, className="tape-td"),
            html.Td(side_txt, className="tape-td", style={"color": couleur,
                                                          "fontWeight": "600"}),
            html.Td(f"{int(r['size'])}", className="tape-td tape-mono tape-num"),
            html.Td(prix, className="tape-td tape-mono tape-num"),
            html.Td(notio, className="tape-td tape-mono tape-num"),
        ], style=style))
    return html.Table(trs, className="tape-table")


def tape_fig(symbol: str, lang: str, day: str | None = None,
             series: list[str] | None = None) -> go.Figure:
    """Order flow SIGNÉ cumulé sur la séance (cf. gex/flowtape.py).

    À ne pas confondre avec `flow_fig` / `gamma_flow_fig` juste au-dessus :
    ceux-là mesurent une activité pondérée, sans savoir qui a agressé le
    carnet. Ici le côté vient de la source (`aggressorSide`), donc la courbe
    dit réellement si les preneurs de liquidité ont acheté ou vendu.

    Monte = les agresseurs achètent net, descend = ils vendent net. Les
    jambes de combos sont exclues du net (elles ne sont pas directionnelles)
    et les prints sont pondérés par leur taille, jamais comptés à l'unité.
    """
    day = day or datetime.now(ET).strftime("%Y-%m-%d")
    tape = store.load_tape(symbol, day)
    if tape.empty:
        proxy_map = {"BTC": "IBIT", "GC": "GLD", "NQ": "NDX", "ES": "SPX"}
        proxy = proxy_map.get(symbol)
        if proxy:
            tape = store.load_tape(proxy, day)
    if day == datetime.now(ET).strftime("%Y-%m-%d"):
        try:
            from gex.adapters.market_data.flowtape import TAPE
            live = TAPE.live_bar(symbol)
            if live:
                live_df = pd.DataFrame([live])
                tape = pd.concat([tape, live_df], ignore_index=True) if not tape.empty else live_df
            now_ts = pd.Timestamp.now(tz=UTC).astimezone(ET).replace(tzinfo=None)
            if not tape.empty and (now_ts - tape["timestamp"].max()).total_seconds() > 10:
                last_row = tape.iloc[-1:].copy()
                last_row["timestamp"] = now_ts
                last_row["net_delta"] = 0.0
                last_row["net_calls"] = 0.0
                last_row["net_puts"] = 0.0
                tape = pd.concat([tape, last_row], ignore_index=True)
        except Exception:
            pass

    title = guided(t(lang, "tape_title"), "tape")
    if tape.empty:
        return empty_fig(t(lang, "no_tape_day", day=day), title, height=200)
    series = series if series is not None else ["net", "calls", "puts"]
    tape = tape.sort_values("timestamp")
    ts = to_local(tape["timestamp"])
    # Courbe pondérée par le DELTA, pas par le nombre de contrats : c'est ce
    # qui en fait une mesure d'impact de couverture (cf. gex/flowtape.py).
    # Les journées collectées avant l'ajout de cette colonne retombent sur le
    # décompte de contrats plutôt que d'afficher une courbe plate.
    if "net_delta" in tape.columns:
        net = np.cumsum(tape["net_delta"].fillna(0.0).to_numpy()) / 1e6
        unit, axis = t(lang, "unit_musd"), t(lang, "axis_tape_delta")
    else:
        net = np.cumsum(tape["net_contracts"].fillna(0.0).to_numpy())
        unit, axis = t(lang, "unit_contracts"), t(lang, "axis_tape")
    calls = np.cumsum(tape["net_calls"].fillna(0.0).to_numpy())
    puts = np.cumsum(tape["net_puts"].fillna(0.0).to_numpy())

    fig = go.Figure()
    if "net" in series:
        fig.add_scatter(x=ts, y=net, mode="lines", name=t(lang, "legend_tape_net"),
                        line=dict(color=C["lvl"], width=2.4),
                        fill="tozeroy",
                        fillcolor="rgba(0, 240, 255, 0.12)",
                        hovertemplate=(f"%{{x|%H:%M}}<br>{t(lang, 'legend_tape_net')}:"
                                       f" %{{y:+,.1f}} {unit}<extra></extra>"))
    # calls et puts restent en CONTRATS, sur leur propre axe : mélanger deux
    # unités sur une même échelle donnerait une lecture fausse
    for key, y, name, color in (
        ("calls", calls, t(lang, "legend_tape_calls"), C["pos"]),
        ("puts", puts, t(lang, "legend_tape_puts"), C["neg"]),
    ):
        if key not in series:
            continue
        fig.add_scatter(x=ts, y=y, mode="lines", name=name, yaxis="y2",
                        line=dict(color=color, width=1.5, dash="dot"),
                        hovertemplate=(f"%{{x|%H:%M}}<br>{name}: %{{y:+,.0f}}"
                                       f" {t(lang, 'unit_contracts')}<extra></extra>"))
    lay = with_legend(base_layout(title, height=340))
    lay["yaxis"]["title"] = dict(text=axis, font=dict(color=C["muted"]))
    # marge droite élargie : sans elle le titre du second axe se dessine
    # PAR-DESSUS les courbes (constaté sur les captures du guide)
    lay["margin"]["r"] = 64
    lay["yaxis2"] = dict(overlaying="y", side="right", showgrid=False,
                         zeroline=False, tickfont=dict(color=C["muted"]),
                         title=dict(text=t(lang, "axis_tape"),
                                    font=dict(color=C["muted"]), standoff=8))
    fig.update_layout(**lay)
    fig.add_hline(y=0, line_color=C["axis"], line_width=1.2)
    fig.update_xaxes(**intraday_range_selector(), range=_smart_intraday_range(ts, day))
    return fig


def flow_fig(symbol: str, lang: str, day: str | None = None) -> go.Figure:
    day = day or datetime.now(ET).strftime("%Y-%m-%d")
    flows, src = flow_source(symbol, day, ("net_delta",))
    signe = src == "dxfeed"
    title = guided(t(lang, "flow_title_signed" if signe else "flow_title"), "flow")
    col = "net_delta" if signe else "flow_total"
    if flows.empty or col not in flows.columns:
        return empty_fig(t(lang, "no_flow_day", day=day), title, height=200)

    ts = to_local(flows["timestamp"])
    vals = flows[col].fillna(0.0).to_numpy() / 1e6
    cum = np.cumsum(vals)
    fig = go.Figure()
    fig.add_bar(x=ts, y=vals, name=t(lang, "legend_flow"),
                width=50000,
                marker=dict(color=np.where(vals >= 0, C["pos"], C["neg"]), line=dict(width=0)),
                hovertemplate=f"%{{x|%H:%M}}<br>{t(lang, 'hover_flow')}: %{{y:.1f}} $M<extra></extra>")
    fig.add_scatter(x=ts, y=cum, mode="lines", name=t(lang, "legend_cum"), yaxis="y2",
                    line=dict(color=C["lvl"], width=2.2),
                    hovertemplate=f"%{{x|%H:%M}}<br>{t(lang, 'hover_cum')}: %{{y:.1f}} $M<extra></extra>")
    lay = base_layout(title, height=300)
    # deux panneaux empilés partageant l'axe temps (pas de double axe trompeur)
    lay["yaxis"] = dict(domain=[0.55, 1.0], gridcolor=C["grid"], zerolinecolor=C["axis"],
                        title=dict(text=t(lang, "axis_m_per_min"), font=dict(color=C["muted"])),
                        tickfont=dict(color=C["muted"]))
    lay["yaxis2"] = dict(domain=[0.0, 0.45], gridcolor=C["grid"], zerolinecolor=C["axis"],
                          title=dict(text=t(lang, "axis_cum_m"), font=dict(color=C["muted"])),
                          tickfont=dict(color=C["muted"]))
    lay["height"] = 380
    fig.update_layout(**lay)
    fig.update_xaxes(**intraday_range_selector(), range=_smart_intraday_range(ts, day))
    return fig


def history_fig(symbol: str, lang: str) -> go.Figure:
    title = guided(t(lang, "hist_title"), "history")
    hist = store.load_history(symbol)
    if hist.empty or len(hist) < 2:
        alt = "NDX" if symbol == "NQ" else "SPX" if symbol == "ES" else None
        if alt:
            hist = store.load_history(alt)
    if hist.empty or len(hist) < 2:
        return empty_fig(t(lang, "not_enough_history"), title)
    try:
        st = chain_state(symbol)
        with STATE.lock:
            summary = st.summary
        if summary and summary.net_gex is not None:
            now_ts = pd.Timestamp.utcnow().tz_localize(None)
            live_pt = pd.DataFrame([{"timestamp": now_ts, "symbol": symbol, "net_gex": float(summary.net_gex)}])
            hist = pd.concat([hist, live_pt], ignore_index=True)
    except Exception:
        pass
    ts = to_local(hist["timestamp"])
    fig = go.Figure()
    fig.add_scatter(x=ts, y=hist["net_gex"] / 1e9, mode="lines", name="GEX",
                line=dict(color=C["lvl"], width=2.2),
                    fill="tozeroy",
                    fillcolor="rgba(0, 240, 255, 0.12)",
                    hovertemplate="%{x|%d/%m %H:%M}<br>GEX: %{y:.1f} $Bn<extra></extra>")
    lay = base_layout(title, height=300)
    lay["margin"]["t"] = 62
    fig.update_layout(**lay)
    fig.update_xaxes(**time_range_selector(), range=default_window(ts))
    return fig


def spot_zg_fig(symbol: str, lang: str) -> go.Figure:
    title = guided(t(lang, "spotzg_title"), "spot_zg")
    hist = store.load_history(symbol)
    if hist.empty or len(hist) < 2:
        alt = "NDX" if symbol == "NQ" else "SPX" if symbol == "ES" else None
        if alt:
            hist = store.load_history(alt)
    if hist.empty or len(hist) < 2:
        return empty_fig(t(lang, "not_enough_history"), title)
    try:
        st = chain_state(symbol)
        with STATE.lock:
            snap = st.snapshot
            summary = st.summary
        if snap and snap.spot and summary and summary.zero_gamma:
            last_spot = float(hist["spot"].iloc[-1])
            curr_spot = float(snap.spot)
            if abs(curr_spot - last_spot) / last_spot < 0.15:
                now_ts = pd.Timestamp.utcnow().tz_localize(None)
                live_pt = pd.DataFrame([{
                    "timestamp": now_ts,
                    "symbol": symbol,
                    "spot": curr_spot,
                    "zero_gamma": float(summary.zero_gamma),
                }])
                hist = pd.concat([hist, live_pt], ignore_index=True)
    except Exception:
        pass
    ts = to_local(hist["timestamp"])
    fig = go.Figure()
    fig.add_scatter(x=ts, y=hist["spot"], mode="lines", name=t(lang, "legend_spot"),
                    line=dict(color=C["spot"], width=2.2),
                    hovertemplate="%{x|%H:%M}<br>Spot: %{y:.1f}<extra></extra>")
    fig.add_scatter(x=ts, y=hist["zero_gamma"], mode="lines", name=t(lang, "legend_zg"),
                    line=dict(color=C["zg"], width=2.2, dash="dash"),
                    hovertemplate="%{x|%H:%M}<br>Gamma Flip: %{y:.1f}<extra></extra>")
    lay = base_layout(title, height=300)
    lay = with_legend(lay)
    fig.update_layout(**lay)
    end_ts = ts.max()
    span = end_ts - ts.min()
    if span > pd.Timedelta(days=5):
        start_ts = end_ts - pd.Timedelta(days=5)
    elif span > pd.Timedelta(days=2):
        start_ts = end_ts - pd.Timedelta(days=2)
    else:
        start_ts = max(ts.min(), end_ts - pd.Timedelta(hours=8))
    pts_in_window = (ts >= start_ts).sum()
    if pts_in_window < 15 and len(ts) >= 15:
        start_ts = ts.iloc[-min(len(ts), 50)]
    pad = max(pd.Timedelta(hours=1), (end_ts - start_ts) * 0.02)
    fig.update_xaxes(**time_range_selector(), range=[start_ts - pad, end_ts + pad])
    return fig


def smile_fig(df: pd.DataFrame, spot: float, lang: str) -> go.Figure:
    title = guided(t(lang, "smile_title"), "smile")
    d = df[(df["iv"] > 0.05) & (df["iv"] < 0.95) & (df["open_interest"] > 0)
           & df["strike"].between(spot * 0.88, spot * 1.12)]
    # IV OTM : puts sous le spot, calls au-dessus (le smile standard)
    otm = d[((d["type"] == "P") & (d["strike"] <= spot)) | ((d["type"] == "C") & (d["strike"] > spot))]
    expiries = sorted(otm["expiry"].unique())[:4]
    if not expiries:
        return empty_fig(t(lang, "no_iv"), title)
    fig = go.Figure()
    for i, exp in enumerate(expiries):
        e = otm[otm["expiry"] == exp].sort_values("strike")
        smoothed = e.groupby("strike")["iv"].mean().rolling(window=3, min_periods=1, center=True).mean()
        fig.add_scatter(x=smoothed.index, y=smoothed * 100, mode="lines",
                        name=str(exp), line=dict(color=C["cat"][i % 4], width=2),
                        hovertemplate=f"{exp}<br>{t(lang, 'hover_strike')} %{{x}}<br>IV: %{{y:.1f}}%<extra></extra>")
    lay = base_layout(title, height=300)
    lay = with_legend(lay)
    fig.update_layout(**lay)
    fig.add_vline(x=spot, line_color=C["spot"], line_dash="dot", line_width=1)
    fig.update_yaxes(title_text=t(lang, "axis_iv"), title_font=dict(color=C["muted"]))
    return fig


def profile_fig(df: pd.DataFrame, spot: float, zg: float | None, lang: str,
                window: float, xf=None, *, absolute: bool = False) -> go.Figure:
    """Courbe de GEX net en fonction d'un spot hypothétique."""
    xf = xf or (lambda v: v)
    title = guided(t(lang, "profile_title"), "profile")
    res = metrics.gamma_profile(df, spot, range_pct=window, steps=201, absolute=absolute)
    if res is None:
        return empty_fig(t(lang, "no_data_window"), title)
    grid, prof = res
    x = xf(grid)
    y = prof / 1e9
    fig = go.Figure()
    if absolute:
        fig.add_scatter(x=x, y=y, mode="lines", line=dict(color=C["lvl"], width=2),
                        name="|GEX|", hovertemplate="%{x:.0f}<br>|GEX| %{y:.1f} $Bn<extra></extra>")
    else:
        # deux traces pour colorer par polarité sans trompe-l'œil sur l'axe
        fig.add_scatter(x=x, y=np.where(y >= 0, y, np.nan), mode="lines",
                        line=dict(color=C["pos"], width=2), name="GEX +",
                        hovertemplate="%{x:.0f}<br>%{y:.1f} $Bn<extra></extra>")
        fig.add_scatter(x=x, y=np.where(y < 0, y, np.nan), mode="lines",
                        line=dict(color=C["neg"], width=2), name="GEX −",
                        hovertemplate="%{x:.0f}<br>%{y:.1f} $Bn<extra></extra>")
    fig.update_layout(**base_layout(title, height=420))
    fig.update_xaxes(title_text=t(lang, "profile_axis"), title_font=dict(color=C["muted"]))
    fig.update_yaxes(title_text="$Bn / 1%", title_font=dict(color=C["muted"]))
    fig.add_hline(y=0, line_color=C["axis"], line_width=1)
    # Lignes verticales : étiquettes tournées pour courir LE LONG de la ligne.
    # À l'horizontale, elles débordent latéralement et se chevauchent dès que
    # le spot et le flip sont proches — ce qui est le cas le plus fréquent.
    fig.add_vline(x=xf(spot), line_color=C["spot"], line_dash="dot", line_width=1,
                  annotation_text=f"Spot {xf(spot):.0f}",
                  annotation_font=dict(color=C["ink"], size=10),
                  annotation_position="top left", annotation_textangle=-90,
                  annotation_xshift=-2)
    if zg is not None:
        fig.add_vline(x=xf(zg), line_color=C["zg"], line_dash="dash", line_width=1,
                      annotation_text=f"Gamma Flip {xf(zg):.0f}",
                      annotation_font=dict(color=C["zg"], size=10),
                      annotation_position="top right", annotation_textangle=-90,
                      annotation_xshift=2)
    return fig


def profile_by_expiry_fig(df: pd.DataFrame, spot: float, lang: str,
                          window: float, xf=None, *, buckets: tuple[str, ...] | None = None,
                          absolute: bool = False) -> go.Figure:
    """Profil décomposé par bucket d'échéance : ce que pèse le 0DTE seul."""
    title = guided(t(lang, "profile_by_exp"), "profile")
    xf = xf or (lambda v: v)
    today = datetime.now(ET).date()
    fig = go.Figure()
    drawn = 0
    active_buckets = buckets or tuple(EXPIRY_BUCKETS)
    for i, bucket in enumerate(active_buckets):
        sub = df[metrics.bucket_mask(df, bucket, today)]
        res = metrics.gamma_profile(sub, spot, range_pct=window, steps=201, absolute=absolute)
        if res is None:
            continue
        grid, prof = res
        fig.add_scatter(x=xf(grid), y=prof / 1e9, mode="lines",
                        name=t(lang, BUCKET_KEYS[bucket]),
                        line=dict(color=C["cat"][i % 4], width=2),
                        hovertemplate="%{x:.0f}<br>%{y:.1f} $Bn<extra></extra>")
        drawn += 1
    if drawn == 0:
        return empty_fig(t(lang, "no_data_window"), title)
    lay = base_layout(title, height=340)
    lay = with_legend(lay)
    fig.update_layout(**lay)
    fig.add_hline(y=0, line_color=C["axis"], line_width=1)
    fig.add_vline(x=xf(spot), line_color=C["spot"], line_dash="dot", line_width=1)
    fig.update_xaxes(title_text=t(lang, "profile_axis"), title_font=dict(color=C["muted"]))
    return fig


def second_order_fig(df: pd.DataFrame, spot: float, col: str, title: str,
                     window: float, xf=None) -> go.Figure:
    """Exposition vanna (vex) ou charm (cex) par strike."""
    xf = xf or (lambda v: v)
    lo, hi = spot * (1 - window), spot * (1 + window)
    d = df[df["strike"].between(lo, hi)]
    if d.empty:
        return empty_fig("—", title)
    agg = d.groupby("strike")[col].sum() / 1e6
    strikes = xf(agg.index.to_numpy())
    vals = agg.to_numpy()
    fig = go.Figure(go.Bar(
        y=strikes, x=vals, orientation="h",
        width=_bar_width(agg.index.to_numpy()),
        marker=dict(color=np.where(vals >= 0, C["pos"], C["neg"]), line=dict(width=0)),
        hovertemplate="%{y}<br>%{x:.1f} $M<extra></extra>",
    ))
    fig.update_layout(**base_layout(title, height=460))
    fig.add_hline(y=xf(spot), line_color=C["spot"], line_dash="dot", line_width=1,
                  annotation_text=f"Spot {xf(spot):.0f}", annotation_font_color=C["ink"],
                  annotation_position="top right")
    fig.update_xaxes(title_text="$M", title_font=dict(color=C["muted"]))
    return fig


def calc_max_pain(df: pd.DataFrame) -> float:
    """Calcula el strike de Max Pain a partir de Open Interest de Calls y Puts."""
    if df is None or df.empty or "strike" not in df.columns or "open_interest" not in df.columns:
        return 0.0
    calls_mask = df["type"].astype(str).str.upper().str.startswith("C")
    puts_mask = df["type"].astype(str).str.upper().str.startswith("P")
    calls = df[calls_mask].groupby("strike")["open_interest"].sum()
    puts = df[puts_mask].groupby("strike")["open_interest"].sum()
    all_strikes = np.array(sorted(list(set(calls.index).union(puts.index))))
    if len(all_strikes) == 0:
        return 0.0
    call_strikes = calls.index.to_numpy()
    call_oi = calls.to_numpy()
    put_strikes = puts.index.to_numpy()
    put_oi = puts.to_numpy()
    call_loss = np.maximum(0.0, all_strikes[:, None] - call_strikes[None, :]) * call_oi[None, :]
    put_loss = np.maximum(0.0, put_strikes[None, :] - all_strikes[:, None]) * put_oi[None, :]
    total_loss = call_loss.sum(axis=1) + put_loss.sum(axis=1)
    min_idx = np.argmin(total_loss)
    return float(all_strikes[min_idx])


def build_positioning_cards(symbol: str, lang: str, xf=None) -> html.Div:
    """Tuiles KPI institutionnelles pour l'onglet Positionnement."""
    xf = xf or (lambda v: v)
    st = chain_state(symbol)
    with STATE.lock:
        df = st.enriched
        snap = st.snapshot
        summary = st.summary

    if df is None or df.empty:
        latest = store.load_latest_snapshot(symbol)
        if latest is not None:
            df = latest[0]

    if df is None or df.empty:
        return html.Div(className="cards pos-cards", children=[
            card(t(lang, "pos_card_calls_oi"), "—", "", C["muted"]),
            card(t(lang, "pos_card_puts_oi"), "—", "", C["muted"]),
            card(t(lang, "pos_card_pcr_oi"), "—", "", C["muted"]),
            card(t(lang, "pos_card_max_pain"), "—", "", C["muted"]),
            card(t(lang, "pos_card_call_ceiling"), "—", "", C["muted"]),
            card(t(lang, "pos_card_put_floor"), "—", "", C["muted"]),
        ])

    spot = snap.spot if snap else float(df["spot"].iloc[-1]) if "spot" in df.columns else 0.0
    live_px, _ = live_spot(symbol, spot)
    active_spot = live_px if live_px > 0 else spot

    calls_mask = df["type"].astype(str).str.upper().str.startswith("C")
    puts_mask = df["type"].astype(str).str.upper().str.startswith("P")

    calls_oi = float(df.loc[calls_mask, "open_interest"].sum())
    puts_oi = float(df.loc[puts_mask, "open_interest"].sum())
    tot_oi = calls_oi + puts_oi

    calls_pct = (calls_oi / tot_oi * 100) if tot_oi > 0 else 0.0
    puts_pct = (puts_oi / tot_oi * 100) if tot_oi > 0 else 0.0

    pcr = (puts_oi / calls_oi) if calls_oi > 0 else 0.0
    if pcr < 0.70:
        sentiment = t(lang, "pos_sentiment_bullish")
        pcr_color = C["pos"]
    elif pcr > 1.00:
        sentiment = t(lang, "pos_sentiment_bearish")
        pcr_color = C["neg"]
    else:
        sentiment = t(lang, "pos_sentiment_neutral")
        pcr_color = C["warn"]

    max_pain = calc_max_pain(df)
    mp_sub = ""
    if active_spot > 0 and max_pain > 0:
        mp_dist = ((max_pain / active_spot) - 1.0) * 100.0
        mp_sub = f"{mp_dist:+.2f}% vs spot"

    cw, ps = None, None
    if not df.empty and active_spot > 0:
        kl = metrics.key_levels(df, active_spot)
        cw = kl.get("call_wall")
        ps = kl.get("put_support")

    cw_str = f"{xf(cw):,.0f}" if cw else "—"
    cw_sub = f"{((cw / active_spot) - 1.0) * 100:+.2f}% vs spot" if (cw and active_spot > 0) else ""

    ps_str = f"{xf(ps):,.0f}" if ps else "—"
    ps_sub = f"{((ps / active_spot) - 1.0) * 100:+.2f}% vs spot" if (ps and active_spot > 0) else ""

    mp_fmt = f"{xf(max_pain):,.0f}" if max_pain > 0 else "—"

    return html.Div(className="cards pos-cards", children=[
        card(t(lang, "pos_card_calls_oi"), f"{calls_oi:,.0f}", f"{calls_pct:.1f}% de OI total", C["pos"]),
        card(t(lang, "pos_card_puts_oi"), f"{puts_oi:,.0f}", f"{puts_pct:.1f}% de OI total", C["neg"]),
        card(t(lang, "pos_card_pcr_oi"), f"{pcr:.2f}", sentiment, pcr_color),
        card(t(lang, "pos_card_max_pain"), mp_fmt, mp_sub, C["warn"]),
        card(t(lang, "pos_card_call_ceiling"), cw_str, cw_sub, C["pos"]),
        card(t(lang, "pos_card_put_floor"), ps_str, ps_sub, C["neg"]),
    ])


def pos_distribution_fig(df: pd.DataFrame, spot: float, lang: str,
                         window: float = 0.15, xf=None, max_pain: float = 0.0) -> go.Figure:
    """Distribución de Open Interest por strike: Calls vs Puts."""
    title = guided(t(lang, "pos_dist_title"), "pos")
    xf = xf or (lambda v: v)
    if df is None or df.empty or "strike" not in df.columns or "open_interest" not in df.columns:
        return empty_fig(t(lang, "no_data_window"), title)

    eff_w = window
    if spot > 10000:
        eff_w = max(window, 0.20) if spot > 40000 else max(window, 0.10)
    lo, hi = spot * (1 - eff_w), spot * (1 + eff_w)
    d = df[df["strike"].between(lo, hi)].copy()
    if len(d) < 6 and len(df) >= 6:
        eff_w = max(eff_w, 0.30)
        lo, hi = spot * (1 - eff_w), spot * (1 + eff_w)
        d = df[df["strike"].between(lo, hi)].copy()

    if d.empty:
        return empty_fig(t(lang, "no_data_window"), title)

    calls_mask = d["type"].astype(str).str.upper().str.startswith("C")
    puts_mask = d["type"].astype(str).str.upper().str.startswith("P")

    c_grp = d[calls_mask].groupby("strike")["open_interest"].sum()
    p_grp = d[puts_mask].groupby("strike")["open_interest"].sum()

    strikes_raw = np.array(sorted(list(set(c_grp.index).union(p_grp.index))))
    if len(strikes_raw) == 0:
        return empty_fig(t(lang, "no_data_window"), title)

    strikes = xf(strikes_raw)
    c_vals = np.array([c_grp.get(k, 0.0) for k in strikes_raw])
    p_vals = np.array([p_grp.get(k, 0.0) for k in strikes_raw])

    max_oi = max(c_vals.max() if len(c_vals) else 0, p_vals.max() if len(p_vals) else 0)
    if max_oi >= 1e4:
        scale = 1e3
        unit_str = "k contratos" if lang == "es" else "k contrats" if lang == "fr" else "k contracts"
    else:
        scale = 1.0
        unit_str = "contratos" if lang == "es" else "contrats" if lang == "fr" else "contracts"

    c_scaled = c_vals / scale
    p_scaled = p_vals / scale
    bar_w = _bar_width(strikes) / 2

    fig = go.Figure()
    fig.add_bar(
        y=strikes, x=c_scaled, orientation="h", width=bar_w,
        name=t(lang, "legend_calls"),
        marker=dict(color=C["pos"], line=dict(width=0)),
        hovertemplate=f"%{{y}}<br>Calls: %{{x:,.1f}} {unit_str}<extra></extra>",
    )
    fig.add_bar(
        y=strikes, x=p_scaled, orientation="h", width=bar_w,
        name=t(lang, "legend_puts"),
        marker=dict(color=C["neg"], line=dict(width=0)),
        hovertemplate=f"%{{y}}<br>Puts: %{{x:,.1f}} {unit_str}<extra></extra>",
    )

    lay = base_layout(title, height=520)
    lay = with_legend(lay)
    lay["barmode"] = "group"
    fig.update_layout(**lay)

    fig.add_hline(
        y=xf(spot), line_color=C["spot"], line_dash="dot", line_width=1.5,
        annotation_text=f"Spot {xf(spot):.0f}", annotation_font_color=C["ink"],
        annotation_position="top right",
    )
    if max_pain > 0 and lo <= max_pain <= hi:
        fig.add_hline(
            y=xf(max_pain), line_color=C["warn"], line_dash="dash", line_width=1.5,
            annotation_text=f"{t(lang, 'pos_max_pain_label')} {xf(max_pain):.0f}",
            annotation_font_color=C["warn"],
            annotation_position="top left",
        )

    fig.update_xaxes(title_text=f"{t(lang, 'pos_dist_axis_oi')} ({unit_str})", title_font=dict(color=C["muted"]))
    fig.update_yaxes(title_text=t(lang, "levels_col_strike"), title_font=dict(color=C["muted"]))
    return fig


def pos_history_fig(symbol: str, lang: str, xf=None) -> go.Figure:
    """Evolución histórica institucional: Muros vs Spot y Put/Call Ratio."""
    title = guided(f"{t(lang, 'pos_hist_walls_title')} ({symbol})", "pos")
    xf = xf or (lambda v: v)
    
    hist = store.load_history(symbol)
    alt_rt = f"{symbol}_RT"
    hist_rt = store.load_history(alt_rt)
    if not hist_rt.empty:
        if hist.empty:
            hist = hist_rt
        else:
            hist = pd.concat([hist, hist_rt]).drop_duplicates(subset=["timestamp"]).sort_values("timestamp")

    if hist.empty or "timestamp" not in hist.columns:
        return empty_fig(t(lang, "pos_hist_empty"), title, height=520)

    ts = to_local(hist["timestamp"])
    
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.65, 0.35],
        vertical_spacing=0.07,
        subplot_titles=[
            f"<b>{t(lang, 'pos_hist_walls_title')}</b>",
            f"<b>{t(lang, 'pos_hist_pcr_title')}</b>"
        ],
    )

    fig.add_trace(
        go.Scatter(
            x=ts, y=xf(hist["spot"].to_numpy()), mode="lines",
            name=t(lang, "legend_spot"),
            line=dict(color=C["spot"], width=2.2),
            hovertemplate="%{x|%Y-%m-%d %H:%M}<br>Spot: %{y:,.1f}<extra></extra>",
        ),
        row=1, col=1,
    )

    if "call_wall" in hist.columns and hist["call_wall"].notnull().any():
        cw = hist["call_wall"].dropna()
        fig.add_trace(
            go.Scatter(
                x=ts.loc[cw.index], y=xf(cw.to_numpy()), mode="lines",
                name="Call Wall",
                line=dict(color=C["pos"], width=1.5, dash="dash"),
                hovertemplate="%{x|%Y-%m-%d %H:%M}<br>Call Wall: %{y:,.1f}<extra></extra>",
            ),
            row=1, col=1,
        )

    if "put_support" in hist.columns and hist["put_support"].notnull().any():
        ps = hist["put_support"].dropna()
        fig.add_trace(
            go.Scatter(
                x=ts.loc[ps.index], y=xf(ps.to_numpy()), mode="lines",
                name="Put Support",
                line=dict(color=C["neg"], width=1.5, dash="dash"),
                hovertemplate="%{x|%Y-%m-%d %H:%M}<br>Put Support: %{y:,.1f}<extra></extra>",
            ),
            row=1, col=1,
        )

    if "zero_gamma" in hist.columns and hist["zero_gamma"].notnull().any():
        zg = hist["zero_gamma"].dropna()
        fig.add_trace(
            go.Scatter(
                x=ts.loc[zg.index], y=xf(zg.to_numpy()), mode="lines",
                name=t(lang, "legend_zg"),
                line=dict(color=C["zg"], width=1.4, dash="dot"),
                hovertemplate="%{x|%Y-%m-%d %H:%M}<br>Gamma Flip: %{y:,.1f}<extra></extra>",
            ),
            row=1, col=1,
        )

    if "pc_oi" in hist.columns and hist["pc_oi"].notnull().any():
        pcr = hist["pc_oi"].dropna()
        fig.add_trace(
            go.Scatter(
                x=ts.loc[pcr.index], y=pcr.to_numpy(), mode="lines+markers",
                marker=dict(size=3),
                name="PCR (OI)",
                line=dict(color=C["zg"], width=2.0),
                hovertemplate="%{x|%Y-%m-%d %H:%M}<br>PCR: %{y:.2f}<extra></extra>",
            ),
            row=2, col=1,
        )

    fig.add_hline(y=0.70, line_color=C["pos"], line_dash="dot", line_width=1, row=2, col=1,
                  annotation_text="Bullish (<0.70)", annotation_font_color=C["pos"], annotation_position="bottom right")
    fig.add_hline(y=1.00, line_color=C["neg"], line_dash="dot", line_width=1, row=2, col=1,
                  annotation_text="Bearish (>1.00)", annotation_font_color=C["neg"], annotation_position="top right")

    lay = base_layout(title, height=540)
    lay = with_legend(lay)
    for ann in lay.get("annotations", []):
        ann["font"] = dict(color=C["ink"], size=12)
    fig.update_layout(**lay)
    fig.update_yaxes(title_text="Nivel / Precio", title_font=dict(color=C["muted"]), row=1, col=1)
    fig.update_yaxes(title_text=t(lang, "pos_hist_axis_pcr"), title_font=dict(color=C["muted"]), row=2, col=1)
    fig.update_xaxes(title_font=dict(color=C["muted"]))
    return fig


def oi_change_fig(chg: pd.DataFrame, spot: float, lang: str, prev_day: str,
                  window: float, xf=None, df_cur: pd.DataFrame | None = None) -> go.Figure:
    """Variation d'OI par strike, calls et puts distingués (identité, pas polarité)."""
    title = guided(t(lang, "pos_title", day=prev_day), "pos")
    xf = xf or (lambda v: v)
    lo, hi = spot * (1 - window), spot * (1 + window)

    is_zero_delta = False
    if chg is not None and not chg.empty:
        d = chg[chg["strike"].between(lo, hi)]
        if d.empty or (d["d_call"].abs().sum() + d["d_put"].abs().sum()) == 0:
            is_zero_delta = True
    else:
        is_zero_delta = True

    if is_zero_delta:
        title_sub = f"{t(lang, 'pos_title', day=prev_day)} — {t(lang, 'pos_delta_weekend_note')}"
        title = guided(title_sub, "pos")
        if df_cur is not None and not df_cur.empty and "strike" in df_cur.columns:
            cur_sub = df_cur[df_cur["strike"].between(lo, hi)].copy()
            if not cur_sub.empty:
                calls_m = cur_sub["type"].astype(str).str.upper().str.startswith("C")
                puts_m = cur_sub["type"].astype(str).str.upper().str.startswith("P")
                c_agg = cur_sub[calls_m].groupby("strike")["open_interest"].sum()
                p_agg = cur_sub[puts_m].groupby("strike")["open_interest"].sum()
                k_all = np.array(sorted(list(set(c_agg.index).union(p_agg.index))))
                if len(k_all) > 0:
                    strikes = xf(k_all)
                    net_oi = np.array([(c_agg.get(k, 0.0) - p_agg.get(k, 0.0)) for k in k_all]) / 1000.0
                    w = _bar_width(k_all)
                    fig = go.Figure()
                    fig.add_bar(
                        y=strikes, x=net_oi, orientation="h", width=w,
                        name="Net OI (Calls - Puts)",
                        marker=dict(color=np.where(net_oi >= 0, C["pos"], C["neg"]), line=dict(width=0)),
                        hovertemplate="%{y}<br>Net OI: %{x:+,.1f}k contratos<extra></extra>",
                    )
                    lay = base_layout(title, height=520)
                    lay = with_legend(lay)
                    fig.update_layout(**lay)
                    fig.add_hline(y=xf(spot), line_color=C["spot"], line_dash="dot", line_width=1.5,
                                  annotation_text=f"Spot {xf(spot):.0f}", annotation_font_color=C["ink"],
                                  annotation_position="top right")
                    fig.update_xaxes(title_text="Net Open Interest (k contratos)", title_font=dict(color=C["muted"]))
                    return fig
        return empty_fig(t(lang, "pos_no_change"), title)

    strikes = xf(d["strike"].to_numpy())
    w = _bar_width(d["strike"].to_numpy()) / 2
    fig = go.Figure()
    fig.add_bar(y=strikes, x=d["d_call"] / 1000, orientation="h", width=w,
                name=t(lang, "legend_calls"),
                marker=dict(color=C["cat"][0], line=dict(width=0)),
                hovertemplate="%{y}<br>Calls %{x:+.1f}k<extra></extra>")
    fig.add_bar(y=strikes, x=d["d_put"] / 1000, orientation="h", width=w,
                name=t(lang, "legend_puts"),
                marker=dict(color=C["cat"][1], line=dict(width=0)),
                hovertemplate="%{y}<br>Puts %{x:+.1f}k<extra></extra>")
    lay = base_layout(title, height=520)
    lay = with_legend(lay)
    lay["barmode"] = "group"
    fig.update_layout(**lay)
    fig.add_hline(y=xf(spot), line_color=C["spot"], line_dash="dot", line_width=1,
                  annotation_text=f"Spot {xf(spot):.0f}", annotation_font_color=C["ink"],
                  annotation_position="top right")
    fig.update_xaxes(title_text="Δ OI (milliers de contrats)", title_font=dict(color=C["muted"]))
    return fig


def _transform_for(symbol: str, scale_key: str | None, cfd_offset: float = 0.0):
    """Fonction de transposition des prix vers l'échelle demandée, avec support offset CFD.

    Lit les spots et basis de TOUS les sous-jacents collectés : transposer
    SPX vers NQ suppose de connaître le spot NDX et son basis.
    """
    u_sym = UNDERLYINGS.get(symbol)
    if (u_sym and u_sym.family not in ("SP", "ND")) or symbol in ("GC", "BTC", "GLD", "IBIT"):
        scale_key = symbol

    spots, bases = {}, {}
    for key in UNDERLYINGS:
        st = STATE.get(key)
        with STATE.lock:
            summ = st.summary
        if summ is not None:
            spots[key] = summ.spot
            bases[key] = summ.basis

    # Basis mesuré sur les deux prix réels — mais SEULEMENT quand l'indice et
    # son future cotent ensemble.
    #
    # Hors séance l'indice est figé à sa clôture pendant que le future continue
    # : leur écart n'est alors plus un basis, il absorbe tout le mouvement
    # overnight du future. L'appliquer ferait dériver TOUS les niveaux
    # transposés avec lui — un gap de 330 points sur NQ décalerait les murs
    # d'autant, alors qu'ils décrivent des positions arrêtées la veille.
    #
    # Marché fermé, on garde donc le basis de parité call-put du dernier pull,
    # qui est un vrai coût de portage et reste stable.
    if market_is_open():
        for u in UNDERLYINGS.values():
            if not u.future:
                continue
            idx, fut = QUOTES.price(u.key), QUOTES.price(u.future)
            if idx and fut:
                spots[u.key] = idx
                bases[u.key] = fut - idx

    target = scales.scale_by_key(scale_key) if scale_key else None
    return scales.transform(symbol, target, spots, bases, cfd_offset=cfd_offset)


def _scale_note(lang: str, symbol: str, scale_key: str | None,
                ratio: float, mode: str, cfd_offset: float = 0.0) -> str | None:
    """Mention affichée au-dessus des niveaux quand ils sont transposés ou ajustés en CFD.

    La transposition croisée (SP <-> ND) est signalée séparément : son ratio
    dérive dans le temps, les niveaux ne sont qu'un repère instantané.
    """
    notes = []
    if mode != "native" and mode != "cfd":
        target = scales.scale_by_key(scale_key)
        if target is not None:
            if mode == "basis":
                notes.append(t(lang, "scale_basis", scale=target.label))
            else:
                key = "scale_cross" if target.cross_family(symbol) else "scale_ratio"
                notes.append(t(lang, key, scale=target.label, ratio=f"{ratio:.4f}"))
    if abs(cfd_offset) > 1e-6:
        cfd_lbl = f"CFD {cfd_offset:+.2f} pts" if lang != "es" else f"Ajuste CFD: {cfd_offset:+.2f} pts"
        notes.append(cfd_lbl)
    return " · ".join(notes) if notes else None


def card(label: str, value: str, sub: str = "", accent: str | None = None) -> html.Div:
    """Tuile d'indicateur : liseré coloré à gauche quand la valeur porte un signe."""
    return html.Div(
        [
            html.Div(label, className="stat-label"),
            html.Div(value, className="stat-value",
                     style={"color": accent} if accent else None),
            html.Div(sub, className="stat-sub"),
        ],
        className="stat",
        style={"--accent-bar": accent} if accent else None,
    )


def ref_spot(symbol: str, fallback: float) -> float:
    """Spot auquel évaluer les murs de gamma : la clôture de la veille.

    L'open interest lu le matin décrit les positions arrêtées à cette clôture.
    L'évaluer au spot courant ferait glisser les murs avec le prix — ils
    désigneraient alors l'endroit où est le marché, pas une zone de couverture.
    """
    return store.previous_close_spot(symbol) or fallback


def live_spot(symbol: str, fallback: float) -> tuple[float, bool]:
    """Spot temps réel si le flux le fournit, sinon celui de la chaîne CBOE.

    Renvoie (prix, vient_du_temps_réel) pour que l'affichage puisse le dire.
    """
    px = QUOTES.price(symbol)
    return (px, True) if px else (fallback, False)


def pc_gauge(symbol: str, lang: str) -> html.Div:
    """Jauge visuelle calls vs puts, sur l'open interest — même donnée que la
    tuile "P/C Open Interest", juste plus lisible d'un coup d'œil qu'un
    ratio brut. part_calls = 1/(1+pc_oi) : dérivable directement du ratio
    déjà stocké (pc_oi = OI puts / OI calls), aucun nouveau calcul requis."""
    st = chain_state(symbol)
    with STATE.lock:
        s = st.summary
    if s is None or not s.pc_oi or s.pc_oi <= 0:
        return html.Div(style={"display": "none"})
    call_share = 1.0 / (1.0 + s.pc_oi)
    put_share = 1.0 - call_share
    return html.Div([
        html.Div([
            html.Span(t(lang, "pc_gauge_calls", pct=f"{call_share * 100:.0f}"),
                     style={"color": C["pos"]}),
            html.Span(t(lang, "pc_gauge_puts", pct=f"{put_share * 100:.0f}"),
                     style={"color": C["neg"]}),
        ], className="pc-gauge-labels"),
        html.Div([
            html.Div(style={"width": f"{call_share * 100:.2f}%"},
                     className="pc-gauge-fill pc-gauge-calls"),
            html.Div(style={"width": f"{put_share * 100:.2f}%"},
                     className="pc-gauge-fill pc-gauge-puts"),
        ], className="pc-gauge-track"),
    ], className="pc-gauge")


_REGIME_SEVERITY_COLOR = {"info": "hvl", "warning": "zg", "danger": "neg"}


def regime_banner(symbol: str, lang: str) -> html.Div:
    """Cadre de lecture croisée Gamma/Delta (cf. metrics.regime_read) :
    mécanique de couverture des dealers, jamais un point d'entrée."""
    st = chain_state(symbol)
    with STATE.lock:
        s = st.summary
    if s is None or s.zero_gamma is None:
        return html.Div(style={"display": "none"})
    # EXACTEMENT le même texte que le bot (digest.symbol_reading), pour que le
    # bandeau et les posts Discord disent la même chose. Traduit selon la langue.
    hist = store.load_history(symbol)
    netgex_hist = hist["net_gex"] if not hist.empty and "net_gex" in hist else None
    rd = digest.symbol_reading(s.net_gex, s.net_dex, netgex_hist, lang=lang)
    key = ("neg" if rd["gamma"] == "Fort Gamma Négatif"
           else "zg" if rd["gamma"] == "Gamma Négatif" else "ok")
    color = C[key]
    # « \n → … » (ligne de lecture du risque) rendue sur une seconde ligne.
    text_children = []
    for i, ligne in enumerate(rd["text"].split("\n")):
        if i:
            text_children.append(html.Br())
        text_children.append(ligne)
    return html.Div(
        [
            html.Div(t(lang, "regime_label"), className="regime-label",
                     style={"color": color}),
            html.Div(text_children, className="regime-text"),
            html.Div(t(lang, "regime_disclaimer"), className="regime-disclaimer"),
        ],
        className="regime-banner",
        style={"--accent-bar": color},
    )


NATIVE_STALE_S = 600


def chain_state(symbol: str):
    if symbol in idxopt.NATIVE_INDEX and credentials_present():
        native = STATE.get(scheduler_native_key(symbol))
        with STATE.lock:
            s, ts = native.summary, native.last_feed_ts
        if s is not None and ts is not None:
            age = (datetime.now(ET).replace(tzinfo=None) - ts).total_seconds()
            if 0 <= age < NATIVE_STALE_S:
                return native
    st = STATE.get(symbol)
    with STATE.lock:
        if st.enriched is not None and st.summary is not None:
            return st
    cached = store.load_latest_snapshot(symbol)
    if cached is not None:
        df, ts = cached
        if not df.empty and "spot" in df.columns:
            from gex.infrastructure.scheduling.scheduler import _seed_native_state
            _seed_native_state(symbol, df, ts)
            return STATE.get(symbol)
    # Repli propre pour NQ et ES vers leur indice maître (NDX et SPX)
    if symbol == "NQ":
        return chain_state("NDX")
    if symbol == "ES":
        return chain_state("SPX")
    return st


def build_cards(symbol: str, lang: str, xf=None, scale: str | None = None) -> list:
    st = chain_state(symbol)
    with STATE.lock:
        s = st.summary
        df = st.enriched
        err = STATE.last_error
    if s is None:
        u_sym = UNDERLYINGS.get(symbol)
        is_native_fut = symbol in ("NQ", "ES", "GC", "BTC") or (u_sym and u_sym.source == "futopt")
        delayed = PUBLIC_QUOTES.price(symbol) if symbol in ("NQ", "ES") else None
        if is_native_fut and not credentials_present():
            wait = t(lang, "native_no_chain_delayed" if delayed else "native_no_chain")
        else:
            wait = t(lang, "waiting_native" if is_native_fut else "waiting_short")
        cards = [card(t(lang, "card_status"), "…", err or wait)]
        if delayed:
            cards.append(card(t(lang, "card_spot_delayed"), f"{delayed:,.2f}",
                              t(lang, "card_spot_delayed_sub"), accent=C["muted"]))
        return cards
    xf = xf or (lambda v: v)

    # Le GEX net dépend surtout du spot
    spot, is_live = live_spot(symbol, s.spot)
    net_gex = s.net_gex
    if is_live and df is not None:
        recomputed = metrics.net_gex_at(df, spot)
        if recomputed is not None:
            net_gex = recomputed

    zg_val = s.zero_gamma
    if zg_val is None and df is not None and not df.empty:
        zg_val = metrics.zero_gamma(df, spot)

    zg_txt = f"{xf(zg_val):.0f}" if zg_val else "n/a"
    zg_sub = ""
    if zg_val:
        d = spot - zg_val  # écart natif, non transposé
        zg_sub = t(lang, "card_zg_sub", sign="+" if d >= 0 else "",
                   pts=f"{d:.0f}", reg="+" if d >= 0 else "-")
    gex_color = C["pos"] if net_gex >= 0 else C["neg"]
    feed_local = s.timestamp.replace(tzinfo=ET).astimezone(LOCAL_TZ)
    fut_px = QUOTES.price(scale) if scale and scale not in UNDERLYINGS else None
    display_spot = fut_px if fut_px else xf(spot)
    spot_sub = (t(lang, "card_spot_live") if is_live else
                t(lang, "card_feed", local=f"{feed_local:%H:%M:%S}",
                  et=f"{s.timestamp:%H:%M}"))

    def _fmt_usd(val: float) -> str:
        if abs(val) >= 1e9:
            return f"{val / 1e9:+.2f} $Bn"
        elif abs(val) >= 1e6:
            return f"{val / 1e6:+.1f} $M"
        return f"{val:,.0f} $"

    spot_fmt = f"{display_spot:,.2f}" if display_spot < 10000 else f"{display_spot:,.0f}"

    return [
        card(t(lang, "card_spot_rt") if is_live else t(lang, "card_spot"),
             spot_fmt, spot_sub,
             accent=C["ok"] if is_live else None),
        card(t(lang, "card_net_gex"), _fmt_usd(net_gex),
             t(lang, "stabilizing") if net_gex >= 0 else t(lang, "destabilizing"),
             accent=gex_color),
        card(t(lang, "card_net_dex"), _fmt_usd(s.net_dex),
             t(lang, "dex_long") if s.net_dex >= 0 else t(lang, "dex_short"),
             accent=C["pos"] if s.net_dex >= 0 else C["neg"]),
        card(t(lang, "card_zero_gamma"), zg_txt, zg_sub, accent=C["zg"]),
        card(t(lang, "card_gex_0dte"), _fmt_usd(s.net_gex_0dte)),
        card(t(lang, "card_pc_oi"), f"{s.pc_oi:.2f}"),
        card(t(lang, "card_pc_vol"), f"{s.pc_volume:.2f}"),
    ]


# --- Export d'un graphique en image (pour le bot Discord, etc.) -----------
# Chaque graphique du dashboard doit pouvoir sortir en PNG à la demande, pas
# seulement la heatmap : un ami qui demande « la courbe du Delta de NQ » doit
# la recevoir comme n'importe quel autre. D'où ce dispatch unique par nom.
CHART_NAMES = ("gex", "dex", "heatmap", "flow", "gflow", "tape", "history",
               "spotzg", "smile", "profile", "profile_exp", "vanna", "charm", "oi",
               "oi_change", "pos_hist", "vol_surface", "iv_term_structure",
               "gex_by_expiry", "oi_by_expiry")


def _figure_for(symbol: str, name: str, lang: str = "es", bucket: str = "Tout",
                window: float | None = None, scale: str | None = None,
                cfd_offset: float = 0.0) -> go.Figure | None:
    """Reconstruit un graphique hors du contexte Dash. `bucket` (échéance :
    0DTE / Semaine / Mois / Tout), `window` (concentration, ex. 0.02) et `scale`
    (échelle d'affichage, ex. NQ pour transposer NDX en prix NQ) sont réglables
    — sinon défauts (Tout, 4 %, échelle native). Renvoie None si le nom est
    inconnu ou si les données manquent."""
    if name not in CHART_NAMES:
        return None
    if bucket not in BUCKET_KEYS:
        bucket = "Tout"
    win = window if window is not None else 0.04    # défaut concentration ±4 %
    today = datetime.now(ET).strftime("%Y-%m-%d")
    today_d = datetime.now(ET).date()
    # Échelle : native par défaut ; sinon transpose les prix vers `scale`
    # (ex. GEX du NDX affiché en prix NQ), comme le sélecteur du dashboard.
    xf, _, _ = _transform_for(symbol, (scale or symbol).upper(), cfd_offset=cfd_offset)

    # Graphiques qui lisent le disque directement (jour + réglages par défaut).
    if name == "heatmap":
        return heatmap_fig(symbol, lang, today, win, xf, symbol, None)
    if name == "flow":
        return flow_fig(symbol, lang, today)
    if name == "gflow":
        return gamma_flow_fig(symbol, lang, today)
    if name == "tape":
        return tape_fig(symbol, lang, today)
    if name == "history":
        return history_fig(symbol, lang)
    if name == "spotzg":
        return spot_zg_fig(symbol, lang)
    if name == "vol_surface":
        return vol_surface_fig(symbol, lang, window=window or 0.15)
    if name == "iv_term_structure":
        return iv_term_structure_fig(symbol, lang)
    if name == "gex_by_expiry":
        return gex_by_expiry_fig(symbol, lang)
    if name == "oi_by_expiry":
        return oi_by_expiry_fig(symbol, lang)

    # Graphiques qui ont besoin de la chaîne enrichie courante.
    st = chain_state(symbol)
    with STATE.lock:
        df, snap = st.enriched, st.snapshot
    if df is None or snap is None:
        return None
    spot = snap.spot
    zg = metrics.zero_gamma(df, spot)
    sel = df[metrics.bucket_mask(df, bucket, today_d)]
    b_lbl = t(lang, BUCKET_KEYS[bucket])
    # Mêmes murs que le dashboard : structural = clôture veille (magnitude),
    # live = spot courant en séance (côté), périmètre = bucket affiché.
    structural = ref_spot(symbol, spot)
    live = spot if market_is_open() else structural

    if name == "gex":
        res = metrics.compute_levels(df, structural, live, bucket=bucket, today=today_d)
        hvl = metrics.zero_gamma(df, spot, weight_col="volume")
        return exposure_fig(sel, spot, zg, "gex",
                            t(lang, "gex_title", bucket=b_lbl), lang,
                            levels=res["levels"], hvl=hvl, xf=xf, keys=res["keys"], window=win)
    if name == "dex":
        res = metrics.compute_levels(df, structural, live, bucket=bucket, today=today_d)
        hvl = metrics.zero_gamma(df, spot, weight_col="volume")
        return exposure_fig(sel, spot, zg, "dex",
                            t(lang, "dex_title", bucket=b_lbl), lang,
                            hvl=hvl, xf=xf, keys=res["keys"], level_set="regime", window=win)
    if name == "smile":
        return smile_fig(sel, spot, lang)
    if name == "profile":
        return profile_fig(df, spot, zg, lang, window or 0.08, xf)
    if name == "profile_exp":
        return profile_by_expiry_fig(df, spot, lang, window or 0.08, xf)
    if name in ("vanna", "charm"):
        sec = metrics.add_second_order(sel, spot)
        col = "vex" if name == "vanna" else "cex"
        title = t(lang, "vex_title" if name == "vanna" else "cex_title")
        return second_order_fig(sec, spot, col, title, win, xf)
    if name in ("oi", "pos", "oi_dist"):
        return pos_distribution_fig(df, spot, lang, window=win or 0.15, xf=xf, max_pain=calc_max_pain(df))
    if name == "oi_change":
        prev = store.load_previous_snapshot(symbol, today)
        prev_day = prev[0] if prev else today
        prev_df = prev[1] if prev else pd.DataFrame()
        chg = metrics.oi_change(prev_df, df) if not prev_df.empty else pd.DataFrame()
        return oi_change_fig(chg, spot, lang, prev_day, win, xf, df_cur=df)
    if name == "pos_hist":
        return pos_history_fig(symbol, lang, xf)
    return None


def chart_png(symbol: str, name: str, lang: str = "es", bucket: str = "Tout",
              window: float | None = None, scale: str | None = None) -> bytes | None:
    """PNG d'un graphique, ou None si indisponible. `bucket`/`window`/`scale`
    réglables (échéance, concentration, échelle d'affichage). Fond opaque (le
    thème sombre a un fond transparent par défaut, illisible dans Discord)."""
    fig = _figure_for(symbol, name, lang, bucket, window, scale)
    if fig is None:
        return None
    fig.update_layout(paper_bgcolor=C["surface"], plot_bgcolor=C["surface"])
    # Round-trip via l'encodeur JSON de Plotly : kaleido sérialise avec orjson,
    # qui refuse les Timestamp pandas présents dans les bornes d'axe (heatmap,
    # history fixent un `range` en Timestamps). L'encodeur Plotly les convertit
    # proprement en chaînes ISO ; from_json reconstruit une figure sérialisable.
    import plotly.io as pio
    fig = pio.from_json(pio.to_json(fig))
    return fig.to_image(format="png", width=1100, height=620, scale=2)



# ============================================================
# Analytics Tab — fonctions de graphiques avancés
# Toutes les données viennent de la chaîne d'options CBOE réelle
# (metrics.enrich) ou du Tape dxFeed (flowtape). Aucun simulé.
# ============================================================

def vol_surface_fig(symbol: str, lang: str, window: float = 0.15) -> go.Figure:
    """Skew IV par expirations proches — données RÉELLES de la chaîne.

    Fonctionne pour TOUS les actifs (indices, ETF, futures CME, crypto BTC, or GC, actions).
    Chaque courbe montre l'IV observée dans le snapshot le plus récent.
    """
    title = guided(t(lang, "vol_surface_title"), "smile")
    st = chain_state(symbol)
    with STATE.lock:
        df, snap = st.enriched, st.snapshot
    if df is None or snap is None:
        return empty_fig(t(lang, "waiting_first_pull"), title, height=380)

    spot = snap.spot
    eff_w = max(window, 0.20) if symbol == "BTC" else max(window, 0.10) if symbol in ("GC", "GLD") else max(window, 0.04)
    lo, hi = spot * (1 - eff_w), spot * (1 + eff_w)

    has_oi = (df["open_interest"] > 0).any()
    oi_mask = (df["open_interest"] > 0) if has_oi else (df["strike"] > 0)
    sel = df[(df["strike"] >= lo) & (df["strike"] <= hi) & (df["iv"] > 1e-4) & oi_mask].copy()
    if sel.empty:
        sel = df[(df["iv"] > 1e-4) & oi_mask].copy()
    if sel.empty:
        return empty_fig(t(lang, "no_iv"), title, height=380)

    expiries = sorted(sel["expiry"].unique())[:4]
    palette = [C["pos"], C["neg"], C["zg"], C["hvl"]]
    fig = go.Figure()
    for i, exp in enumerate(expiries):
        chunk = sel[sel["expiry"] == exp].sort_values("strike")
        for typ, dash in [("C", "solid"), ("P", "dash")]:
            sub = chunk[chunk["type"] == typ]
            if sub.empty:
                continue
            label = f"{exp} {'Call' if typ == 'C' else 'Put'}"
            fig.add_scatter(
                x=sub["strike"], y=sub["iv"] * 100, mode="lines+markers",
                name=label,
                line=dict(color=palette[i % len(palette)], width=1.8, dash=dash),
                marker=dict(size=4),
                hovertemplate=f"Strike: %{{x:,.1f}}<br>IV: %{{y:.1f}}%<br>{label}<extra></extra>",
            )
    spot_txt = f"Spot: {spot:,.1f}" if spot >= 100 else f"Spot: {spot:,.2f}"
    fig.add_vline(x=spot, line_color=C["spot"], line_width=1.5, line_dash="dot",
                  annotation_text=spot_txt, annotation_font_color=C["muted"],
                  annotation_position="top left")
    lay = with_legend(base_layout(title, height=380))
    lay["xaxis"]["title"] = dict(text="Strike", font=dict(color=C["muted"]))
    lay["yaxis"]["title"] = dict(text=t(lang, "axis_iv"), font=dict(color=C["muted"]))
    fig.update_layout(**lay)
    return fig


def iv_term_structure_fig(symbol: str, lang: str) -> go.Figure:
    """Structure temporelle de l'IV ATM — données RÉELLES pour TOUS les actifs.

    Pour chaque échéance, extrait l'IV du strike le plus proche du spot (ATM).
    Supporte les actifs mono-échéance (BTC) et multi-échéances (SPX, NDX, etc.).
    """
    title = guided(t(lang, "vol_term_title"), "smile")
    st = chain_state(symbol)
    with STATE.lock:
        df, snap = st.enriched, st.snapshot
    if df is None or snap is None:
        return empty_fig(t(lang, "waiting_first_pull"), title, height=300)

    spot = snap.spot
    has_oi = (df["open_interest"] > 0).any()
    oi_mask = (df["open_interest"] > 0) if has_oi else (df["strike"] > 0)
    valid = df[(df["iv"] > 1e-4) & oi_mask].copy()
    if valid.empty:
        return empty_fig(t(lang, "no_iv"), title, height=300)

    points = []
    for exp in sorted(valid["expiry"].unique()):
        chunk = valid[valid["expiry"] == exp]
        atm_idx = (chunk["strike"] - spot).abs().idxmin()
        row = chunk.loc[atm_idx]
        dte = row["t_years"] * 365.0 if "t_years" in chunk.columns else 0
        if dte > 0:
            points.append({"dte": dte, "iv": row["iv"] * 100, "exp": str(exp)})

    if not points:
        return empty_fig(t(lang, "no_iv"), title, height=300)

    pts = pd.DataFrame(points).sort_values("dte")
    fig = go.Figure()
    
    if len(pts) == 1:
        row = pts.iloc[0]
        fig.add_scatter(
            x=[row["dte"]], y=[row["iv"]], mode="markers+text",
            name="ATM IV",
            marker=dict(size=14, color=C["pos"], symbol="diamond",
                        line=dict(width=2, color=C["spot"])),
            text=[f"  {row['iv']:.1f}% ({row['exp']})"],
            textposition="middle right",
            textfont=dict(color=C["pos"], size=13),
            hovertemplate=f"DTE: {row['dte']:.1f}<br>ATM IV: {row['iv']:.1f}%<br>Exp: {row['exp']}<extra></extra>",
        )
        fig.add_hline(y=row["iv"], line_color=C["pos"], line_width=1, line_dash="dash",
                      annotation_text=f"ATM: {row['iv']:.1f}%", annotation_position="top left",
                      annotation_font_color=C["pos"])
    else:
        fig.add_scatter(
            x=pts["dte"], y=pts["iv"], mode="lines+markers",
            name="ATM IV",
            line=dict(color=C["pos"], width=2.5),
            marker=dict(size=8, color=C["pos"], line=dict(width=2, color=C["surface"])),
            text=pts["exp"],
            hovertemplate="DTE: %{x:.0f}<br>IV: %{y:.1f}%<br>Exp: %{text}<extra></extra>",
        )

    lay = base_layout(title, height=300)
    lay["xaxis"]["title"] = dict(text=t(lang, "vol_term_axis"), font=dict(color=C["muted"]))
    lay["yaxis"]["title"] = dict(text=t(lang, "axis_iv"), font=dict(color=C["muted"]))
    fig.update_layout(**lay)
    return fig


def whale_tracker_table(symbol: str, lang: str) -> html.Div:
    """Tableau des gros blocs — données RÉELLES du Tape dxFeed pour TOUS les actifs.

    Seuils calibrés automatiquement selon l'actif :
    - BTC : ≥2 contrats (valeur notionnelle ≥$800k)
    - GC (Gold) : ≥5 contrats (valeur notionnelle ≥$1.3M)
    - SPX / NDX / ETF / Actions : ≥50 contrats OU ≥$500K notionnel.
    Sans transactions dxFeed en direct, affiche l'état temps réel du Tape.
    """
    from gex.adapters.market_data.flowtape import TAPE

    rows = TAPE.recent_prints(symbol, min_size=0, include_combos=False, limit=300)
    if not rows:
        proxy_map = {"BTC": "IBIT", "GC": "GLD", "NQ": "NDX", "ES": "SPX"}
        proxy = proxy_map.get(symbol)
        if proxy:
            rows = TAPE.recent_prints(proxy, min_size=0, include_combos=False, limit=300)

    is_btc = symbol in ("BTC", "IBIT")
    is_gc = symbol in ("GC", "GLD")
    min_contracts = 2 if is_btc else 5 if is_gc else 50
    min_usd = 250_000 if (is_btc or is_gc) else 500_000

    whales = [
        r for r in rows
        if (r["size"] >= min_contracts and (r.get("notional") or 0) >= 100_000)
        or ((r.get("notional") or 0) >= min_usd)
        or (is_btc and r["size"] >= 2)
        or (is_gc and r["size"] >= 5)
    ]

    if not whales:
        etat, total_sub = TAPE.status()
        is_conn = etat == "connected"
        stat_color = C["pos"] if is_conn else C["neg"] if etat == "disconnected" else C["muted"]
        stat_txt = t(lang, "whale_live_monitoring" if is_conn else "whale_empty")
        return html.Div([
            html.Div([
                html.Span(className="live-pulse", style={"backgroundColor": stat_color}, **{"aria-hidden": "true"}),
                html.Span(f"{symbol} Whale Tracker — ", style={"fontWeight": "600", "color": C["ink"]}),
                html.Span(f"Filtre: ≥{min_contracts} contrats / ≥${min_usd:,.0f} notionnel. ", style={"color": C["muted"]}),
                html.Span(stat_txt, style={"color": C["muted"]}),
            ], className="whale-status-card")
        ], className="analytics-empty-wrap")

    entete = [t(lang, k) for k in ("whale_col_time", "whale_col_contract",
                                    "whale_col_side", "whale_col_size",
                                    "whale_col_price", "whale_col_notional")]
    trs = [html.Tr([html.Th(h, className="whale-th") for h in entete])]

    for r in whales[:60]:
        achat = r["side"] == "BUY"
        vente = r["side"] == "SELL"
        couleur = C["pos"] if achat else C["neg"] if vente else C["muted"]
        contrat = (f"{r['strike']:,.0f}{r['type']}"
                   if r["strike"] is not None and r["type"] else "—")
        side_txt = (t(lang, "tape_buy") if achat else t(lang, "tape_sell") if vente else "?")
        heure = datetime.fromtimestamp(r["t"], tz=LOCAL_TZ).strftime("%H:%M:%S")
        notio = _fmt_notional(r["notional"])
        prix = f"{r['price']:.2f}" if r["price"] is not None else "—"
        notional = r.get("notional") or 0
        glow = ""
        if notional >= 1_000_000 or (is_btc and r["size"] >= 5):
            glow = " whale-mega"
        elif notional >= 500_000 or (is_btc and r["size"] >= 2):
            glow = " whale-large"

        trs.append(html.Tr([
            html.Td(heure, className="whale-td whale-mono"),
            html.Td(contrat, className="whale-td"),
            html.Td(side_txt, className="whale-td",
                     style={"color": couleur, "fontWeight": "700"}),
            html.Td(f"{int(r['size']):,}", className="whale-td whale-mono whale-num"),
            html.Td(prix, className="whale-td whale-mono whale-num"),
            html.Td(notio, className="whale-td whale-mono whale-num"),
        ], className=f"whale-row{glow}",
           style={"borderLeft": f"3px solid {couleur}"}))

    return html.Table(trs, className="whale-table")


def gex_by_expiry_fig(symbol: str, lang: str) -> go.Figure:
    """GEX net par bucket d'expirations avec échelle dynamique ($Bn / $M / $k).

    S'adapte automatiquement à l'ordre de grandeur de l'actif (SPX en Md$,
    actions ou crypto en M$). Données 100 % réelles de la chaîne.
    """
    title = t(lang, "gex_expiry_title")
    st = chain_state(symbol)
    with STATE.lock:
        df, snap = st.enriched, st.snapshot
    if df is None or snap is None:
        return empty_fig(t(lang, "waiting_first_pull"), title, height=340)

    if "gex" not in df.columns or df.empty:
        return empty_fig(t(lang, "waiting_first_pull"), title, height=340)

    grp = df.groupby("expiry").agg(
        gex_net=("gex", "sum"),
        gex_calls=("gex", lambda x: x[df.loc[x.index, "type"] == "C"].sum()),
        gex_puts=("gex", lambda x: x[df.loc[x.index, "type"] == "P"].sum()),
        oi_total=("open_interest", "sum"),
    ).reset_index().sort_values("expiry")

    max_abs = grp["gex_net"].abs().max()
    if max_abs >= 5e8:
        div = 1e9
        unit_str = "$Bn"
    elif max_abs >= 5e5:
        div = 1e6
        unit_str = "$M"
    else:
        div = 1e3
        unit_str = "$k"

    fig = go.Figure()
    fig.add_bar(
        x=grp["expiry"].astype(str), y=grp["gex_net"] / div,
        name="GEX Net",
        marker=dict(
            color=[C["pos"] if v >= 0 else C["neg"] for v in grp["gex_net"]],
            line=dict(width=0),
        ),
        hovertemplate=f"Exp: %{{x}}<br>GEX: %{{y:+.2f}} {unit_str}<extra></extra>",
    )
    lay = base_layout(title, height=340)
    lay["xaxis"]["title"] = dict(text="Expiry", font=dict(color=C["muted"]))
    lay["yaxis"]["title"] = dict(text=f"{t(lang, 'gex_expiry_axis')} ({unit_str})", font=dict(color=C["muted"]))
    lay["xaxis"]["tickangle"] = -45
    fig.update_layout(**lay)
    fig.add_hline(y=0, line_color=C["axis"], line_width=1.2)
    return fig


def oi_by_expiry_fig(symbol: str, lang: str) -> go.Figure:
    """Open interest par expirations, calls vs puts — données RÉELLES."""
    title = t(lang, "oi_expiry_title")
    st = chain_state(symbol)
    with STATE.lock:
        df, snap = st.enriched, st.snapshot
    if df is None or snap is None:
        return empty_fig(t(lang, "waiting_first_pull"), title, height=300)
    if df.empty:
        return empty_fig(t(lang, "waiting_first_pull"), title, height=300)

    calls = df[df["type"] == "C"].groupby("expiry")["open_interest"].sum().reset_index()
    puts = df[df["type"] == "P"].groupby("expiry")["open_interest"].sum().reset_index()

    tot_oi = calls["open_interest"].sum() + puts["open_interest"].sum()
    y_col = "open_interest"
    y_lbl = t(lang, "oi_expiry_axis")

    if tot_oi == 0 and "volume" in df.columns and df["volume"].sum() > 0:
        calls = df[df["type"] == "C"].groupby("expiry")["volume"].sum().reset_index()
        puts = df[df["type"] == "P"].groupby("expiry")["volume"].sum().reset_index()
        y_col = "volume"
        y_lbl = "Volume"

    fig = go.Figure()
    fig.add_bar(x=calls["expiry"].astype(str), y=calls[y_col],
                name=f"Calls {y_col.capitalize()}", marker_color=C["pos"],
                hovertemplate="Exp: %{x}<br>" + y_lbl + ": %{y:,.0f}<extra></extra>")
    fig.add_bar(x=puts["expiry"].astype(str), y=puts[y_col],
                name=f"Puts {y_col.capitalize()}", marker_color=C["neg"],
                hovertemplate="Exp: %{x}<br>" + y_lbl + ": %{y:,.0f}<extra></extra>")
    lay = with_legend(base_layout(title, height=300))
    lay["xaxis"]["title"] = dict(text="Expiry", font=dict(color=C["muted"]))
    lay["yaxis"]["title"] = dict(text=y_lbl, font=dict(color=C["muted"]))
    lay["xaxis"]["tickangle"] = -45
    lay["barmode"] = "group"
    fig.update_layout(**lay)
    return fig


def levels_table(symbol: str, lang: str, window: float = 0.05) -> html.Div:
    """Tableau détaillé des niveaux GEX avec formatage dynamique pour TOUS les actifs.

    Ajuste l'échelle d'affichage (B, M, k) pour chaque actif et garantit que
    les actifs à strikes étendus (BTC, GC) affichent leurs niveaux pertinents.
    """
    st = chain_state(symbol)
    with STATE.lock:
        df, snap = st.enriched, st.snapshot
    if df is None or snap is None:
        return html.Div(t(lang, "levels_empty"), className="hint analytics-empty")

    spot = snap.spot
    eff_w = max(window, 0.20) if symbol == "BTC" else max(window, 0.10) if symbol in ("GC", "GLD") else max(window, 0.04)
    lo, hi = spot * (1 - eff_w), spot * (1 + eff_w)
    sel = df[(df["strike"] >= lo) & (df["strike"] <= hi)].copy()
    if sel.empty:
        sel = df.copy()
    if sel.empty:
        return html.Div(t(lang, "levels_empty"), className="hint analytics-empty")

    agg = sel.groupby("strike").agg(
        gex=("gex", "sum") if "gex" in sel.columns else ("strike", lambda x: 0.0),
        oi=("open_interest", "sum") if "open_interest" in sel.columns else ("strike", lambda x: 0.0),
        iv_avg=("iv", "mean") if "iv" in sel.columns else ("strike", lambda x: 0.0),
        type_dom=("type", lambda x: "C" if (x == "C").sum() >= (x == "P").sum() else "P"),
    ).reset_index()

    if "delta_bs" in sel.columns and "open_interest" in sel.columns:
        dex_agg = sel.groupby("strike").apply(
            lambda g: (g["delta_bs"] * g["open_interest"] * 100 * snap.spot).sum()
        ).reset_index(name="dex")
        agg = agg.merge(dex_agg, on="strike", how="left")
    else:
        agg["dex"] = 0.0

    if agg["gex"].abs().sum() > 0:
        agg = agg.sort_values("gex", key=abs, ascending=False).head(25)
    else:
        agg["dist"] = (agg["strike"] - spot).abs()
        agg = agg.sort_values("dist").head(25).drop(columns=["dist"])

    def _fmt_cell(val: float) -> str:
        av = abs(val)
        if av >= 1e9:
            return f"{val / 1e9:+.2f} B"
        elif av >= 1e6:
            return f"{val / 1e6:+.1f} M"
        elif av >= 1e3:
            return f"{val / 1e3:+.0f} k"
        elif av > 0:
            return f"{val:+.1f}"
        return "0.0"

    entete = [t(lang, k) for k in ("levels_col_strike", "levels_col_gex",
                                    "levels_col_dex", "levels_col_oi",
                                    "levels_col_iv", "levels_col_type")]
    trs = [html.Tr([html.Th(h, className="lvl-th") for h in entete])]

    for _, row in agg.iterrows():
        gex_raw = row["gex"]
        is_pos = gex_raw >= 0
        couleur = C["pos"] if is_pos else C["neg"]
        at_spot = abs(row["strike"] - spot) / spot < 0.003
        strike_fmt = f"{row['strike']:,.1f}" if row['strike'] % 1 != 0 else f"{row['strike']:,.0f}"

        trs.append(html.Tr([
            html.Td(strike_fmt, className="lvl-td lvl-mono",
                     style={"fontWeight": "700", "color": C["spot"]}),
            html.Td(_fmt_cell(gex_raw), className="lvl-td lvl-mono lvl-num",
                     style={"color": couleur, "fontWeight": "600"}),
            html.Td(_fmt_cell(row['dex']), className="lvl-td lvl-mono lvl-num"),
            html.Td(f"{int(row['oi']):,}", className="lvl-td lvl-mono lvl-num"),
            html.Td(f"{row['iv_avg'] * 100:.1f}%", className="lvl-td lvl-mono lvl-num"),
            html.Td(row["type_dom"], className="lvl-td",
                     style={"color": C["pos"] if row["type_dom"] == "C" else C["neg"], "fontWeight": "700"}),
        ], className="lvl-row",
           style={"borderLeft": f"3px solid {couleur}",
                  "background": "rgba(0, 240, 255, 0.08)" if at_spot else ""}))

    return html.Table(trs, className="levels-table")


def create_app() -> Dash:

    # assets/ vit dans le package (gex/assets) pour survivre à un pip install ;
    # Dash les sert dans tous les cas sous /assets.
    app = Dash(__name__, title="GEX Dashboard",
               assets_folder=str(Path(__file__).resolve().parents[2] / "assets"),
               suppress_callback_exceptions=True)
    enabled = all_targets()
    from gex.adapters.market_data.rtquote import _env
    # Credentials must never be serialized into the Dash layout. They remain
    # server-side whether this is a local or shared deployment.
    init_cid = ""
    init_sec = ""
    init_ref = ""
    shared_deployment = shared_deployment_enabled()

    init_sym = enabled[0].key if enabled else "SPX"
    alert_monitor = AlertMonitor()
    alert_monitor_threshold: int | None = None
    init_overlay_days = available_overlay_days(init_sym)
    today_str = datetime.now(ET).strftime("%Y-%m-%d")
    init_overlay_options = [
        {"label": f"{d} {'(en vivo / actual)' if d == today_str else '(sesión histórica)'}", "value": d}
        for d in reversed(init_overlay_days)
    ]
    init_overlay_val = today_str if today_str in init_overlay_days else (
        init_overlay_days[-1] if init_overlay_days else None
    )
    init_overlay_fig = None
    if init_overlay_val:
        init_chain, init_spot = _chain_for_day(init_sym, init_overlay_val)
        if init_chain is not None and init_spot is not None:
            init_ref_spot = store.previous_close_spot(init_sym, day=init_overlay_val) or init_spot
            init_res = metrics.compute_levels(init_chain, init_ref_spot, init_spot, bucket="all")
            init_flip = metrics.zero_gamma(init_chain, init_spot)
            init_snaps = store.load_day_snapshots(init_sym, init_overlay_val)
            init_overlay_fig = build_options_overlay(
                init_sym, init_chain, init_spot, init_flip, init_res["keys"],
                init_overlay_val, 0.03, snapshots=init_snaps,
            )
    if init_overlay_fig is None:
        init_overlay_fig = empty_fig("Cargando precio y niveles GEX...", height=620)

    def ctl(label_id, control):
        """Contrôle étiqueté : la légende dit ce que le segment pilote."""
        return html.Div([html.Span(id=label_id, className="ctl-label"), control],
                        className="ctl")

    app.layout = html.Div([
        # bandeau + superposition : NQ/ES sans identifiants dxFeed (cf.
        # native_notice_content) — vides par défaut, peuplés par le callback
        # native_notice sur changement de symbole.
        html.Div(id="native-banner", className="native-banner", style={"display": "none"}),
        dcc.Store(id="terminal-alert-state", data={"enabled": False, "events": []}, storage_type="local"),
        # ------------------------------------------------------ barre haute
        html.Div([
            html.Div([
                html.Div([
                    html.Div("Γ", className="brand-mark"),
                    html.Span(id="app-title"),
                    html.Span(id="brand-sub", className="brand-sub"),
                ], className="brand"),
                terminal_topbar_market(),
                html.Div([
                    dcc.Dropdown(
                        id="symbol", className="symbol-picker",
                        options=[{"label": u.label, "value": u.key} for u in enabled],
                        value=enabled[0].key, clearable=False, searchable=True,
                        optionHeight=34, placeholder="Selecciona un subyacente",
                        persistence=True, persistence_type="local"),
                    dcc.RadioItems(id="unit", className="seg", inline=True,
                                   persistence=True, persistence_type="local"),
                    dcc.RadioItems(
                        id="lang", className="seg",
                        options=[{"label": l.upper(), "value": l} for l in LANGS],
                        value="es", inline=True, persistence=True, persistence_type="local"),
                    html.Button(
                        "SETTINGS", id="terminal-settings-shortcut",
                        className="terminal-topbar-settings", n_clicks=0,
                        title="Open terminal settings",
                    ),
                    # page statique servie depuis assets/ (nouvel onglet)
                    html.A(id="faq-link", className="linkbtn", href="/assets/faq.html",
                           target="_blank", children="FAQ"),
                    # Bouton modal API Tastytrade
                    html.Button([
                        html.Span(id="tt-btn-text", children="API Tastytrade"),
                    ], id="tt-modal-open-btn", className="btn-tt-api", n_clicks=0,
                       title="Configurar credenciales API Tastytrade",
                       style={"display": "none"} if shared_deployment else None),
                    # état du flux temps réel : pastille et libellé
                    html.Div([html.Span(className="rt-dot"),
                              html.Span(id="rt-label")],
                             id="rt-badge", className="rt-badge", n_clicks=0,
                             title="Estado del flujo tiempo real (clic para configurar)"),
                    # Connexion courtier : lien direct vers la route OAuth
                    html.A(id="tt-connect", className="linkbtn",
                           href="/oauth/start", children="Connecter tastytrade",
                           style={"display": "none"}),
                ], className="topbar-actions"),
            ], className="topbar-row"),
            html.Div([
                ctl("lbl-bucket", dcc.RadioItems(id="bucket", className="seg",
                                                 value="Tout", inline=True,
                                                 persistence=True, persistence_type="local")),
                ctl("lbl-window", dcc.RadioItems(
                    id="window", className="seg",
                    options=[{"label": "±2%", "value": 0.02},
                             {"label": "±5%", "value": 0.05},
                             {"label": "±15%", "value": 0.15},
                             {"label": "±30%", "value": 0.30},
                             {"label": "Todo", "value": 1.00}],
                    value=0.05, inline=True, persistence=True, persistence_type="local")),
                dcc.Checklist(id="majors", className="check", value=[], inline=True,
                              persistence=True, persistence_type="local"),
                ctl("lbl-cfd", html.Div([
                    dcc.Input(
                        id="cfd-offset-input",
                        type="number",
                        step="any",
                        placeholder="0.0",
                        className="cfd-input",
                        debounce=True,
                    ),
                    html.Button("Auto", id="cfd-auto-btn", className="cfd-btn cfd-btn-auto",
                                title="Ajuste automático desde Yahoo Finance"),
                    html.Button("0", id="cfd-reset-btn", className="cfd-btn cfd-btn-reset",
                                title="Reset offset"),
                    html.Button("Calc", id="cfd-calc-btn", className="cfd-btn cfd-btn-calc",
                                title="Calculadora CFD"),
                ], id="cfd-control-group", className="cfd-control-group")),
            ], className="toolbar"),
        ], className="topbar"),

        # ---------------------------------------------------------- terminal
        html.Div([
            terminal_sidebar(),
            html.Main([
            dcc.Tabs(id="tab", value="main", className="tabbar", persistence=True,
                     persistence_type="local", children=[
                dcc.Tab(value=v, label=t("es", f"tab_{v}"), id=f"tabh-{v}",
                        className="tab-item", selected_className="tab-item--selected")
                for v in TABS
            ]),

            html.Div([
                html.Div([
                    html.Div([html.Span("MARKET MONITOR", className="eyebrow"),
                              html.H1(id="workspace-title", children="Gamma Exposure Desk")],
                             className="workspace-copy"),
                    html.Div([html.Span(className="live-pulse", **{"aria-hidden": "true"}),
                              html.Span(id="workspace-status", children="Datos de mercado")],
                             className="workspace-status"),
                ], className="workspace-head"),
                html.Div(id="workspace-summary", className="workspace-summary"),
            ], className="workspace-hero"),

            html.Div(id="pane-main", className="page-pane", style={"display": "block"}, children=[
                html.Div(id="terminal-overview-briefing"),
                html.Div([
                    html.Span("MARKET MAP", className="section-kicker"),
                    html.Span("Price, positioning and normalized key levels", className="section-note"),
                ], className="section-head"),
                dcc.Graph(id="overview-market-map", config=GRAPH_CONFIG,
                          figure=empty_fig("Waiting for a market snapshot.", height=620)),
                html.Div([
                    html.Span("MARKET SNAPSHOT", className="section-kicker"),
                    html.Span("Live positioning metrics", className="section-note"),
                ], className="section-head"),
                html.Div(id="cards", className="cards"),
                html.Div(id="pc-gauge"),
                html.Div(id="regime-banner"),
                html.Div([
                    html.Div(id="levels", className="chips"),
                    # copie des niveaux au format de l'indicateur TradingView
                    # (cf. tv_levels_string) — la chaîne suit l'échelle affichée
                    dcc.Clipboard(id="tv-copy", className="tv-copy"),
                ], className="levels-row"),
                html.Div([
                    html.Span("PRICE & GAMMA MAP", className="section-kicker"),
                    html.Span("Intraday price, walls and flow", className="section-note"),
                ], className="section-head"),
                html.Div([
                    html.Div([
                        html.Span("DATA SESSION", className="ctl-label"),
                        dcc.Dropdown(
                            id="overlay-day", className="dash-dropdown", clearable=False,
                            options=init_overlay_options, value=init_overlay_val,
                            placeholder="Select a saved session",
                        ),
                    ], className="chart-command-field chart-command-field--session"),
                    html.Div([
                        html.Span("TIMEFRAME", className="ctl-label"),
                        dcc.Dropdown(
                            id="overlay-timeframe", className="dash-dropdown", clearable=False,
                            options=[
                                {"label": "1 minute", "value": "1m"}, {"label": "5 minutes", "value": "5m"},
                                {"label": "15 minutes", "value": "15m"}, {"label": "30 minutes", "value": "30m"},
                                {"label": "1 hour", "value": "1h"}, {"label": "4 hours", "value": "4h"},
                                {"label": "1 day", "value": "1d"}, {"label": "2 days", "value": "2d"},
                                {"label": "All data", "value": "all"},
                            ], value="2d", persistence=True, persistence_type="local",
                        ),
                    ], className="chart-command-field chart-command-field--timeframe"),
                    html.Details([
                        html.Summary("Chart controls", className="chart-controls-summary"),
                        html.Div([
                            html.Div([
                                html.Span("FLOW", className="ctl-label"),
                                dcc.Dropdown(
                                    id="overlay-flow-type", className="dash-dropdown", clearable=False,
                                    options=[{"label": "All activity", "value": "ALL"}, {"label": "Calls", "value": "CALLS"}, {"label": "Puts", "value": "PUTS"}],
                                    value="ALL", persistence=True, persistence_type="local",
                                ),
                            ], className="chart-control-field"),
                            html.Div([
                                html.Span("ORDER SIDE", className="ctl-label"),
                                dcc.Dropdown(
                                    id="overlay-flow-side", className="dash-dropdown", clearable=False,
                                    options=[{"label": "All", "value": "ALL"}, {"label": "Buy", "value": "BUY"}, {"label": "Sell", "value": "SELL"}, {"label": "Unknown", "value": "UNKNOWN"}],
                                    value="ALL", persistence=True, persistence_type="local",
                                ),
                            ], className="chart-control-field"),
                            html.Div([
                                html.Span("EXPIRATION", className="ctl-label"),
                                dcc.Dropdown(
                                    id="overlay-flow-expiration", className="dash-dropdown", clearable=False,
                                    options=[
                                        {"label": "All expirations", "value": "ALL"}, {"label": "0DTE", "value": "0DTE"},
                                        {"label": "1DTE", "value": "1DTE"}, {"label": "Weekly", "value": "WEEKLY"},
                                        {"label": "Monthly", "value": "MONTHLY"}, {"label": "Custom date", "value": "CUSTOM"},
                                    ], value="ALL", persistence=True, persistence_type="local",
                                ),
                            ], className="chart-control-field"),
                            html.Div([
                                html.Span("CUSTOM EXPIRATION", className="ctl-label"),
                                dcc.Input(id="overlay-flow-expiration-custom", type="text", placeholder="YYYY-MM-DD", debounce=True,
                                          persistence=True, persistence_type="local", className="terminal-number-input"),
                            ], id="overlay-flow-expiration-custom-wrap", className="chart-control-field", style={"display": "none"}),
                            html.Div([
                                html.Span("MIN PREMIUM", className="ctl-label"),
                                dcc.Input(id="overlay-min-premium", type="number", min=0, step=10000, value=0, debounce=True,
                                          className="terminal-number-input"),
                            ], className="chart-control-field"),
                            html.Div([
                                html.Span("MIN VOLUME", className="ctl-label"),
                                dcc.Input(id="overlay-min-volume", type="number", min=0, step=1, value=0, debounce=True,
                                          className="terminal-number-input"),
                            ], className="chart-control-field"),
                            html.Div([
                                html.Span("VISIBLE LAYERS", className="ctl-label"),
                                dcc.Checklist(
                                    id="overlay-layers", className="check chart-layer-checklist",
                                    options=[
                                        {"label": "Price", "value": "price"}, {"label": "Spot", "value": "spot"},
                                        {"label": "Call Wall", "value": "call_wall"}, {"label": "Put Wall", "value": "put_wall"},
                                        {"label": "Gamma Flip", "value": "gamma_flip"}, {"label": "Flow", "value": "flow"},
                                        {"label": "Badges", "value": "annotations"},
                                    ],
                                    value=["price", "spot", "call_wall", "put_wall", "gamma_flip", "flow", "annotations"],
                                    persistence=True, persistence_type="local",
                                ),
                            ], className="chart-control-field chart-control-field--layers"),
                        ], className="chart-controls-panel"),
                    ], className="chart-controls-menu"),
                ], className="daybar chart-command-bar"),
                html.Div(
                    dcc.Graph(config=GRAPH_CONFIG, id="options-flow-overlay",
                              figure=init_overlay_fig,
                              style={"width": "100%"}),
                    className="primary-overlay-chart",
                ),
                html.Div([
                    dcc.Graph(config=GRAPH_CONFIG, id="gex-strike",
                              figure=empty_fig("Cargando GEX por Strike...", height=420)),
                    dcc.Graph(config=GRAPH_CONFIG, id="dex-strike",
                              figure=empty_fig("Cargando DEX por Strike...", height=420)),
                ], className="row", style={"marginBottom": "12px"}),
                html.Div([
                    html.Span(id="flow-day-label", className="ctl-label"),
                    dcc.Dropdown(id="flow-day", clearable=False,
                                 style={"width": "160px"}),
                    html.Button(id="flow-today", n_clicks=0, className="btn"),
                ], className="daybar"),
                html.Div([
                    html.Span("FLOW & POSITIONING", className="section-kicker"),
                    html.Span("Intraday pressure and dealer activity", className="section-note"),
                ], className="section-head"),
                dcc.Graph(config=GRAPH_CONFIG, id="flow",
                          figure=empty_fig("Cargando Delta Flow...", height=420),
                          style={"marginBottom": "12px"}),
                html.Div([
                    html.Span(id="lbl-gflow-series", className="ctl-label"),
                    dcc.Checklist(id="gflow-series", className="check", inline=True,
                                 value=["calls", "puts", "net"]),
                ], className="daybar"),
                dcc.Graph(config=GRAPH_CONFIG, id="gflow",
                          figure=empty_fig("Cargando Gamma Flow...", height=420),
                          style={"marginBottom": "12px"}),
                # Order flow SIGNÉ : placé juste après les deux proxys non
                # signés, pour que la différence saute aux yeux plutôt que de
                # se deviner. Le bandeau porte la provenance et la licence.
                html.Div([
                    html.Span(id="lbl-tape-series", className="ctl-label"),
                    dcc.Checklist(id="tape-series", className="check", inline=True,
                                 value=["net", "calls", "puts"]),
                ], className="daybar"),
                dcc.Graph(config=GRAPH_CONFIG, id="tape",
                          figure=empty_fig("Cargando Order Flow Tape...", height=420)),
                html.Div(id="tape-note", className="hint",
                         style={"marginBottom": "12px"}),
                html.Div([
                    dcc.Graph(config=GRAPH_CONFIG, id="gex-history",
                              figure=empty_fig("Cargando Histórico GEX...", height=420)),
                    dcc.Graph(config=GRAPH_CONFIG, id="spot-zg",
                              figure=empty_fig("Cargando Spot vs Flip...", height=420)),
                    dcc.Graph(config=GRAPH_CONFIG, id="smile",
                              figure=empty_fig("Cargando Skew / Smile...", height=420)),
                ], className="row"),
            ]),

            html.Div(id="pane-profile", className="page-pane", style={"display": "none"}, children=[
                html.Div([
                    html.Div([
                        html.Span("EXPIRY", className="ctl-label"),
                        dcc.RadioItems(
                            id="profile-expiry", className="seg", inline=True,
                            options=[
                                {"label": "All", "value": "Tout"},
                                {"label": "0DTE", "value": "0DTE"},
                                {"label": "Week", "value": "Semaine"},
                                {"label": "Month", "value": "Mois"},
                            ], value="Tout", persistence=True, persistence_type="local",
                        ),
                    ], className="terminal-profile-filter"),
                    html.Div([
                        html.Span("SIDE", className="ctl-label"),
                        dcc.RadioItems(
                            id="profile-side", className="seg", inline=True,
                            options=[
                                {"label": "All", "value": "ALL"},
                                {"label": "Calls", "value": "CALLS"},
                                {"label": "Puts", "value": "PUTS"},
                            ], value="ALL", persistence=True, persistence_type="local",
                        ),
                    ], className="terminal-profile-filter"),
                    html.Div([
                        html.Span("MODE", className="ctl-label"),
                        dcc.RadioItems(
                            id="profile-mode", className="seg", inline=True,
                            options=[{"label": "Net", "value": "NET"}, {"label": "Absolute", "value": "ABSOLUTE"}],
                            value="NET", persistence=True, persistence_type="local",
                        ),
                    ], className="terminal-profile-filter"),
                ], className="terminal-profile-filters"),
                html.Div(id="profile-hint", className="hint"),
                dcc.Graph(config=GRAPH_CONFIG, id="profile",
                          figure=empty_fig("Cargando Gamma Profile...", height=420),
                          style={"marginBottom": "12px"}),
                dcc.Graph(config=GRAPH_CONFIG, id="profile-exp",
                          figure=empty_fig("Cargando Perfil por Vencimiento...", height=420)),
            ]),

            html.Div(id="pane-options", className="page-pane", style={"display": "none"}, children=[
                html.Div([
                    html.Div([
                        html.Span("OPTIONS CHAIN", className="section-kicker"),
                        html.Span("ATM, walls, open interest and gamma context", className="section-note"),
                    ], className="section-head"),
                    html.Div([
                        html.Div([
                            html.Span("EXPIRATION", className="ctl-label"),
                            dcc.Dropdown(id="options-chain-expiration", clearable=False,
                                         options=[{"label": "All expirations", "value": "ALL"}],
                                         value="ALL", className="dash-dropdown"),
                        ], className="terminal-chain-filter"),
                        html.Div([
                            html.Span("SIDE", className="ctl-label"),
                            dcc.RadioItems(
                                id="options-chain-side", className="seg", inline=True,
                                options=[
                                    {"label": "All", "value": "ALL"},
                                    {"label": "Calls", "value": "CALLS"},
                                    {"label": "Puts", "value": "PUTS"},
                                ], value="ALL", persistence=True, persistence_type="local",
                            ),
                        ], className="terminal-chain-filter"),
                        html.Div([
                            html.Span("STRIKE RANGE %", className="ctl-label"),
                            dcc.Input(id="options-chain-range", type="number", min=0, max=100,
                                      step=1, value=5, debounce=True, persistence=True,
                                      persistence_type="local", className="terminal-number-input"),
                        ], className="terminal-chain-filter"),
                        html.Div([
                            html.Span("MIN VOLUME", className="ctl-label"),
                            dcc.Input(id="options-chain-min-volume", type="number", min=0, step=1,
                                      value=0, debounce=True, persistence=True,
                                      persistence_type="local", className="terminal-number-input"),
                        ], className="terminal-chain-filter"),
                        html.Div([
                            html.Span("MIN OI", className="ctl-label"),
                            dcc.Input(id="options-chain-min-oi", type="number", min=0, step=1,
                                      value=0, debounce=True, persistence=True,
                                      persistence_type="local", className="terminal-number-input"),
                        ], className="terminal-chain-filter"),
                        html.Div([
                            html.Span("MIN |NET GEX|", className="ctl-label"),
                            dcc.Input(id="options-chain-min-gex", type="number", min=0, step=100000,
                                      value=0, debounce=True, persistence=True,
                                      persistence_type="local", className="terminal-number-input"),
                        ], className="terminal-chain-filter"),
                        html.Div([
                            html.Span("MIN |DELTA|", className="ctl-label"),
                            dcc.Input(id="options-chain-min-delta", type="number", min=0, max=1,
                                      step=0.05, value=0, debounce=True, persistence=True,
                                      persistence_type="local", className="terminal-number-input"),
                        ], className="terminal-chain-filter"),
                    ], className="terminal-chain-filters"),
                ]),
                html.Div(id="options-chain-table"),
            ]),

            html.Div(id="pane-map", className="page-pane", style={"display": "none"}, children=[
                html.Div([
                    html.Span("MARKET MAP", className="section-kicker"),
                    html.Span("Call and put gamma exposure by strike with normalized key levels", className="section-note"),
                ], className="section-head"),
                dcc.Graph(id="market-map-chart", config=GRAPH_CONFIG,
                          figure=empty_fig("Waiting for a market snapshot.", height=620)),
            ]),

            html.Div(id="pane-levels", className="page-pane", style={"display": "none"}, children=[
                html.Div([
                    html.Span("UNIFIED LEVELS", className="section-kicker"),
                    html.Span("Source, session, strength and live relationship to spot", className="section-note"),
                ], className="section-head"),
                html.Div([
                    html.Div([
                        html.Span("TYPE", className="ctl-label"),
                        dcc.Dropdown(id="level-filter-type", className="dash-dropdown", multi=True,
                                     options=[{"label": item.value.replace("_", " "), "value": item.value} for item in LevelType],
                                     placeholder="All types"),
                    ], className="terminal-level-filter"),
                    html.Div([
                        html.Span("SOURCE", className="ctl-label"),
                        dcc.Dropdown(id="level-filter-source", className="dash-dropdown", multi=True,
                                     options=[{"label": item.value.replace("_", " "), "value": item.value} for item in LevelSource],
                                     placeholder="All sources"),
                    ], className="terminal-level-filter"),
                    html.Div([
                        html.Span("SESSION", className="ctl-label"),
                        dcc.Dropdown(id="level-filter-session", className="dash-dropdown", multi=True,
                                     options=[{"label": item.value, "value": item.value} for item in SessionType],
                                     placeholder="All sessions"),
                    ], className="terminal-level-filter"),
                ], className="terminal-level-filters"),
                dcc.Graph(id="unified-level-map", config=GRAPH_CONFIG,
                          figure=empty_fig("Waiting for unified levels.", height=500)),
                html.Div(id="unified-level-table"),
            ]),

            html.Div(id="pane-scenarios", className="page-pane", style={"display": "none"}, children=[
                html.Div(id="terminal-scenarios-page"),
            ]),

            html.Div(id="pane-greeks2", className="page-pane", style={"display": "none"}, children=[
                html.Div(id="g2-hint", className="hint"),
                html.Div(id="g2-cards", className="cards"),
                html.Div([
                    dcc.Graph(config=GRAPH_CONFIG, id="vex",
                              figure=empty_fig("Cargando Vanna Exposure...", height=420)),
                    dcc.Graph(config=GRAPH_CONFIG, id="cex",
                              figure=empty_fig("Cargando Charm Exposure...", height=420)),
                ], className="row"),
            ]),

            html.Div(id="pane-heat", className="page-pane", style={"display": "none"}, children=[
                html.Div([
                    html.Div([
                        html.Span("VIEW", className="ctl-label"),
                        dcc.Dropdown(
                            id="heat-sub", className="dash-dropdown heat-view-picker", clearable=False,
                            options=[
                                {"label": "Intraday liquidity", "value": "intraday"},
                                {"label": "Options flow bubbles", "value": "bubbles"},
                                {"label": "Expiry structure", "value": "term"},
                                {"label": "Multi-day history", "value": "hist"},
                                {"label": "GEX & price profile", "value": "overlay"},
                            ],
                            value="intraday", persistence=True, persistence_type="local",
                        ),
                    ], className="heat-view-control"),
                ], className="daybar heat-bar"),
                html.Div([
                    html.Div([
                        html.Span(id="heat-day-label", className="ctl-label"),
                        dcc.Dropdown(id="heat-day", className="dash-dropdown",
                                     clearable=False,
                                     value=datetime.now(ET).strftime("%Y-%m-%d"),
                                     style={"width": "220px"}),
                    ], className="heat-control-group"),
                    html.Div([
                        html.Span(id="heat-metric-label", className="ctl-label"),
                        dcc.RadioItems(
                            id="heat-metric", className="seg",
                            options=[
                                {"label": "Net GEX ($)", "value": "gex"},
                                {"label": "Open Interest", "value": "oi"},
                                {"label": "Volumen", "value": "vol"},
                            ],
                            value="gex", inline=True,
                        ),
                    ], className="heat-control-group"),
                    html.Div([
                        html.Span(id="heat-levels-label", className="ctl-label"),
                        dcc.Checklist(id="heat-levels", className="check", inline=True,
                                      value=["zero_gamma", "call_wall", "put_support"]),
                    ], className="heat-control-group"),
                    html.Div([
                        html.Span("Filtro burbujas:", className="ctl-label"),
                        dcc.Dropdown(
                            id="heat-bubble-min", className="dash-dropdown",
                            options=[
                                {"label": "Todas", "value": 0},
                                {"label": "≥ 10 contratos", "value": 10},
                                {"label": "≥ 50 contratos", "value": 50},
                                {"label": "≥ 100 contratos", "value": 100},
                                {"label": "≥ 500 contratos", "value": 500},
                            ],
                            value=50, clearable=False, style={"width": "170px"},
                        ),
                    ], className="heat-control-group"),
                    html.Div([
                        html.Span("Máximo:", className="ctl-label"),
                        dcc.Dropdown(
                            id="heat-bubble-limit", className="dash-dropdown",
                            options=[
                                {"label": "500 puntos", "value": 500},
                                {"label": "1.500 puntos", "value": 1500},
                                {"label": "3.000 puntos", "value": 3000},
                            ],
                            value=1500, clearable=False, style={"width": "145px"},
                        ),
                    ], className="heat-control-group"),
                ], id="heat-controls-row", className="ctl", style={"flexWrap": "wrap"}),
                html.Div(id="heat-cards", className="cards heat-cards"),
                html.Div(id="heat-hint", className="hint"),
                html.Div(id="heat-intraday-pane", children=[
                    dcc.Graph(config=GRAPH_CONFIG, id="heatmap-intraday",
                              figure=empty_fig("Cargando matriz intradiaria...", height=560)),
                ]),
                html.Div(id="heat-bubbles-pane", style={"display": "none"}, children=[
                    dcc.Graph(config=GRAPH_CONFIG, id="heatmap-bubbles",
                              figure=empty_fig("Cargando burbujas de contratos...", height=560)),
                ]),
                html.Div(id="heat-term-pane", style={"display": "none"}, children=[
                    dcc.Graph(config=GRAPH_CONFIG, id="heatmap-term",
                              figure=empty_fig("Cargando estructura temporal...", height=560)),
                ]),
                html.Div(id="heat-hist-pane", style={"display": "none"}, children=[
                    dcc.Graph(config=GRAPH_CONFIG, id="heatmap-hist",
                              figure=empty_fig("Cargando histórico multi-día...", height=560)),
                ]),
                html.Div(id="heat-overlay-pane", style={"display": "none"}, children=[
                    dcc.Graph(config=GRAPH_CONFIG, id="heatmap-overlay",
                              figure=empty_fig("Cargando perfil GEX & precio...", height=560)),
                ]),
            ]),

            html.Div(id="pane-pos", className="page-pane", style={"display": "none"}, children=[
                html.Div(id="pos-cards", className="cards pos-cards"),
                html.Div(id="pos-hint", className="hint"),
                html.Div([
                    dcc.RadioItems(
                        id="pos-sub", className="seg pos-seg",
                        options=[
                            {"label": "Distribucion OI", "value": "dist"},
                            {"label": "Variacion Diaria (ΔOI)", "value": "delta"},
                            {"label": "Historico (Walls & PCR)", "value": "hist"},
                        ],
                        value="dist", inline=True,
                    ),
                ], className="daybar pos-bar"),
                html.Div(id="pos-dist-pane", children=[
                    dcc.Graph(config=GRAPH_CONFIG, id="pos-dist-graph",
                              figure=empty_fig("Cargando distribución de Open Interest...", height=520)),
                ]),
                html.Div(id="pos-delta-pane", style={"display": "none"}, children=[
                    dcc.Graph(config=GRAPH_CONFIG, id="oi-change",
                              figure=empty_fig("Cargando variación diaria de Open Interest...", height=520)),
                ]),
                html.Div(id="pos-hist-pane", style={"display": "none"}, children=[
                    dcc.Graph(config=GRAPH_CONFIG, id="pos-hist-graph",
                              figure=empty_fig("Cargando histórico de Muros y PCR...", height=520)),
                ]),
            ]),

            html.Div(id="pane-tape", className="page-pane", style={"display": "none"}, children=[
                html.Div(id="tape-hint", className="hint"),
                html.Div([
                    html.Span(id="lbl-tape-size", className="ctl-label"),
                    dcc.RadioItems(id="tape-min-size", className="seg", inline=True,
                                   value=0),
                    dcc.Checklist(id="tape-combos", className="check", inline=True,
                                  value=["combos"]),
                ], className="daybar"),
                # Tableau reconstruit à chaque tick — pas un dcc.Graph : une
                # liste de transactions se lit comme un tableau, pas un tracé.
                html.Div(id="tape-table"),
            ]),

            html.Div(id="pane-analytics", className="page-pane", style={"display": "none"}, children=[
                html.Div(id="analytics-hint", className="hint"),
                html.Div([
                    dcc.RadioItems(
                        id="analytics-sub", className="seg analytics-seg",
                        options=[
                            {"label": "Volatility", "value": "vol"},
                            {"label": "Whale Tracker", "value": "whale"},
                            {"label": "By Expiry", "value": "expiry"},
                            {"label": "GEX Levels", "value": "levels"},
                        ],
                        value="vol", inline=True,
                    ),
                ], className="daybar analytics-bar"),
                # Sub-panes para cada sección del analytics
                html.Div(id="analytics-vol-pane", children=[
                    dcc.Graph(config=GRAPH_CONFIG, id="vol-surface",
                              figure=empty_fig("Cargando superficie de volatilidad...", height=420)),
                    dcc.Graph(config=GRAPH_CONFIG, id="iv-term-structure",
                              figure=empty_fig("Cargando estructura temporal IV...", height=420)),
                ]),
                html.Div(id="analytics-whale-pane", style={"display": "none"}, children=[
                    html.Div(id="whale-tracker"),
                ]),
                html.Div(id="analytics-expiry-pane", style={"display": "none"}, children=[
                    dcc.Graph(config=GRAPH_CONFIG, id="gex-by-expiry",
                              figure=empty_fig("Cargando GEX por expiración...", height=420)),
                    dcc.Graph(config=GRAPH_CONFIG, id="oi-by-expiry",
                              figure=empty_fig("Cargando OI por expiración...", height=420)),
                ]),
                html.Div(id="analytics-levels-pane", style={"display": "none"}, children=[
                    html.Div(id="levels-table-container"),
                ]),
            ]),

            html.Div(id="pane-report", className="page-pane", style={"display": "none"}, children=[
                html.Div(id="terminal-market-report"),
            ]),

            html.Div(id="pane-history", className="page-pane", style={"display": "none"}, children=[
                html.Div([
                    html.Span("LEVEL HISTORY", className="section-kicker"),
                    html.Span("Observed snapshot evolution; no inferred paths", className="section-note"),
                ], className="section-head"),
                html.Div([
                    html.Span("SESSION", className="ctl-label"),
                    dcc.Dropdown(id="level-history-day", clearable=False,
                                 options=[], className="dash-dropdown", style={"width": "200px"}),
                    html.Span("LEVEL TYPE", className="ctl-label"),
                    dcc.Dropdown(
                        id="level-history-types", className="dash-dropdown", multi=True,
                        options=[{"label": item.value.replace("_", " "), "value": item.value} for item in LevelType],
                        placeholder="All level types", style={"width": "260px"},
                    ),
                ], className="daybar"),
                dcc.Graph(id="level-history-chart", config=GRAPH_CONFIG,
                          figure=empty_fig("Select a session with saved snapshots.", height=560)),
            ]),

            html.Div(id="pane-diagnostics", className="page-pane", style={"display": "none"}, children=[
                html.Div(id="terminal-diagnostics"),
            ]),

            html.Div(id="pane-session", className="page-pane", style={"display": "none"}, children=[
                html.Div(id="terminal-session-profile"),
            ]),

            html.Div(id="pane-settings", className="page-pane", style={"display": "none"}, children=[
                html.Div([
                    html.Span("SETTINGS", className="section-kicker"),
                    html.Span("Terminal preferences", className="section-note"),
                ], className="section-head"),
                html.Div([
                    html.Section([
                        html.H3("Market context"),
                        html.Label("Underlying", htmlFor="settings-underlying"),
                        dcc.Dropdown(id="settings-underlying", className="dash-dropdown", clearable=False,
                                     options=[{"label": u.label, "value": u.key} for u in enabled], value=init_sym,
                                     persistence=True, persistence_type="local"),
                        html.Label("Display timezone", htmlFor="settings-display-timezone"),
                        dcc.Dropdown(
                            id="settings-display-timezone", className="dash-dropdown", clearable=False,
                            options=[
                                {"label": "New York (ET)", "value": "America/New_York"},
                                {"label": "Bogota (COT)", "value": "America/Bogota"},
                                {"label": "UTC", "value": "UTC"},
                            ], value="America/New_York", persistence=True, persistence_type="local",
                        ),
                        html.Label("Analysis expiration", htmlFor="settings-expiry-bucket"),
                        dcc.RadioItems(
                            id="settings-expiry-bucket", className="seg", inline=True,
                            options=[
                                {"label": "0DTE", "value": "0DTE"},
                                {"label": "Week", "value": "Semaine"},
                                {"label": "Month", "value": "Mois"},
                                {"label": "All", "value": "Tout"},
                            ],
                            value="Tout", persistence=True, persistence_type="local",
                        ),
                        html.Label("Market map window", htmlFor="settings-map-window"),
                        dcc.RadioItems(id="settings-map-window", className="seg", inline=True,
                                       options=[{"label": "±1%", "value": 1.0}, {"label": "±3%", "value": 3.0},
                                                {"label": "±5%", "value": 5.0}], value=3.0,
                                       persistence=True, persistence_type="local"),
                        html.Label("Neutral gamma threshold", htmlFor="settings-neutral-gex"),
                        dcc.Input(id="settings-neutral-gex", type="number", min=0, step=1_000_000,
                                  value=0, className="cfd-input", debounce=True,
                                  persistence=True, persistence_type="local"),
                        html.Label("Minimum wall strength", htmlFor="settings-wall-min-strength"),
                        dcc.RadioItems(
                            id="settings-wall-min-strength", className="seg", inline=True,
                            options=[{"label": "All", "value": 0}, {"label": "60+", "value": 60},
                                     {"label": "75+", "value": 75}, {"label": "90+", "value": 90}],
                            value=0, persistence=True, persistence_type="local",
                        ),
                    ], className="terminal-settings-section"),
                    html.Section([
                        html.H3("Update & scenarios"),
                        html.Label("Update interval", htmlFor="settings-update-seconds"),
                        dcc.RadioItems(id="settings-update-seconds", className="seg", inline=True,
                                       options=[{"label": "3s", "value": 3}, {"label": "5s", "value": 5},
                                                {"label": "10s", "value": 10}, {"label": "30s", "value": 30}],
                                       value=10, persistence=True, persistence_type="local"),
                        html.Label("Scenario limit", htmlFor="settings-scenario-limit"),
                        dcc.RadioItems(id="settings-scenario-limit", className="seg", inline=True,
                                       options=[{"label": "3", "value": 3}, {"label": "5", "value": 5},
                                                {"label": "8", "value": 8}], value=5,
                                       persistence=True, persistence_type="local"),
                        html.Label("Session value area", htmlFor="settings-value-area"),
                        dcc.RadioItems(id="settings-value-area", className="seg", inline=True,
                                       options=[{"label": "68%", "value": 0.68}, {"label": "70%", "value": 0.70},
                                                {"label": "80%", "value": 0.80}], value=0.70,
                                       persistence=True, persistence_type="local"),
                    ], className="terminal-settings-section"),
                    html.Section([
                        html.H3("Alerts"),
                        html.Label("Market alerts", htmlFor="settings-alerts-enabled"),
                        dcc.Checklist(
                            id="settings-alerts-enabled", className="check",
                            options=[{"label": "Enable meaningful market events", "value": "enabled"}],
                            value=[], persistence=True, persistence_type="local",
                        ),
                        html.Label("Strength change threshold", htmlFor="settings-alert-strength"),
                        dcc.Input(id="settings-alert-strength", type="number", min=1, max=100, step=1,
                                  value=15, debounce=True, persistence=True,
                                  persistence_type="local", className="terminal-number-input"),
                    ], className="terminal-settings-section"),
                    html.Section([
                        html.H3("Levels & appearance"),
                        html.Label("Visible level sources", htmlFor="settings-level-sources"),
                        dcc.Checklist(
                            id="settings-level-sources", className="check terminal-level-source-settings",
                            options=[
                                {"label": source.value.replace("_", " "), "value": source.value}
                                for source in LevelSource
                            ],
                            value=[source.value for source in LevelSource],
                            persistence=True, persistence_type="local",
                        ),
                        html.Label("Terminal accent", htmlFor="settings-terminal-accent"),
                        dcc.RadioItems(
                            id="settings-terminal-accent", className="terminal-accent-options", inline=True,
                            options=[
                                {"label": html.Span([html.Span(className="terminal-color-swatch terminal-color-swatch--blue"), " Blue"]), "value": "blue"},
                                {"label": html.Span([html.Span(className="terminal-color-swatch terminal-color-swatch--teal"), " Teal"]), "value": "teal"},
                                {"label": html.Span([html.Span(className="terminal-color-swatch terminal-color-swatch--gold"), " Gold"]), "value": "gold"},
                            ],
                            value="blue", persistence=True, persistence_type="local",
                        ),
                    ], className="terminal-settings-section"),
                ], className="terminal-settings-grid"),
            ]),

            dcc.Interval(id="tick", interval=10000),
            # le Tape doit défiler vivant, cadence 1s
            dcc.Interval(id="tape-tick", interval=1000),
            # le voyant du flux et les tuiles spot en temps réel (1s)
            # The quote stream is tick-level; rebuilding full Plotly figures
            # every second made browser requests overlap and caused visible
            # frame drops while panning. Three seconds keeps the UI responsive
            # without changing the underlying Tastytrade latency.
            dcc.Interval(id="rt-tick", interval=3000),
            dcc.Store(id="lang-boot", data=0),
            dcc.Store(id="cfd-offsets-store", storage_type="local", data={}),
            dcc.Store(id="cfd-active-offset", data=0.0),
            dcc.Store(id="cfd-modal-calc-diff-store", data=0.0),
            html.Div(id="footer", className="footer"),
            ], className="app-shell terminal-main"),
            terminal_intelligence_panel(),
        ], id="terminal-frame", className="terminal-frame"),
        terminal_statusbar(),
        dcc.Store(id="terminal-sidebar-state", data={"collapsed": False}, storage_type="local"),
        dcc.Store(id="native-alt"),  # "NDX" ou "SPY" : cible du bouton OK
        html.Div(id="native-overlay", className="native-overlay", style={"display": "none"}),
        # Modal Calculadora CFD
        html.Div(
            id="cfd-modal",
            className="cfd-modal-backdrop",
            style={"display": "none"},
            children=[
                html.Div([
                    html.Div([
                        html.H3(id="cfd-modal-title", children="Calculadora de Ajuste CFD"),
                        html.Button("✕", id="cfd-modal-close-icon", className="cfd-btn", style={"fontSize": "14px"}),
                    ], className="cfd-modal-header"),
                    html.P(id="cfd-modal-desc", className="cfd-modal-desc"),
                    html.Div([
                        html.Span(id="cfd-modal-fut-label", className="cfd-calc-label"),
                        html.Div(id="cfd-modal-fut-spot", className="cfd-calc-static-val"),
                    ], className="cfd-calc-row"),
                    html.Button("Obtener desde Yahoo Finance", id="cfd-modal-yahoo-btn", className="btn",
                                style={"margin": "2px 0 6px 0", "background": "rgba(46, 204, 113, 0.15)", "color": "var(--ok)", "border": "1px solid rgba(46, 204, 113, 0.35)", "fontWeight": "600", "fontSize": "13px"}),
                    html.Div([
                        html.Span(id="cfd-modal-cfd-label", className="cfd-calc-label"),
                        dcc.Input(
                            id="cfd-modal-target-input",
                            type="number",
                            step="any",
                            placeholder="0.00",
                            className="cfd-calc-field",
                            debounce=False,
                        ),
                    ], className="cfd-calc-row"),
                    html.Div([
                        html.Span(id="cfd-modal-diff-label", className="cfd-calc-label"),
                        html.Div(id="cfd-modal-diff-val", className="cfd-calc-result-val", children="0.00 pts"),
                    ], className="cfd-calc-result"),
                    html.Div([
                        html.Button(id="cfd-modal-close-btn", className="btn", style={"background": "var(--surface-2)"}),
                        html.Button(id="cfd-modal-apply-btn", className="btn"),
                    ], className="cfd-modal-actions"),
                ], className="cfd-modal-card"),
            ],
        ),
        # Modal Configuración API Tastytrade
        html.Div(
            id="tt-modal",
            className="tt-modal-backdrop",
            style={"display": "none"},
            children=[
                html.Div([
                    html.Div([
                        html.H3([
                            html.Span(id="tt-modal-title", children="Configuración API Tastytrade (Tiempo Real)"),
                        ], className="tt-modal-title"),
                        html.Button("✕", id="tt-modal-close-icon", className="cfd-btn", style={"fontSize": "14px"}, n_clicks=0),
                    ], className="tt-modal-header"),
                    html.P(id="tt-modal-desc", className="tt-modal-desc"),

                    # Status banner
                    html.Div([
                        html.Span(className="tt-status-dot"),
                        html.Span(id="tt-modal-status-text", children="Verificando estado..."),
                    ], id="tt-modal-status-banner", className="tt-status-banner tt-disconnected"),

                    # Alert message (for save confirmation or error)
                    html.Div(id="tt-modal-feedback", className="tt-msg-alert"),

                    # Input: Client ID
                    html.Div([
                        html.Span(id="tt-label-client-id", className="tt-label", children="Tastytrade Client ID"),
                        dcc.Input(
                            id="tt-input-client-id",
                            type="text",
                            value=init_cid,
                            placeholder="Pega aquí tu Client ID",
                            className="tt-input",
                            debounce=False,
                        ),
                    ], className="tt-input-group"),

                    # Input: Client Secret
                    html.Div([
                        html.Span(id="tt-label-client-secret", className="tt-label", children="Tastytrade Client Secret"),
                        dcc.Input(
                            id="tt-input-client-secret",
                            type="password",
                            value=init_sec,
                            placeholder="Pega aquí tu Client Secret",
                            className="tt-input",
                            debounce=False,
                        ),
                    ], className="tt-input-group"),

                    # Input: Refresh Token (Recomendado para conexión 100% directa)
                    html.Div([
                        html.Span(id="tt-label-refresh", className="tt-label", children="Refresh Token (Recomendado / Personal Grant)"),
                        dcc.Input(
                            id="tt-input-refresh-token",
                            type="password",
                            value=init_ref,
                            placeholder="Pega aquí el Refresh Token generado en Tastytrade",
                            className="tt-input",
                            debounce=False,
                        ),
                    ], className="tt-input-group"),

                    # Quick Guide box
                    html.Div([
                        html.Div(id="tt-guide-title", className="tt-guide-title", children="¿Cómo conectar Tastytrade sin errores?"),
                        html.Div(id="tt-step-1", children=[
                            html.B("Opción A (Recomendada - 100% Directa): "),
                            "En ", html.Code("my.tastytrade.com > Manage > My Profile > API > OAuth Applications"),
                            ", en tu aplicación haz clic en ", html.B("Manage > Create Grant"),
                            " y copia el ", html.B("Refresh Token"), " directamente aquí arriba."
                        ], style={"marginBottom": "6px"}),
                        html.Div(id="tt-step-3", children=[
                            html.B("Opción B (Login con Navegador): "),
                            "La ", html.B("Redirect URI"), " en Tastytrade debe ser EXACTAMENTE: ",
                            html.Code(tt_auth.redirect_uri(), className="tt-guide-code"),
                            " (si difiere, Tastytrade arrojará error 403 Forbidden)."
                        ]),
                    ], className="tt-guide-box"),

                    # Modal Action buttons
                    html.Div([
                        html.Div([
                            html.Button(id="tt-modal-disconnect-btn", className="tt-btn-danger", children="Desconectar", n_clicks=0),
                        ]),
                        html.Div([
                            html.Button(id="tt-modal-close-btn", className="tt-btn-secondary", children="Cerrar", style={"marginRight": "8px"}, n_clicks=0),
                            html.Button(id="tt-modal-save-btn", className="tt-btn-secondary", children="Solo Guardar", style={"marginRight": "8px"}, n_clicks=0),
                            html.Button(id="tt-modal-save-connect-btn", className="tt-btn-primary", children="Guardar y Conectar", n_clicks=0),
                        ], style={"display": "flex", "alignItems": "center"}),
                    ], className="tt-modal-actions"),
                ], className="tt-modal-card"),
            ],
        ),
        dcc.Location(id="tt-url-redirect", refresh=True),
        dcc.Store(id="tt-status-dummy-store", data=0),
    ])

    def _chip(children, accent):
        return html.Span(children, className="chip", style={"--chip-accent": accent})

    def levels_strip(levels: pd.DataFrame | None, lang: str,
                     hvl: float | None = None, zg: float | None = None,
                     xf=None, scale_note: str | None = None,
                     keys: dict | None = None) -> list:
        if levels is None or levels.empty:
            return [html.Span(t(lang, "levels_unavailable"),
                              style={"color": C["muted"], "fontSize": "12px"})]
        exp = levels["expiry"].iloc[0]
        labels = wall_labels(levels)
        xf = xf or (lambda v: v)
        today = datetime.now(ET).date()
        days_to_exp = (exp - today).days if isinstance(exp, date) else 0
        if days_to_exp <= 0:
            prefix = t(lang, "levels_prefix", exp=f"{exp:%d/%m}")
        elif days_to_exp <= 7:
            prefix = f"Niveles Semanales ({exp:%d/%m}):" if lang == "es" else f"Weekly Levels ({exp:%d/%m}):" if lang == "en" else f"Niveaux Hebdo ({exp:%d/%m}):"
        else:
            prefix = f"Niveles ({exp:%d/%m}):" if lang == "es" else f"Levels ({exp:%d/%m}):" if lang == "en" else f"Niveaux ({exp:%d/%m}):"

        items = [html.Span(prefix,
                           style={"color": C["muted"], "fontSize": "12px", "marginRight": "4px"})]
        if scale_note:
            items.append(html.Span(scale_note, className="scale-note"))
        if zg is not None:
            items.append(_chip([html.B("Gamma Flip ", style={"color": C["zg"]}),
                                f"{xf(zg):.0f}"], C["zg"]))
        if hvl is not None:
            items.append(_chip([html.B("HVL ", style={"color": C["hvl"]}),
                                f"{xf(hvl):.0f}"], C["hvl"]))
        # niveaux directionnels (support/résistance) et bornes de move attendu
        for key, color, label in (("call_wall", C["cw"], "Call Wall"),
                                  ("put_support", C["ps"], "Put Support"),
                                  ("d1_min", C["d1"], "1D Min"),
                                  ("d1_max", C["d1"], "1D Max")):
            v = (keys or {}).get(key)
            if v is not None:
                items.append(_chip([html.B(f"{label} ", style={"color": color}),
                                    f"{xf(v):.0f}"], color))
        for lv in levels.itertuples():
            side = t(lang, "side_call") if lv.gex > 0 else t(lang, "side_put")
            gex_val_str = f"{lv.gex / 1e9:+.2f} $Bn" if abs(lv.gex) >= 1e9 else f"{lv.gex / 1e6:+.1f} $M"
            items.append(_chip(
                [html.B(f"{labels[lv.strike]} ", style={"color": C["lvl"]}),
                 f"{xf(lv.strike):.0f} ",
                 html.Span(f"({gex_val_str} {side})",
                           style={"color": C["ink2"], "fontSize": "11px"})],
                "rgba(255,255,255,0.10)",
            ))
        return items

    # Détection de la langue du navigateur au chargement ; un choix manuel
    # (bouton ES/EN/FR) est mémorisé dans localStorage et prime sur la détection.
    app.clientside_callback(
        """
        function(_) {
            const saved = window.localStorage.getItem('gex-lang');
            if (saved === 'es' || saved === 'en' || saved === 'fr') return saved;
            const nav = (navigator.language || 'es').slice(0, 2).toLowerCase();
            return (nav === 'es' || nav === 'en' || nav === 'fr') ? nav : 'es';
        }
        """,
        Output("lang", "value"),
        Input("lang-boot", "data"),
    )
    app.clientside_callback(
        "function(l) { window.localStorage.setItem('gex-lang', l); return window.dash_clientside.no_update; }",
        Output("lang-boot", "data"),
        Input("lang", "value"),
        prevent_initial_call=True,
    )

    @app.callback(
        [Output("bucket", "options"), Output("majors", "options"),
         Output("flow-day-label", "children"), Output("flow-today", "children"),
         Output("footer", "children"), Output("unit", "options"),
         Output("app-title", "children"),
         Output("lbl-bucket", "children"), Output("lbl-window", "children"),
         Output("unit", "value"),
         Output("lbl-gflow-series", "children"), Output("gflow-series", "options"),
         Output("lbl-tape-series", "children"), Output("tape-series", "options"),
         Output("tape-note", "children"),
         Output("heat-levels-label", "children"), Output("heat-levels", "options"),
         Output("tape-hint", "children"), Output("lbl-tape-size", "children"),
         Output("tape-min-size", "options"), Output("tape-combos", "options"),
         Output("lbl-cfd", "children"), Output("cfd-offset-input", "placeholder"),
         Output("cfd-auto-btn", "title"), Output("cfd-reset-btn", "title"), Output("cfd-calc-btn", "title"),
         Output("cfd-modal-title", "children"), Output("cfd-modal-desc", "children"),
         Output("cfd-modal-fut-label", "children"), Output("cfd-modal-cfd-label", "children"),
         Output("cfd-modal-diff-label", "children"), Output("cfd-modal-apply-btn", "children"),
         Output("cfd-modal-close-btn", "children"), Output("cfd-modal-yahoo-btn", "children"),
         Output("pos-sub", "options"),
         Output("heat-sub", "options"),
         Output("heat-metric-label", "children"),
         Output("heat-metric", "options")],
        [Input("lang", "value"), Input("symbol", "value")],
    )
    def apply_lang(lang, symbol):
        bucket_opts = [{"label": t(lang, BUCKET_KEYS[b]), "value": b} for b in EXPIRY_BUCKETS]
        majors_opts = [{"label": t(lang, "majors_only"), "value": "on"}]
        gflow_series_opts = [{"label": t(lang, "legend_gcalls"), "value": "calls"},
                             {"label": t(lang, "legend_gputs"), "value": "puts"},
                             {"label": t(lang, "legend_gnet"), "value": "net"}]
        tape_series_opts = [{"label": t(lang, "legend_tape_net"), "value": "net"},
                            {"label": t(lang, "legend_tape_calls"), "value": "calls"},
                            {"label": t(lang, "legend_tape_puts"), "value": "puts"}]
        heat_levels_opts = [{"label": "Gamma Flip", "value": "zero_gamma"},
                           {"label": "HVL", "value": "hvl"},
                           {"label": "Call Wall", "value": "call_wall"},
                           {"label": "Put Support", "value": "put_support"},
                           {"label": "1D Min/Max", "value": "d1"},
                           {"label": t(lang, "heat_levels_gex_walls"), "value": "gex_walls"}]
        heat_sub_opts = [
            {"label": t(lang, "heat_sub_intraday"), "value": "intraday"},
            {"label": t(lang, "heat_sub_bubbles"), "value": "bubbles"},
            {"label": t(lang, "heat_sub_term"), "value": "term"},
            {"label": t(lang, "heat_sub_hist"), "value": "hist"},
            {"label": t(lang, "heat_sub_overlay"), "value": "overlay"},
        ]
        heat_metric_opts = [
            {"label": t(lang, "heat_metric_gex"), "value": "gex"},
            {"label": t(lang, "heat_metric_oi"), "value": "oi"},
            {"label": t(lang, "heat_metric_vol"), "value": "vol"},
        ]
        # échelles : le sous-jacent natif, puis les deux futures (la
        # transposition croisée SPX→NQ est le cas d'usage visé). Pour NQ/ES
        # eux-mêmes (chaîne native, pas transposée), la question ne se pose
        # pas : ce sont déjà les futures, un seul choix a du sens.
        # GLD/IBIT : familles propres (CM/CR), pas de transposition possible.
        u = UNDERLYINGS.get(symbol)
        if symbol in ("NQ", "ES"):
            opts = [{"label": t(lang, "unit_futures"), "value": symbol}]
        elif u and u.family not in ("SP", "ND"):
            # Commodities, Crypto — pas de transposition vers ES/NQ
            opts = [{"label": symbol, "value": symbol}]
        else:
            native_label = (t(lang, "unit_index")
                            if u and u.future else symbol)
            opts = [{"label": native_label, "value": symbol},
                    {"label": "ES", "value": "ES"},
                    {"label": "NQ", "value": "NQ"}]
        # seuils de taille : Tout, puis des paliers qui isolent progressivement
        # les blocs. En contrats — la même unité que la colonne « taille ».
        tape_size_opts = [{"label": t(lang, "tape_size_all"), "value": 0},
                          {"label": "≥ 10", "value": 10},
                          {"label": "≥ 50", "value": 50},
                          {"label": "≥ 100", "value": 100}]
        tape_combos_opts = [{"label": t(lang, "tape_show_combos"), "value": "combos"}]
        return (bucket_opts, majors_opts, t(lang, "flow_day_label"),
                t(lang, "last_session"), t(lang, "footer"), opts,
                t(lang, "app_title"),
                t(lang, "lbl_expiry"), t(lang, "lbl_window"), symbol,
                t(lang, "gflow_series_label"), gflow_series_opts,
                t(lang, "tape_series_label"), tape_series_opts,
                t(lang, "tape_note"),
                t(lang, "heat_levels_label"), heat_levels_opts,
                t(lang, "tape_hint"), t(lang, "tape_size_label"),
                tape_size_opts, tape_combos_opts,
                t(lang, "lbl_cfd"), t(lang, "cfd_placeholder"),
                t(lang, "cfd_auto_title"), t(lang, "cfd_reset_title"), t(lang, "cfd_calc"),
                t(lang, "cfd_calc_title", sym=symbol),
                t(lang, "cfd_calc_desc"),
                t(lang, "cfd_calc_fut_spot"),
                t(lang, "cfd_calc_cfd_spot"),
                t(lang, "cfd_calc_diff"),
                t(lang, "cfd_calc_apply", sym=symbol),
                t(lang, "cfd_calc_close"),
                t(lang, "cfd_calc_yahoo"),
                [{"label": t(lang, "pos_sub_dist"), "value": "dist"},
                 {"label": t(lang, "pos_sub_delta"), "value": "delta"},
                 {"label": t(lang, "pos_sub_hist"), "value": "hist"}],
                heat_sub_opts,
                t(lang, "heat_metric_label"),
                heat_metric_opts)

    @app.callback(
        [Output("cfd-offset-input", "value"),
         Output("cfd-offsets-store", "data"),
         Output("cfd-active-offset", "data"),
         Output("cfd-control-group", "className")],
        [Input("symbol", "value"),
         Input("cfd-offset-input", "value"),
         Input("cfd-auto-btn", "n_clicks"),
         Input("cfd-reset-btn", "n_clicks"),
         Input("cfd-modal-apply-btn", "n_clicks")],
        [State("cfd-offsets-store", "data"),
         State("cfd-modal-calc-diff-store", "data")],
    )
    def sync_cfd_offset(symbol, input_val, auto_clicks, reset_clicks, apply_clicks, store_data, diff_store):
        store_data = dict(store_data or {})
        trig = ctx.triggered_id

        if trig == "cfd-reset-btn":
            val = 0.0
            store_data[symbol] = 0.0
        elif trig == "cfd-auto-btn":
            st = chain_state(symbol)
            with STATE.lock:
                snap = st.snapshot if st else None
            base_spot = snap.spot if snap else 0.0
            live_px, _ = live_spot(symbol, base_spot)
            spot_ref = live_px if live_px else base_spot
            val = scales.get_auto_cfd_offset(symbol, spot_ref)
            store_data[symbol] = val
        elif trig == "cfd-modal-apply-btn" and diff_store is not None:
            val = float(diff_store)
            store_data[symbol] = val
        elif trig == "cfd-offset-input":
            val = float(input_val) if input_val is not None else 0.0
            store_data[symbol] = val
        else:
            val = float(store_data.get(symbol, 0.0) or 0.0)

        cls = "cfd-control-group cfd-active" if abs(val) > 1e-6 else "cfd-control-group"
        return (val if abs(val) > 1e-6 else None), store_data, val, cls

    @app.callback(
        [Output("cfd-modal", "style"),
         Output("cfd-modal-fut-spot", "children"),
         Output("cfd-modal-target-input", "value"),
         Output("cfd-modal-diff-val", "children"),
         Output("cfd-modal-calc-diff-store", "data")],
        [Input("cfd-calc-btn", "n_clicks"),
         Input("cfd-modal-yahoo-btn", "n_clicks"),
         Input("cfd-modal-close-icon", "n_clicks"),
         Input("cfd-modal-close-btn", "n_clicks"),
         Input("cfd-modal-apply-btn", "n_clicks"),
         Input("cfd-modal-target-input", "value")],
        [State("symbol", "value"),
         State("cfd-active-offset", "data"),
         State("cfd-modal-calc-diff-store", "data")],
    )
    def handle_cfd_modal(calc_clicks, yahoo_clicks, close_icon, close_btn, apply_clicks, target_val,
                         symbol, current_offset, current_diff):
        trig = ctx.triggered_id
        if not trig:
            raise PreventUpdate

        st = chain_state(symbol)
        with STATE.lock:
            snap = st.snapshot if st else None
        base_spot = snap.spot if snap else 0.0
        live_px, _ = live_spot(symbol, base_spot)
        spot_to_show = live_px if live_px else base_spot

        if trig == "cfd-calc-btn":
            init_target = round(spot_to_show + (current_offset or 0.0), 2) if spot_to_show else None
            diff = (init_target - spot_to_show) if init_target and spot_to_show else 0.0
            diff_str = f"{diff:+.2f} pts"
            return {"display": "flex"}, f"{spot_to_show:,.2f}", init_target, diff_str, diff

        elif trig == "cfd-modal-yahoo-btn":
            cfd_px = scales.get_yahoo_cfd_price(symbol)
            if cfd_px and cfd_px > 0 and spot_to_show > 0:
                diff = round(cfd_px - spot_to_show, 2)
                diff_str = f"{diff:+.2f} pts"
                return dash.no_update, f"{spot_to_show:,.2f}", cfd_px, diff_str, diff
            return dash.no_update, f"{spot_to_show:,.2f}", dash.no_update, dash.no_update, dash.no_update

        elif trig in ("cfd-modal-close-icon", "cfd-modal-close-btn", "cfd-modal-apply-btn"):
            return {"display": "none"}, f"{spot_to_show:,.2f}", dash.no_update, dash.no_update, dash.no_update

        elif trig == "cfd-modal-target-input":
            if target_val is not None and spot_to_show > 0:
                diff = float(target_val) - spot_to_show
                diff_str = f"{diff:+.2f} pts"
                return dash.no_update, f"{spot_to_show:,.2f}", dash.no_update, diff_str, diff
            else:
                return dash.no_update, f"{spot_to_show:,.2f}", dash.no_update, "0.00 pts", 0.0

        return dash.no_update, f"{spot_to_show:,.2f}", dash.no_update, dash.no_update, dash.no_update

    @app.callback(
        [Output("brand-sub", "children"), Output("rt-badge", "style"),
         Output("rt-badge", "className"), Output("rt-badge", "title"),
         Output("rt-label", "children"),
         Output("tt-connect", "style"), Output("tt-connect", "children"),
         Output("tt-connect", "title")],
        [Input("rt-tick", "n_intervals"), Input("lang", "value")],
    )
    def rt_status(_, lang):
        """Provenance du spot affiché, et pastille d'état du flux temps réel.

        Le badge reste masqué sur une installation sans identifiants courtier :
        inutile d'attirer l'œil sur une fonctionnalité non configurée. En
        revanche, si un compte est renseigné, l'état doit être explicite.
        """
        # La pastille suit rtquote : vert = flux actif (dxFeed connecté),
        # orange = secours CBOE (reconnexion dxFeed en cours), rouge = déconnecté.
        is_rt = credentials_present()
        if not is_rt:
            return (t(lang, "brand_sub"), {"display": "inline-flex", "cursor": "pointer"},
                    "rt-badge rt-disconnected", t(lang, "rt_disconnected") + " — Clic para configurar API",
                    "OFFLINE", {"display": "none"}, "", "")
        if not QUOTES._started:
            QUOTES.start()
        state, detail = QUOTES.status(market_open=market_is_open())
        badge_state = state if state in ("connected", "degraded") else "connected"
        conn_style = {"display": "none"}
        return (t(lang, "brand_sub_rt"), {"display": "inline-flex", "cursor": "pointer"},
                f"rt-badge rt-{badge_state}", "Tastytrade API Conectada — Tiempo Real Activo",
                "LIVE", conn_style, t(lang, "tt_connect"), "")

    @app.callback(
        [Output("native-banner", "children"), Output("native-banner", "style"),
         Output("native-overlay", "children"), Output("native-overlay", "style"),
         Output("native-alt", "data")],
        [Input("symbol", "value"), Input("lang", "value")],
    )
    def native_notice(symbol, lang):
        u = UNDERLYINGS.get(symbol)
        is_fut = symbol in ("NQ", "ES", "GC", "BTC") or (u and u.source == "futopt")
        if not is_fut or credentials_present():
            return "", {"display": "none"}, "", {"display": "none"}, None

        # NQ -> bascule vers NDX ; ES -> bascule vers SPY (ou SPX) ; GC/BTC -> SPX
        alt = "NDX" if symbol == "NQ" else "SPY" if symbol == "ES" else "SPX"
        banner = [
            html.Span("ℹ", style={"marginRight": "6px"}),
            html.Span(t(lang, "native_banner_text", sym=symbol, alt=alt)),
            html.Button(t(lang, "tt_configure_cta"),
                        className="btn-tt-api tt-open-trigger", style={"marginLeft": "12px", "padding": "2px 8px"}),
            html.A(t(lang, "native_banner_link"), href="/assets/faq.html#realtime",
                   target="_blank", style={"marginLeft": "10px"}),
        ]
        overlay = html.Div([
            html.H3(t(lang, "native_overlay_title", sym=symbol)),
            html.P(t(lang, "native_overlay_body", sym=symbol, alt=alt)),
            html.Div([
                html.Button(t(lang, "tt_configure_cta"),
                            className="btn tt-btn-primary tt-open-trigger", style={"marginRight": "10px"}),
                html.Button(t(lang, "native_overlay_ok", alt=alt),
                            id="native-overlay-ok", n_clicks=0, className="btn"),
            ], style={"display": "flex", "alignItems": "center", "marginBottom": "12px"}),
            html.A(t(lang, "native_overlay_link"), href="/assets/faq.html#realtime",
                   target="_blank", style={"display": "block"}),
        ], className="native-overlay-card")
        return banner, {}, overlay, {}, alt

    @app.callback(
        Output("symbol", "value"),
        Input("native-overlay-ok", "n_clicks"),
        State("native-alt", "data"),
        prevent_initial_call=True,
    )
    def native_overlay_dismiss(n_clicks, alt):
        if not n_clicks or not alt:
            raise PreventUpdate
        return alt

    @app.callback(
        [Output("cards", "children"), Output("regime-banner", "children"),
         Output("pc-gauge", "children")],
        [Input("rt-tick", "n_intervals"), Input("symbol", "value"),
         Input("lang", "value"), Input("unit", "value"),
         Input("cfd-active-offset", "data")],
    )
    def refresh_cards(_, symbol, lang, unit, cfd_offset):
        """Tuiles au rythme du flux (5 s) et non des pulls (60 s).

        Le GEX net y est recalculé au spot courant : c'est la valeur qui dit
        si le marché est amorti ou amplifié, et elle se périme en quelques
        minutes. Le recalcul porte sur un seul point de spot, donc son coût
        est négligeable devant la grille de 161 points du Gamma Flip.
        """
        cfd_off = float(cfd_offset or 0.0)
        xf, _, _ = _transform_for(symbol, unit, cfd_offset=cfd_off)
        return (build_cards(symbol, lang, xf, scale=unit), regime_banner(symbol, lang),
                pc_gauge(symbol, lang))

    @app.callback(
        [Output("levels", "children"), Output("gex-strike", "figure"),
         Output("dex-strike", "figure"), Output("flow", "figure"),
         Output("gflow", "figure"), Output("tape", "figure"),
         Output("gex-history", "figure"), Output("spot-zg", "figure"),
         Output("smile", "figure"), Output("tv-copy", "content"),
         Output("tv-copy", "title")],
        [Input("tick", "n_intervals"), Input("symbol", "value"),
         Input("bucket", "value"), Input("window", "value"),
         Input("majors", "value"), Input("flow-day", "value"),
         Input("lang", "value"), Input("unit", "value"),
         Input("gflow-series", "value"), Input("tape-series", "value"),
         Input("cfd-active-offset", "data")],
        [State("gex-strike", "relayoutData"),
         State("dex-strike", "relayoutData"),
         State("gex-strike", "figure"),
         State("dex-strike", "figure")],
    )
    def refresh(_, symbol, bucket, window, majors, flow_day, lang, unit, gflow_series,
                tape_series, cfd_offset, gex_relayout, dex_relayout,
                gex_current, dex_current):
        st = chain_state(symbol)
        with STATE.lock:
            df = st.enriched
            snap = st.snapshot
            summary = st.summary
        bucket_label = t(lang, BUCKET_KEYS[bucket])
        u_sym = UNDERLYINGS.get(symbol)
        is_fut = symbol in ("NQ", "ES", "GC", "BTC") or (u_sym and u_sym.source == "futopt")
        if df is None or snap is None:
            wait = t(lang, "waiting_native" if is_fut else "waiting_first_pull")
            return (
                levels_strip(None, lang),
                empty_fig(wait, guided(t(lang, "gex_title", bucket=bucket_label), "gex_strike")),
                empty_fig(wait, guided(t(lang, "dex_title", bucket=bucket_label), "dex_strike")),
                empty_fig(wait, t(lang, "flow_title")),
                empty_fig(wait, t(lang, "gflow_title")),
                empty_fig(wait, t(lang, "tape_title")),
                empty_fig(wait, t(lang, "hist_title")),
                empty_fig(wait, t(lang, "spotzg_title")),
                empty_fig(wait, t(lang, "smile_title")),
                "", t(lang, "tv_copy_title", scale=unit),
            )
        today = datetime.now(ET).date()
        sel = df[metrics.bucket_mask(df, bucket, today)]
        zg = summary.zero_gamma if summary and summary.zero_gamma else metrics.zero_gamma(df, snap.spot)

        # uirevision : tant que la révision ne change pas, Plotly conserve le
        # zoom/pan de l'utilisateur à travers les refresh de dcc.Interval.
        def _pin(fig, rev):
            fig.update_layout(uirevision=rev)
            return fig

        # transposition vers l'échelle d'affichage (voir gex/scales.py)
        cfd_off = float(cfd_offset or 0.0)
        xf, ratio, mode = _transform_for(symbol, unit, cfd_offset=cfd_off)
        note = _scale_note(lang, symbol, unit, ratio, mode, cfd_offset=cfd_off)
        rev = f"{symbol}-{bucket}-{window}-{unit}-{cfd_off}"
        preserve_zoom = ctx.triggered_id not in {
            "symbol", "bucket", "window", "unit", "cfd-active-offset",
        }
        # Plotly may send only one endpoint while the user is dragging. Merge
        # that partial event with the ranges in the figure already on screen;
        # otherwise the next interval response can restore the other axis.
        gex_effective_relayout = (
            merge_relayout_ranges(gex_relayout, gex_current)
            if preserve_zoom else None
        )
        dex_effective_relayout = (
            merge_relayout_ranges(dex_relayout, dex_current)
            if preserve_zoom else None
        )
        ref = ref_spot(symbol, snap.spot)
        # Le côté où chercher résistance et support suit le marché EN SÉANCE
        # seulement. Hors séance, un gap de futures invaliderait des murs avant
        # même l'ouverture du cash : le prix de référence reste alors celui de
        # la clôture, qui est l'état sur lequel le plan a été bâti.
        side_spot = snap.spot if market_is_open() else ref
        # Source UNIQUE des niveaux (cf. metrics.compute_levels) : murs classés au
        # spot structurel (clôture veille), côté au spot live, périmètre = bucket.
        _res = metrics.compute_levels(df, ref, side_spot, bucket=bucket)
        levels = _res["levels"]
        if majors and not levels.empty:
            # ne garde que les murs pesant au moins 25 % du plus fort
            levels = levels[levels["gex"].abs() >= 0.25 * levels["gex"].abs().max()]
        hvl = metrics.zero_gamma(df, snap.spot, weight_col="volume")
        keys = _res["keys"]
        scale_title_str = f"{unit} | CFD {cfd_off:+.1f}" if abs(cfd_off) > 1e-6 else unit
        
        # CORRECCIÓN: Usar spot en tiempo real en lugar de snap.spot para evitar discrepancias
        current_live_spot, is_live = live_spot(symbol, snap.spot)
        correct_spot = current_live_spot if is_live and current_live_spot > 0 else snap.spot
        
        return (
            levels_strip(levels, lang, hvl, zg, xf, note, keys),
            _pin(exposure_fig(sel, correct_spot, zg, "gex",
                              guided(t(lang, "gex_title", bucket=bucket_label), "gex_strike"), lang,
                              levels=levels, hvl=hvl, window=window, xf=xf,
                              keys=keys,
                              relayout=gex_effective_relayout), rev),
            _pin(exposure_fig(sel, correct_spot, zg, "dex",
                              guided(t(lang, "dex_title", bucket=bucket_label), "dex_strike"), lang,
                              hvl=hvl, window=window, xf=xf, keys=keys,
                              level_set="regime",
                              relayout=dex_effective_relayout), rev),
            _pin(flow_fig(symbol, lang, flow_day), f"{symbol}-{flow_day}"),
            _pin(gamma_flow_fig(symbol, lang, flow_day, gflow_series),
                f"g{symbol}-{flow_day}-{gflow_series}"),
            _pin(tape_fig(symbol, lang, flow_day, tape_series),
                f"t{symbol}-{flow_day}-{tape_series}"),
            _pin(history_fig(symbol, lang), symbol),
            _pin(spot_zg_fig(symbol, lang), symbol),
            _pin(smile_fig(sel, snap.spot, lang), rev),
            tv_levels_string(levels, hvl, zg, keys, xf),
            t(lang, "tv_copy_title", scale=scale_title_str),
        )

    @app.callback(
        [Output("overlay-day", "options"), Output("overlay-day", "value")],
        Input("symbol", "value"), State("overlay-day", "value"),
    )
    def overlay_days(symbol, current):
        days = available_overlay_days(symbol)
        if not days:
            return [], None
        today = datetime.now(ET).strftime("%Y-%m-%d")
        options = [
            {"label": f"{day} {'(en vivo / actual)' if day == today else '(sesión histórica)'}", "value": day}
            for day in reversed(days)
        ]
        default_day = today if today in days else days[-1]
        return options, default_day

    @app.callback(
        Output("options-flow-overlay", "figure"),
        [Input("rt-tick", "n_intervals"), Input("symbol", "value"),
         Input("overlay-day", "value"), Input("bucket", "value"), Input("window", "value"), Input("unit", "value"),
         Input("overlay-timeframe", "value"),
         Input("overlay-flow-type", "value"), Input("overlay-min-premium", "value"),
         Input("overlay-min-volume", "value"),
         Input("overlay-flow-side", "value"), Input("overlay-flow-expiration", "value"),
         Input("overlay-flow-expiration-custom", "value"),
         Input("overlay-layers", "value"),
         Input("cfd-active-offset", "data")],
        [State("options-flow-overlay", "relayoutData"),
         State("options-flow-overlay", "figure")],
    )
    def refresh_options_overlay(
        _, symbol, day, bucket, window, unit, timeframe, flow_type, min_premium, min_volume,
        flow_side, flow_expiration, custom_expiration, overlay_layers, cfd_offset,
        relayout_data, current_figure,
    ):
        """Refresh only the primary price/GEX view at the real-time cadence."""
        preserve_zoom = ctx.triggered_id not in {
            "overlay-timeframe", "overlay-day", "symbol",
        }
        effective_relayout = (
            merge_relayout_ranges(relayout_data, current_figure)
            if preserve_zoom else None
        )
        today = datetime.now(ET).strftime("%Y-%m-%d")
        if not day:
            days = available_overlay_days(symbol)
            default_day = today if today in days else (days[-1] if days else today)
            day = default_day

        is_live_session = day == today
        # Una sesión histórica es inmutable: no se vuelve a leer ni se pierde
        # el zoom cada segundo por el tick del feed actual.
        if not is_live_session and ctx.triggered_id == "rt-tick":
            raise PreventUpdate

        chain = None
        base_spot = None
        summary = None
        current_spot = None

        if is_live_session:
            st = chain_state(symbol)
            with STATE.lock:
                chain, snap, summary = st.enriched, st.snapshot, st.summary
            if chain is not None and snap is not None:
                base_spot = snap.spot
                current_spot, _ = live_spot(symbol, base_spot)

        if chain is None or not current_spot:
            chain, base_spot = _chain_for_day(symbol, day)
            summary = None
            current_spot = base_spot

        # Si aún no hay datos para el día solicitado (mercado cerrado o sin snapshot),
        # buscamos la sesión más reciente disponible que sí tenga cadena completa
        if chain is None or not current_spot:
            days = available_overlay_days(symbol)
            for d in reversed(days):
                c, s = _chain_for_day(symbol, d)
                if c is not None and s:
                    chain, base_spot = c, s
                    day = d
                    current_spot = base_spot
                    is_live_session = (day == today)
                    break

        cfd_off = float(cfd_offset or 0.0)
        xf, _, _ = _transform_for(symbol, unit, cfd_offset=cfd_off)
        price_bars, previous_bars = overlay_price_series(symbol, day, timeframe or "2d")
        layer_flags = overlay_layer_flags(overlay_layers)
        if chain is None or not current_spot:
            return build_options_overlay_from_view_model(
                OptionsOverlayViewModel(
                    symbol=symbol,
                    price_series=price_bars,
                    previous_price_series=previous_bars,
                    current_price=None,
                    chain=None,
                    gamma_flip=None,
                    keys={},
                    day=day,
                    window=window,
                ),
                transform=xf,
                **layer_flags,
                relayout=effective_relayout,
                timeframe=timeframe or "2d",
            )

        ref = store.previous_close_spot(symbol, day=day) or base_spot
        # Una sesión histórica debe clasificar soporte/resistencia respecto de
        # SU cierre, no respecto al estado actual del mercado.
        side_spot = current_spot if (not is_live_session or market_is_open()) else ref
        level_result = metrics.compute_levels(chain, ref, side_spot, bucket=bucket)
        gamma_flip = metrics.zero_gamma(chain, ref)
        gex_levels = build_gex_levels(chain, current_spot, gamma_flip, level_result["keys"])
        snapshot_symbol = scheduler_native_key(symbol) if symbol in ("NQ", "ES") else symbol
        snapshots = store.load_day_snapshots(snapshot_symbol, day)
        if not snapshots and symbol in ("NQ", "ES"):
            fallback_key = "NDX" if symbol == "NQ" else "SPX"
            snapshots = store.load_day_snapshots(fallback_key, day)
        flow_bubbles = (
            overlay_flow_bubbles(
                symbol, current_spot, min_premium, min_volume, flow_type,
                flow_side, overlay_expiration_filter(flow_expiration, custom_expiration), window,
            )
            if is_live_session else []
        )

        fig = build_options_overlay_from_view_model(
            OptionsOverlayViewModel(
                symbol=symbol,
                price_series=price_bars,
                previous_price_series=previous_bars,
                current_price=current_spot,
                chain=chain,
                gamma_flip=gamma_flip,
                keys=level_result["keys"],
                day=day,
                window=window,
                gex_levels=gex_levels,
                flow_bubbles=flow_bubbles,
                snapshots=snapshots,
            ),
            transform=xf,
            **layer_flags,
            relayout=effective_relayout,
            timeframe=timeframe or "2d",
        )
        fig.update_layout(
            uirevision=f"overlay-{symbol}-{day}-{bucket}-{timeframe or '2d'}"
        )
        return fig

    @app.callback(
        Output("overlay-flow-expiration-custom-wrap", "style"),
        Input("overlay-flow-expiration", "value"),
    )
    def toggle_custom_overlay_expiration(expiration):
        return {} if expiration == "CUSTOM" else {"display": "none"}

    @app.callback(
        Output("tab", "value"),
        [Input({"type": "terminal-nav-link", "page": ALL}, "n_clicks"),
         Input("terminal-settings-shortcut", "n_clicks")],
        prevent_initial_call=True,
    )
    def navigate_terminal(_, __):
        """Navigate from the categorized keyboard-accessible terminal links."""
        triggered = ctx.triggered_id
        if triggered == "terminal-settings-shortcut":
            return "settings"
        if not isinstance(triggered, dict):
            raise PreventUpdate
        page = str(triggered.get("page", ""))
        if page not in TABS:
            raise PreventUpdate
        return page

    @app.callback(
        Output({"type": "terminal-nav-link", "page": ALL}, "className"),
        Input("tab", "value"),
    )
    def highlight_active_terminal_navigation(page):
        """Keep sidebar state aligned with both sidebar and tab navigation."""
        return [
            "terminal-nav-item terminal-nav-item--active"
            if value == page
            else "terminal-nav-item"
            for value in terminal_navigation_pages()
        ]

    @app.callback(
        Output("terminal-sidebar-state", "data"),
        Input("terminal-sidebar-toggle", "n_clicks"),
        State("terminal-sidebar-state", "data"),
        prevent_initial_call=True,
    )
    def toggle_terminal_sidebar(_, current):
        return {"collapsed": not bool((current or {}).get("collapsed", False))}

    @app.callback(
        Output("terminal-frame", "className"),
        Input("terminal-sidebar-state", "data"),
    )
    def apply_terminal_sidebar_state(current):
        return "terminal-frame terminal-frame--collapsed" if (current or {}).get("collapsed") else "terminal-frame"

    @app.callback(
        Output("terminal-frame", "style"),
        Input("settings-terminal-accent", "value"),
    )
    def apply_terminal_accent(accent):
        return terminal_accent_style(accent)

    @app.callback(
        Output("symbol", "value", allow_duplicate=True),
        Input("settings-underlying", "value"),
        prevent_initial_call=True,
    )
    def apply_settings_underlying(symbol):
        return symbol

    @app.callback(
        Output("bucket", "value", allow_duplicate=True),
        Input("settings-expiry-bucket", "value"),
        prevent_initial_call=True,
    )
    def apply_settings_expiry_bucket(bucket):
        return bucket if bucket in EXPIRY_BUCKETS else "Tout"

    @app.callback(
        [Output("tick", "interval"), Output("rt-tick", "interval")],
        Input("settings-update-seconds", "value"),
    )
    def apply_update_interval(seconds):
        interval_ms = max(int(seconds or 10), 3) * 1000
        return interval_ms, interval_ms

    @app.callback(
        [Output("terminal-market-state", "children"),
         Output("terminal-key-levels", "children"),
         Output("terminal-scenarios", "children"),
         Output("terminal-data-status", "children"),
         Output("terminal-status-symbol", "children"),
         Output("terminal-status-session", "children"),
         Output("terminal-status-timestamp", "children"),
         Output("workspace-summary", "children"),
         Output("terminal-market-report", "children"),
         Output("terminal-topbar-price", "children"),
         Output("terminal-topbar-change", "children"),
         Output("terminal-topbar-session", "children"),
         Output("terminal-topbar-expiry", "children"),
         Output("terminal-topbar-data", "children"),
         Output("terminal-topbar-updated", "children")],
        [Input("rt-tick", "n_intervals"), Input("symbol", "value"),
         Input("bucket", "value"), Input("settings-neutral-gex", "value"),
         Input("settings-scenario-limit", "value"), Input("settings-value-area", "value"),
         Input("settings-level-sources", "value"), Input("settings-wall-min-strength", "value"),
         Input("settings-display-timezone", "value")],
    )
    def refresh_terminal_intelligence(_, symbol, bucket, neutral_gex, scenario_limit, value_area, visible_sources, wall_min_strength, display_timezone):
        """Present the API's unified market snapshot without UI-side math."""
        snapshot = _market_intelligence(
            symbol,
            bucket,
            config=MarketIntelligenceConfig(
                neutral_gex_threshold=max(float(neutral_gex or 0), 0.0),
                max_scenarios=max(int(scenario_limit or 5), 0),
            ),
            session_config=SessionProfileConfig(value_area_fraction=float(value_area or 0.70)),
            level_config=LevelBuildConfig(min_wall_strength=max(min(int(wall_min_strength or 0), 100), 0)),
        )
        allowed_sources = set(visible_sources) if visible_sources is not None else {
            source.value for source in LevelSource
        }
        visible_levels = filter_levels(snapshot, sources=allowed_sources or {"__HIDDEN__"})
        return (
            *intelligence_view(snapshot, visible_levels, display_timezone),
            market_report_view(snapshot, display_timezone),
            *topbar_market_view(snapshot, bucket, display_timezone),
        )

    @app.callback(
        [Output("terminal-overview-briefing", "children"), Output("overview-market-map", "figure")],
        [Input("tab", "value"), Input("rt-tick", "n_intervals"), Input("symbol", "value"),
         Input("bucket", "value"), Input("settings-map-window", "value"),
         Input("settings-neutral-gex", "value"), Input("settings-scenario-limit", "value"),
         Input("settings-value-area", "value"), Input("settings-level-sources", "value"),
         Input("settings-wall-min-strength", "value"), Input("settings-display-timezone", "value")],
    )
    def refresh_overview(tab, _, symbol, bucket, map_window, neutral_gex, scenario_limit, value_area, visible_sources, wall_min_strength, display_timezone):
        if tab != "main":
            raise PreventUpdate
        snapshot = _market_intelligence(
            symbol,
            bucket,
            config=MarketIntelligenceConfig(
                neutral_gex_threshold=max(float(neutral_gex or 0), 0.0),
                max_scenarios=max(int(scenario_limit or 5), 0),
            ),
            session_config=SessionProfileConfig(value_area_fraction=float(value_area or 0.70)),
            level_config=LevelBuildConfig(min_wall_strength=max(min(int(wall_min_strength or 0), 100), 0)),
        )
        return overview_briefing_view(snapshot, display_timezone), _market_map_figure_for_display(
            symbol,
            bucket,
            map_window=float(map_window or 3.0),
            neutral_gex=float(neutral_gex or 0),
            scenario_limit=int(scenario_limit or 5),
            value_area=float(value_area or 0.70),
            visible_sources=visible_sources,
            wall_min_strength=int(wall_min_strength or 0),
        )

    @app.callback(
        Output("terminal-scenarios-page", "children"),
        [Input("tab", "value"), Input("rt-tick", "n_intervals"), Input("symbol", "value"),
         Input("bucket", "value"), Input("settings-neutral-gex", "value"),
         Input("settings-scenario-limit", "value"), Input("settings-value-area", "value"),
         Input("settings-wall-min-strength", "value"), Input("settings-display-timezone", "value")],
    )
    def refresh_scenarios_page(tab, _, symbol, bucket, neutral_gex, scenario_limit, value_area, wall_min_strength, display_timezone):
        if tab != "scenarios":
            raise PreventUpdate
        snapshot = _market_intelligence(
            symbol,
            bucket,
            config=MarketIntelligenceConfig(
                neutral_gex_threshold=max(float(neutral_gex or 0), 0.0),
                max_scenarios=max(int(scenario_limit or 5), 0),
            ),
            session_config=SessionProfileConfig(value_area_fraction=float(value_area or 0.70)),
            level_config=LevelBuildConfig(min_wall_strength=max(min(int(wall_min_strength or 0), 100), 0)),
        )
        return scenarios_view(snapshot, display_timezone)

    @app.callback(
        [Output("terminal-alerts", "children"), Output("terminal-alert-state", "data")],
        [Input("rt-tick", "n_intervals"), Input("symbol", "value"), Input("bucket", "value"),
         Input("settings-alerts-enabled", "value"), Input("settings-alert-strength", "value"),
         Input("settings-neutral-gex", "value"), Input("settings-wall-min-strength", "value")],
        State("terminal-alert-state", "data"),
    )
    def refresh_terminal_alerts(_, symbol, bucket, enabled_values, strength_threshold, neutral_gex, wall_min_strength, prior_state):
        """Keep alerts opt-in and preserve only monitor-emitted events for this browser."""
        nonlocal alert_monitor, alert_monitor_threshold
        enabled_alerts = "enabled" in (enabled_values or [])
        symbol = str(symbol or "").upper()
        if not enabled_alerts:
            alert_monitor.reset(symbol)
            return alerts_view((), enabled=False), {"enabled": False, "events": []}

        threshold = max(int(strength_threshold or 15), 1)
        if alert_monitor_threshold != threshold:
            alert_monitor = AlertMonitor(AlertConfig(strength_change_threshold=threshold))
            alert_monitor_threshold = threshold
        snapshot = _market_intelligence(
            symbol,
            bucket,
            config=MarketIntelligenceConfig(neutral_gex_threshold=max(float(neutral_gex or 0), 0.0)),
            level_config=LevelBuildConfig(min_wall_strength=max(min(int(wall_min_strength or 0), 100), 0)),
        )
        existing = prior_state.get("events", []) if isinstance(prior_state, dict) else []
        history = [event for event in existing if event.get("symbol") == symbol] if isinstance(existing, list) else []
        if snapshot is None:
            return alerts_view(history, enabled=True), {"enabled": True, "events": history}
        emitted = [alert.to_dict() for alert in alert_monitor.observe(snapshot)]
        history = (emitted + history)[:8]
        return alerts_view(history, enabled=True), {"enabled": True, "events": history}

    @app.callback(
        [Output("options-chain-expiration", "options"), Output("options-chain-expiration", "value")],
        [Input("tick", "n_intervals"), Input("symbol", "value")],
        State("options-chain-expiration", "value"),
    )
    def refresh_options_chain_expirations(_, symbol, selected):
        state = chain_state(symbol)
        with STATE.lock:
            chain = state.enriched
        expirations = available_expirations(chain)
        options = [{"label": "All expirations", "value": "ALL"}] + [
            {"label": expiration, "value": expiration}
            for expiration in expirations
        ]
        return options, selected if selected in {item["value"] for item in options} else "ALL"

    @app.callback(
        Output("options-chain-table", "children"),
        [Input("tick", "n_intervals"), Input("tab", "value"), Input("symbol", "value"),
         Input("options-chain-expiration", "value"), Input("options-chain-side", "value"),
         Input("options-chain-range", "value"), Input("options-chain-min-volume", "value"),
         Input("options-chain-min-oi", "value"), Input("options-chain-min-gex", "value"),
         Input("options-chain-min-delta", "value"), Input("settings-wall-min-strength", "value")],
    )
    def refresh_options_chain(_, tab, symbol, expiration, side, strike_range, min_volume, min_oi,
                              min_gex, min_delta, wall_min_strength):
        if tab != "options":
            raise PreventUpdate
        state = chain_state(symbol)
        with STATE.lock:
            chain, summary = state.enriched, state.summary
        if chain is None or summary is None:
            return options_chain_view(None)
        snapshot = _market_intelligence(
            symbol, "Tout",
            level_config=LevelBuildConfig(min_wall_strength=max(min(int(wall_min_strength or 0), 100), 0)),
        )
        payload = build_options_chain_payload(
            chain=valid_option_records(chain),
            spot=summary.spot,
            levels=snapshot.report.key_levels if snapshot is not None else (),
            config=OptionsChainConfig(
                expiration=None if expiration == "ALL" else expiration,
                strike_range_pct=max(float(strike_range or 0), 0.0),
                side=side or "ALL",
                min_volume=max(float(min_volume or 0), 0.0),
                min_open_interest=max(float(min_oi or 0), 0.0),
                min_abs_net_gex=max(float(min_gex or 0), 0.0),
                min_abs_delta=max(float(min_delta or 0), 0.0),
            ),
        )
        return options_chain_view(payload)

    @app.callback(
        [Output("level-history-day", "options"), Output("level-history-day", "value")],
        [Input("tick", "n_intervals"), Input("symbol", "value")],
        State("level-history-day", "value"),
    )
    def refresh_level_history_days(_, symbol, selected):
        preferred = scheduler_native_key(symbol)
        days = store.snapshot_days(preferred) or store.snapshot_days(symbol)
        options = [{"label": day, "value": day} for day in reversed(days)]
        valid = {item["value"] for item in options}
        return options, selected if selected in valid else (options[0]["value"] if options else None)

    @app.callback(
        Output("level-history-chart", "figure"),
        [Input("tab", "value"), Input("symbol", "value"), Input("level-history-day", "value"),
         Input("bucket", "value"), Input("level-history-types", "value")],
    )
    def refresh_level_history(tab, symbol, day, bucket, level_types):
        if tab != "history":
            raise PreventUpdate
        return build_level_history_figure(
            _market_level_history_payload(symbol, day, bucket), level_types=level_types,
        )

    @app.callback(
        Output("terminal-diagnostics", "children"),
        [Input("tab", "value"), Input("tick", "n_intervals")],
    )
    def refresh_diagnostics(tab, _):
        if tab != "diagnostics":
            raise PreventUpdate
        return diagnostics_view(_market_diagnostics_payload())

    @app.callback(
        Output("terminal-session-profile", "children"),
        [Input("tab", "value"), Input("tick", "n_intervals"), Input("symbol", "value"),
         Input("settings-value-area", "value")],
    )
    def refresh_session_profile(tab, _, symbol, value_area):
        if tab != "session":
            raise PreventUpdate
        return session_profile_view(_market_session_payload(
            symbol,
            config=SessionProfileConfig(value_area_fraction=float(value_area or 0.70)),
        ))

    @app.callback(
        Output("market-map-chart", "figure"),
        [Input("tab", "value"), Input("rt-tick", "n_intervals"), Input("symbol", "value"),
         Input("bucket", "value"), Input("settings-map-window", "value"),
         Input("settings-neutral-gex", "value"), Input("settings-scenario-limit", "value"),
         Input("settings-value-area", "value"), Input("settings-level-sources", "value"),
         Input("settings-wall-min-strength", "value")],
    )
    def refresh_market_map(tab, _, symbol, bucket, map_window, neutral_gex, scenario_limit, value_area, visible_sources, wall_min_strength):
        if tab != "map":
            raise PreventUpdate
        return _market_map_figure_for_display(
            symbol,
            bucket,
            map_window=float(map_window or 3.0),
            neutral_gex=float(neutral_gex or 0),
            scenario_limit=int(scenario_limit or 5),
            value_area=float(value_area or 0.70),
            visible_sources=visible_sources,
            wall_min_strength=int(wall_min_strength or 0),
        )

    @app.callback(
        [Output("unified-level-map", "figure"), Output("unified-level-table", "children")],
        [Input("tab", "value"), Input("rt-tick", "n_intervals"), Input("symbol", "value"),
         Input("bucket", "value"), Input("settings-neutral-gex", "value"),
         Input("settings-scenario-limit", "value"), Input("settings-value-area", "value"),
         Input("level-filter-type", "value"), Input("level-filter-source", "value"),
         Input("level-filter-session", "value"), Input("settings-level-sources", "value"),
         Input("settings-wall-min-strength", "value")],
    )
    def refresh_unified_levels(tab, _, symbol, bucket, neutral_gex, scenario_limit, value_area,
                               level_types, sources, sessions, visible_sources, wall_min_strength):
        if tab != "levels":
            raise PreventUpdate
        snapshot = _market_intelligence(
            symbol, bucket,
            config=MarketIntelligenceConfig(
                neutral_gex_threshold=max(float(neutral_gex or 0), 0.0),
                max_scenarios=max(int(scenario_limit or 5), 0),
            ),
            session_config=SessionProfileConfig(value_area_fraction=float(value_area or 0.70)),
            level_config=LevelBuildConfig(min_wall_strength=max(min(int(wall_min_strength or 0), 100), 0)),
        )
        source_set = set(visible_sources) if visible_sources is not None else {
            source.value for source in LevelSource
        }
        selected_sources = set(sources or ())
        selected_sources = selected_sources & source_set if selected_sources else source_set
        visible_levels = filter_levels(
            snapshot, level_types=level_types, sources=selected_sources or {"__HIDDEN__"}, sessions=sessions,
        )
        return build_level_map_figure(snapshot, visible_levels), levels_view(snapshot, visible_levels)

    @app.callback(
        Output("terminal-level-inspector", "children"),
        [Input({"type": "terminal-level", "level": ALL}, "n_clicks"),
         Input({"type": "terminal-level-page", "level": ALL}, "n_clicks")],
        [State("symbol", "value"), State("bucket", "value"), State("settings-wall-min-strength", "value")],
        prevent_initial_call=True,
    )
    def inspect_terminal_level(_, __, symbol, bucket, wall_min_strength):
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict):
            raise PreventUpdate
        snapshot = _market_intelligence(
            symbol, bucket,
            level_config=LevelBuildConfig(min_wall_strength=max(min(int(wall_min_strength or 0), 100), 0)),
        )
        if snapshot is None:
            return level_inspector_view(None)
        level_id = str(triggered.get("level", ""))
        selected = next((level for level in snapshot.report.key_levels if level.id == level_id), None)
        if selected is None:
            return level_inspector_view(None)
        return level_inspector_view(build_level_inspector_payload(
            level=selected,
            spot=snapshot.state.spot,
            related_levels=snapshot.report.key_levels,
            scenarios=snapshot.scenarios,
        ))

    @app.callback(
        Output("terminal-scenario-inspector", "children"),
        Input({"type": "terminal-scenario", "scenario": ALL}, "n_clicks"),
        [State("symbol", "value"), State("bucket", "value"), State("settings-wall-min-strength", "value")],
        prevent_initial_call=True,
    )
    def inspect_terminal_scenario(_, symbol, bucket, wall_min_strength):
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict):
            raise PreventUpdate
        snapshot = _market_intelligence(
            symbol, bucket,
            level_config=LevelBuildConfig(min_wall_strength=max(min(int(wall_min_strength or 0), 100), 0)),
        )
        if snapshot is None:
            return scenario_inspector_view(None)
        scenario_id = str(triggered.get("scenario", ""))
        selected = next((scenario for scenario in snapshot.scenarios if scenario.id == scenario_id), None)
        return scenario_inspector_view(selected)

    @app.callback(
        [Output(f"pane-{v}", "style") for v in TABS] +
        [Output(f"tabh-{v}", "label") for v in TABS] +
        [Output("workspace-title", "children")],
        [Input("tab", "value"), Input("lang", "value")],
    )
    def switch_tab(tab, lang):
        styles = [{"display": "block"} if v == tab else {"display": "none"} for v in TABS]
        labels = [t(lang, f"tab_{v}") for v in TABS]
        title = t(lang, f"tab_{tab}") if tab in TABS else "GAMMA"
        return styles + labels + [title]

    @app.callback(
        [Output("profile", "figure"), Output("profile-exp", "figure"),
         Output("profile-hint", "children")],
        [Input("tick", "n_intervals"), Input("tab", "value"), Input("symbol", "value"),
         Input("window", "value"), Input("lang", "value"), Input("unit", "value"),
         Input("cfd-active-offset", "data"), Input("profile-expiry", "value"),
         Input("profile-side", "value"), Input("profile-mode", "value")],
    )
    def refresh_profile(_, tab, symbol, window, lang, unit, cfd_offset, profile_expiry, profile_side, profile_mode):
        if tab != "profile":   # onglet masqué : rien à recalculer
            raise PreventUpdate
        st = chain_state(symbol)
        with STATE.lock:
            df, snap, summary = st.enriched, st.snapshot, st.summary
        if df is None or snap is None:
            e = empty_fig(t(lang, "waiting_first_pull"), t(lang, "profile_title"))
            return e, e, t(lang, "profile_hint")
        cfd_off = float(cfd_offset or 0.0)
        xf, _, _ = _transform_for(symbol, unit, cfd_offset=cfd_off)
        scoped = _profile_chain_for_display(df, profile_expiry or "Tout", profile_side or "ALL")
        absolute = profile_mode == "ABSOLUTE"
        zg = metrics.zero_gamma(scoped, snap.spot) if not absolute else None
        # fenêtre élargie : la courbe n'a d'intérêt que si elle montre le flip
        w = max(window, 0.06)
        active_buckets = tuple(EXPIRY_BUCKETS) if profile_expiry in (None, "Tout") else (profile_expiry,)
        return (profile_fig(scoped, snap.spot, zg, lang, w, xf, absolute=absolute),
                profile_by_expiry_fig(
                    _profile_chain_for_display(df, "Tout", profile_side or "ALL"),
                    snap.spot, lang, w, xf, buckets=active_buckets, absolute=absolute,
                ),
                t(lang, "profile_hint"))

    @app.callback(
        [Output("vex", "figure"), Output("cex", "figure"),
         Output("g2-cards", "children"), Output("g2-hint", "children")],
        [Input("tick", "n_intervals"), Input("tab", "value"), Input("symbol", "value"),
         Input("bucket", "value"), Input("window", "value"),
         Input("lang", "value"), Input("unit", "value"),
         Input("cfd-active-offset", "data")],
    )
    def refresh_greeks2(_, tab, symbol, bucket, window, lang, unit, cfd_offset):
        if tab != "greeks2":
            raise PreventUpdate
        st = chain_state(symbol)
        with STATE.lock:
            df, snap, summary = st.enriched, st.snapshot, st.summary
        if df is None or snap is None:
            e = empty_fig(t(lang, "waiting_first_pull"))
            return e, e, [], t(lang, "vex_hint")
        cfd_off = float(cfd_offset or 0.0)
        xf, _, _ = _transform_for(symbol, unit, cfd_offset=cfd_off)
        today = datetime.now(ET).date()
        sel = metrics.add_second_order(df[metrics.bucket_mask(df, bucket, today)], snap.spot)
        cards = [
            card(t(lang, "vex_card"), f"{sel['vex'].sum() / 1e9:+.2f} $Bn",
                 t(lang, "vex_title").split("(")[-1].rstrip(")")),
            card(t(lang, "cex_card"), f"{sel['cex'].sum() / 1e9:+.2f} $Bn",
                 t(lang, "cex_title").split("(")[-1].rstrip(")")),
        ]
        return (second_order_fig(sel, snap.spot, "vex", guided(t(lang, "vex_title"), "vex"), window, xf),
                second_order_fig(sel, snap.spot, "cex", guided(t(lang, "cex_title"), "cex"), window, xf),
                cards, t(lang, "vex_hint"))

    @app.callback(
        [Output("heat-day", "options"), Output("heat-day", "value"),
         Output("heat-day-label", "children")],
        [Input("symbol", "value"), Input("lang", "value"), Input("tab", "value")],
        State("heat-day", "value"),
    )
    def heat_days(symbol, lang, tab, current):
        days_set = set(store.snapshot_days(symbol))
        alt = "NDX" if symbol == "NQ" else "SPX" if symbol == "ES" else None
        if alt:
            days_set.update(store.snapshot_days(alt))
        days = sorted(list(days_set))
        if not days:
            days = [datetime.now(ET).strftime("%Y-%m-%d")]
        opts = [{"label": f"{d} (En vivo)" if d == days[-1] else f"{d} (Sesión pasada)", "value": d}
                for d in reversed(days)]
        value = current if current in days else days[-1]
        return opts, value, t(lang, "heat_day_label")

    @app.callback(
        [Output("heat-intraday-pane", "style"),
         Output("heat-bubbles-pane", "style"),
         Output("heat-term-pane", "style"),
         Output("heat-hist-pane", "style"),
         Output("heat-overlay-pane", "style"),
         Output("heat-controls-row", "style")],
        [Input("heat-sub", "value"), Input("tab", "value")],
    )
    def toggle_heat_sub(sub, tab):
        hide = {"display": "none"}
        show = {"display": "block"}
        show_ctl = {"display": "flex", "flexWrap": "wrap"}
        if tab != "heat":
            return hide, hide, hide, hide, hide, hide
        return (
            show if sub == "intraday" else hide,
            show if sub == "bubbles" else hide,
            show if sub == "term" else hide,
            show if sub == "hist" else hide,
            show if sub == "overlay" else hide,
            hide if sub == "hist" else show_ctl,
        )

    @app.callback(
        [Output("heat-cards", "children"),
         Output("heatmap-intraday", "figure"),
         Output("heatmap-bubbles", "figure"),
         Output("heatmap-term", "figure"),
         Output("heatmap-hist", "figure"),
         Output("heatmap-overlay", "figure"),
         Output("heat-hint", "children")],
        [Input("tick", "n_intervals"), Input("tab", "value"), Input("heat-sub", "value"),
         Input("symbol", "value"), Input("window", "value"), Input("lang", "value"),
         Input("unit", "value"), Input("heat-day", "value"), Input("heat-levels", "value"),
         Input("heat-metric", "value"), Input("cfd-active-offset", "data"),
         Input("heat-bubble-min", "value"), Input("heat-bubble-limit", "value")],
        [         State("heatmap-intraday", "relayoutData"),
         State("heatmap-intraday", "figure"),
         State("heatmap-overlay", "relayoutData"),
         State("heatmap-bubbles", "figure"),
         State("heatmap-term", "figure"),
         State("heatmap-hist", "figure"),
         State("heatmap-overlay", "figure")],
    )
    def refresh_heatmap(_, tab, heat_sub, symbol, window, lang, unit, day, levels_shown, metric, cfd_offset,
                        bubble_min, bubble_limit,
                        intraday_relayout, intraday_current, relayout,
                        cur_bubbles, cur_term, cur_hist, cur_overlay):
        # onglet masqué : ne pas relire une quarantaine de fichiers pour rien
        if tab != "heat":
            raise PreventUpdate
        cfd_off = float(cfd_offset or 0.0)
        xf, _, _ = _transform_for(symbol, unit, cfd_offset=cfd_off)
        day = day or datetime.now(ET).strftime("%Y-%m-%d")
        cards = build_heatmap_cards(symbol, lang, day, xf)
        intraday_effective_relayout = merge_relayout_ranges(
            intraday_relayout, intraday_current
        )
        # Una sola vista se calcula por actualización. Las vistas secundarias
        # preservan su figura hasta que el usuario las abre explícitamente.
        if heat_sub == "intraday":
            return (cards,
                    build_intraday_heatmap(
                        symbol, lang, day, window, xf, unit, levels_shown, metric,
                        intraday_effective_relayout,
                    ),
                    no_update, no_update, no_update, no_update, t(lang, "heat_hint"))
        if heat_sub == "bubbles":
            return (cards, no_update,
                    heatmap_bubbles_fig(
                        symbol, lang, day, window, xf, unit, levels_shown, metric,
                        min_size=float(bubble_min or 0), max_points=int(bubble_limit or 1500),
                    ),
                    no_update, no_update, no_update, t(lang, "heat_hint"))
        if heat_sub == "term":
            return (cards, no_update, no_update,
                    heatmap_term_fig(symbol, lang, day, window, xf, unit, levels_shown, metric),
                    no_update, no_update, t(lang, "heat_hint"))
        if heat_sub == "hist":
            return (cards, no_update, no_update, no_update,
                    heatmap_history_fig(symbol, lang, xf), no_update, t(lang, "heat_hint"))
        return (cards, no_update, no_update, no_update, no_update,
                heatmap_fig(symbol, lang, day, window, xf, unit, levels_shown, relayout),
                t(lang, "heat_hint"))

    @app.callback(
        [Output("pos-dist-pane", "style"),
         Output("pos-delta-pane", "style"),
         Output("pos-hist-pane", "style")],
        [Input("pos-sub", "value"), Input("tab", "value")],
    )
    def toggle_pos_sub(sub, tab):
        hide = {"display": "none"}
        show = {"display": "block"}
        if tab != "pos":
            return hide, hide, hide
        return (
            show if sub == "dist" else hide,
            show if sub == "delta" else hide,
            show if sub == "hist" else hide,
        )

    @app.callback(
        [Output("pos-cards", "children"),
         Output("pos-dist-graph", "figure"),
         Output("oi-change", "figure"),
         Output("pos-hist-graph", "figure"),
         Output("pos-hint", "children")],
        [Input("tick", "n_intervals"), Input("tab", "value"), Input("symbol", "value"),
         Input("window", "value"), Input("lang", "value"), Input("unit", "value"),
         Input("cfd-active-offset", "data")],
    )
    def refresh_positioning(_, tab, symbol, window, lang, unit, cfd_offset):
        if tab != "pos":
            raise PreventUpdate
        st = chain_state(symbol)
        with STATE.lock:
            df, snap, summary = st.enriched, st.snapshot, st.summary

        if df is None or df.empty:
            latest = store.load_latest_snapshot(symbol)
            if latest is not None:
                df = latest[0]

        cfd_off = float(cfd_offset or 0.0)
        xf, _, _ = _transform_for(symbol, unit, cfd_offset=cfd_off)

        cards = build_positioning_cards(symbol, lang, xf)
        hist_fig = pos_history_fig(symbol, lang, xf)

        if df is None or df.empty:
            empty = empty_fig(t(lang, "waiting_first_pull"))
            return cards, empty, empty, hist_fig, t(lang, "pos_hint")

        spot = snap.spot if snap else float(df["spot"].iloc[-1]) if "spot" in df.columns else 0.0
        live_px, _ = live_spot(symbol, spot)
        active_spot = live_px if live_px > 0 else spot
        max_pain = calc_max_pain(df)

        dist_fig = pos_distribution_fig(df, active_spot, lang, window=window, xf=xf, max_pain=max_pain)

        today = datetime.now(ET).strftime("%Y-%m-%d")
        prev = store.load_previous_snapshot(symbol, today)
        if prev is not None:
            prev_day, prev_df = prev
            chg = metrics.oi_change(prev_df, df)
            delta_fig = oi_change_fig(chg, active_spot, lang, prev_day, window, xf=xf, df_cur=df)
        else:
            delta_fig = oi_change_fig(pd.DataFrame(), active_spot, lang, today, window, xf=xf, df_cur=df)

        return cards, dist_fig, delta_fig, hist_fig, t(lang, "pos_hint")

    @app.callback(
        Output("tape-table", "children"),
        [Input("tape-tick", "n_intervals"), Input("tab", "value"),
         Input("symbol", "value"), Input("tape-min-size", "value"),
         Input("tape-combos", "value"), Input("lang", "value")],
    )
    def refresh_tape(_, tab, symbol, min_size, combos, lang):
        # ne se recalcule que lorsque l'onglet est ouvert : inutile de
        # reconstruire 60 lignes toutes les 2 s en arrière-plan
        if tab != "tape":
            raise PreventUpdate
        return tape_table(symbol, lang, min_size=float(min_size or 0),
                          include_combos=bool(combos))

    @app.callback(
        [Output("flow-day", "options"), Output("flow-day", "value")],
        [Input("symbol", "value"), Input("tick", "n_intervals")],
        State("flow-day", "value"),
    )
    def update_flow_days(symbol, _, current):
        days = available_flow_days(symbol)
        opts = [{"label": d, "value": d} for d in days]
        # sur un tick, ne pas écraser la sélection de l'utilisateur ;
        # sur changement de sous-jacent (ou sélection invalide), dernier jour
        if ctx.triggered_id == "tick" and current in days:
            return opts, current
        return opts, (days[-1] if days else None)

    @app.callback(
        Output("flow-day", "value", allow_duplicate=True),
        Input("flow-today", "n_clicks"),
        State("symbol", "value"),
        prevent_initial_call=True,
    )
    def back_to_today(_, symbol):
        today = datetime.now(ET).strftime("%Y-%m-%d")
        days = available_flow_days(symbol)
        # le jour courant s'il a des flux, sinon le plus récent disponible
        return today if today in days else (days[-1] if days else None)

    # ------------------------------------------------------------------
    # Analytics tab — callbacks
    # ------------------------------------------------------------------

    @app.callback(
        [Output("analytics-vol-pane", "style"),
         Output("analytics-whale-pane", "style"),
         Output("analytics-expiry-pane", "style"),
         Output("analytics-levels-pane", "style")],
        [Input("analytics-sub", "value"), Input("tab", "value")],
    )
    def toggle_analytics_sub(sub, tab):
        """N'affiche que le sous-panneau sélectionné du tab Analytics."""
        hide = {"display": "none"}
        show = {"display": "block"}
        if tab != "analytics":
            return hide, hide, hide, hide
        return (
            show if sub == "vol" else hide,
            show if sub == "whale" else hide,
            show if sub == "expiry" else hide,
            show if sub == "levels" else hide,
        )

    @app.callback(
        Output("analytics-hint", "children"),
        [Input("tab", "value"), Input("lang", "value")],
    )
    def analytics_hint(tab, lang):
        if tab != "analytics":
            raise PreventUpdate
        return t(lang, "analytics_hint")

    @app.callback(
        [Output("vol-surface", "figure"),
         Output("iv-term-structure", "figure")],
        [Input("tick", "n_intervals"), Input("tab", "value"),
         Input("analytics-sub", "value"), Input("symbol", "value"),
         Input("window", "value"), Input("lang", "value")],
    )
    def refresh_vol_analytics(_, tab, sub, symbol, window, lang):
        if tab != "analytics" or sub != "vol":
            raise PreventUpdate
        return vol_surface_fig(symbol, lang, window=window), iv_term_structure_fig(symbol, lang)

    @app.callback(
        Output("whale-tracker", "children"),
        [Input("tape-tick", "n_intervals"), Input("tab", "value"),
         Input("analytics-sub", "value"), Input("symbol", "value"),
         Input("lang", "value")],
    )
    def refresh_whale(_, tab, sub, symbol, lang):
        if tab != "analytics" or sub != "whale":
            raise PreventUpdate
        return whale_tracker_table(symbol, lang)

    @app.callback(
        [Output("gex-by-expiry", "figure"),
         Output("oi-by-expiry", "figure")],
        [Input("tick", "n_intervals"), Input("tab", "value"),
         Input("analytics-sub", "value"), Input("symbol", "value"),
         Input("lang", "value")],
    )
    def refresh_expiry_analytics(_, tab, sub, symbol, lang):
        if tab != "analytics" or sub != "expiry":
            raise PreventUpdate
        return gex_by_expiry_fig(symbol, lang), oi_by_expiry_fig(symbol, lang)

    @app.callback(
        Output("levels-table-container", "children"),
        [Input("tick", "n_intervals"), Input("tab", "value"),
         Input("analytics-sub", "value"), Input("symbol", "value"),
         Input("window", "value"), Input("lang", "value")],
    )
    def refresh_levels(_, tab, sub, symbol, window, lang):
        if tab != "analytics" or sub != "levels":
            raise PreventUpdate
        return levels_table(symbol, lang, window=window)


    @app.callback(
        [Output("tt-modal", "style"),
         Output("tt-input-client-id", "value"),
         Output("tt-input-client-secret", "value"),
         Output("tt-input-refresh-token", "value")],
        [Input("tt-modal-open-btn", "n_clicks"),
         Input("rt-badge", "n_clicks"),
         Input("tt-modal-close-icon", "n_clicks"),
         Input("tt-modal-close-btn", "n_clicks")],
        [State("tt-modal", "style"),
         State("tt-input-client-id", "value"),
         State("tt-input-client-secret", "value"),
         State("tt-input-refresh-token", "value")],
        prevent_initial_call=True,
    )
    def handle_tt_modal(open_clicks, rt_clicks, close_icon, close_btn, current_style, cur_cid, cur_sec, cur_ref):
        if shared_deployment:
            return {"display": "none"}, "", "", ""
        trig = ctx.triggered_id
        if trig in ("tt-modal-open-btn", "rt-badge"):
            return {"display": "flex"}, cur_cid or "", cur_sec or "", cur_ref or ""
        elif trig in ("tt-modal-close-icon", "tt-modal-close-btn"):
            return {"display": "none"}, cur_cid, cur_sec, cur_ref
        return current_style or {"display": "none"}, cur_cid, cur_sec, cur_ref

    @app.callback(
        [Output("tt-url-redirect", "href"),
         Output("tt-modal-feedback", "children"),
         Output("tt-modal-feedback", "style"),
         Output("tt-status-dummy-store", "data"),
         Output("tt-modal-close-btn", "n_clicks")],
        [Input("tt-modal-save-connect-btn", "n_clicks"),
         Input("tt-modal-save-btn", "n_clicks"),
         Input("tt-modal-disconnect-btn", "n_clicks")],
        [State("tt-input-client-id", "value"),
         State("tt-input-client-secret", "value"),
         State("tt-input-refresh-token", "value"),
         State("lang", "value"),
         State("tt-status-dummy-store", "data")],
        prevent_initial_call=True,
    )
    def handle_tt_actions(save_conn_clicks, save_clicks, disc_clicks, cid, sec, ref, lang, dummy_val):
        import logging
        log = logging.getLogger(__name__)
        
        trig = ctx.triggered_id
        dummy_val = (dummy_val or 0) + 1

        if shared_deployment:
            return (
                no_update,
                "This shared deployment uses server-managed market-data credentials.",
                {"display": "block", "background": "rgba(34, 211, 238, 0.10)", "color": C["info"], "border": f"1px solid {C['info']}"},
                dummy_val,
                0,
            )
        
        log.info(f"Acción Tastytrade iniciada: {trig}")
        
        if trig == "tt-modal-disconnect-btn":
            log.info("Desconectando credenciales Tastytrade")
            tt_auth.clear_credentials()
            msg = "Credenciales eliminadas correctamente. Los datos en tiempo real se han desactivado."
            return (
                no_update,
                msg,
                {"display": "block", "background": "rgba(240, 92, 124, 0.12)", "color": C["neg"], "border": f"1px solid {C['neg']}"},
                dummy_val,
                0
            )

        cid = (cid or "").strip()
        sec = (sec or "").strip()
        ref = (ref or "").strip() or None

        log.info(f"Validando credenciales - Client ID: {cid[:8]}...{cid[-4:] if len(cid) > 8 else cid} si existe")
        
        if not cid or not sec:
            err_msg = "Client ID y Client Secret son obligatorios. Por favor completa ambos campos."
            log.warning("Validación fallida: faltan credenciales")
            return (
                no_update,
                err_msg,
                {"display": "block", "background": "rgba(240, 92, 124, 0.12)", "color": C["neg"], "border": f"1px solid {C['neg']}"},
                dummy_val,
                0
            )

        tt_auth.save_credentials(cid, sec, ref, persist=False)
        log.info("Credenciales guardadas en memoria")

        if trig == "tt-modal-save-connect-btn":
            if ref:
                log.info("Validando token con Refresh Token directo")
                try:
                    from gex.adapters.market_data.rtquote import quote_token
                    quote_token()
                    log.info("Token validado exitosamente")
                    
                    from gex.adapters.external.tt_web import _demarrer_les_flux
                    _demarrer_les_flux()
                    log.info("Flujos de datos iniciados")
                    
                    success_msg = """Conexión exitosa con Tastytrade.
<br><br>
Token validado correctamente
Datos en tiempo real activados
Flujos iniciados: QUOTES, TAPE, CAPTURE
<br><br>
El modal se cerrará automáticamente en 3 segundos..."""
                    
                    return (
                        no_update,
                        success_msg,
                        {"display": "block", "background": "rgba(45, 212, 191, 0.12)", "color": C["pos"], "border": f"1px solid {C['pos']}"},
                        dummy_val,
                        1  # Cierra el modal
                    )
                except Exception as exc:
                    log.error(f"Error validando token: {exc}")
                    error_msg = f"""Error al validar con Tastytrade:
<br><br>
{str(exc)}
<br><br>
Verifica:
- Client ID correcto
- Client Secret correcto  
- Refresh Token válido y no expirado
<br><br>
Si el Refresh Token expiró, genera uno nuevo en my.tastytrade.com > Manage > My Profile > API > OAuth Applications > Manage > Create Grant"""
                    return (
                        no_update,
                        error_msg,
                        {"display": "block", "background": "rgba(240, 92, 124, 0.12)", "color": C["neg"], "border": f"1px solid {C['neg']}"},
                        dummy_val,
                        0
                    )
            else:
                log.info("Redirigiendo a OAuth sin Refresh Token")
                info_msg = """Redirigiendo a Tastytrade para autorización en navegador...
<br><br>
Sigue estos pasos:
1. Inicia sesión en Tastytrade
2. Aprueba el acceso de la aplicación
3. Serás redirigido automáticamente de vuelta
<br><br>
Nota: la Redirect URI debe coincidir con http://localhost:8080/oauth/callback"""
                return "/oauth/start", info_msg, {"display": "block", "background": "rgba(34, 211, 238, 0.10)", "color": C["info"], "border": f"1px solid {C['info']}"}, dummy_val, 0

        log.info("Credenciales guardadas sin conexión inmediata")
        save_msg = """Credenciales guardadas correctamente
<br><br>
Client ID y Client Secret almacenados
Haz clic en "Guardar y Conectar" para activar tiempo real"""
        return (
            no_update,
            save_msg,
            {"display": "block", "background": "rgba(45, 212, 191, 0.12)", "color": C["pos"], "border": f"1px solid {C['pos']}"},
            dummy_val,
            0
        )

    @app.callback(
        Output("tt-modal", "style"),
        [Input("tt-modal-close-btn", "n_clicks")],
        [State("tt-modal", "style")],
        prevent_initial_call=True,
    )
    def auto_close_modal_on_success(close_clicks, current_style):
        """Cierra el modal automáticamente cuando hay éxito de conexión"""
        if close_clicks:
            return {"display": "none"}
        return current_style or {"display": "none"}

    @app.callback(
        [Output("tt-modal-title", "children"),
         Output("tt-modal-desc", "children"),
         Output("tt-btn-text", "children"),
         Output("tt-label-client-id", "children"),
         Output("tt-label-client-secret", "children"),
         Output("tt-label-refresh", "children"),
         Output("tt-modal-save-connect-btn", "children"),
         Output("tt-modal-save-btn", "children"),
         Output("tt-modal-disconnect-btn", "children"),
         Output("tt-modal-close-btn", "children"),
         Output("tt-guide-title", "children"),
         Output("tt-step-1", "children"),
         Output("tt-step-3", "children"),
         Output("tt-modal-status-banner", "className"),
         Output("tt-modal-status-text", "children")],
        [Input("lang", "value"),
         Input("rt-tick", "n_intervals"),
         Input("tt-status-dummy-store", "data")],
    )
    def update_tt_modal_i18n(lang, _, __):
        etat, msg = connection_status()
        if etat == "connecte":
            banner_cls = "tt-status-banner tt-live"
            status_txt = t(lang, "tt_status_connected")
        elif etat == "deconnecte":
            banner_cls = "tt-status-banner tt-pending"
            status_txt = t(lang, "tt_status_degraded")
        else:
            banner_cls = "tt-status-banner tt-disconnected"
            status_txt = t(lang, "tt_status_absent")

        return (
            t(lang, "tt_modal_title"),
            t(lang, "tt_modal_desc"),
            t(lang, "tt_modal_btn"),
            t(lang, "tt_client_id_label"),
            t(lang, "tt_client_secret_label"),
            t(lang, "tt_refresh_token_label"),
            t(lang, "tt_btn_save_connect"),
            t(lang, "tt_btn_save"),
            t(lang, "tt_btn_disconnect"),
            t(lang, "tt_btn_close"),
            t(lang, "tt_guide_title"),
            t(lang, "tt_step_1"),
            t(lang, "tt_step_3"),
            banner_cls,
            status_txt,
        )

    register_api(app)
    register_oauth(app)

    @app.server.route("/healthz")
    def _healthz():
        """Health check del proceso, sin depender de feeds externos."""
        from flask import jsonify

        return jsonify({"status": "ok", "service": "gex-dashboard"})

    @app.server.route("/api/v1/<symbol>/chart/<name>.png")
    def _chart_png(symbol, name):
        """Graphique en PNG à la demande — n'importe lequel, pas juste la
        heatmap (cf. chart_png / CHART_NAMES). Consommé par le bot Discord."""
        from flask import Response, request
        lang = request.args.get("lang", "es")
        bucket = request.args.get("bucket", "Tout")
        window = request.args.get("window", type=float)   # ex. 0.02, sinon défaut
        scale = request.args.get("scale")                 # échelle d'affichage
        try:
            png = chart_png(symbol.upper(), name.lower(), lang, bucket, window, scale)
        except Exception:  # noqa: BLE001 — un rendu qui échoue ne doit pas 500 salement
            log.exception("Rendu PNG %s/%s", symbol, name)
            png = None
        if png is None:
            return Response(f"graphique indisponible : {name}", status=404)
        return Response(png, mimetype="image/png")

    return app
