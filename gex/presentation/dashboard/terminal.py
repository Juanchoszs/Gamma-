"""Terminal presentation primitives for the GAMMA market workspace.

This module deliberately consumes the normalized market-intelligence output.
It contains no option calculations, provider access, or persistence calls.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dash import html

from gex.application.market_intelligence.service import MarketIntelligenceSnapshot
from gex.domain.market.intelligence import MarketLevel, Scenario


_NAVIGATION: tuple[tuple[str, str, str], ...] = (
    ("main", "Overview", "MARKET"),
    ("map", "Market Map", "MARKET"),
    ("heat", "Heatmaps", "MARKET"),
    ("profile", "GEX & Gamma", "MARKET"),
    ("options", "Options Chain", "MARKET"),
    ("levels", "Levels", "MARKET"),
    ("scenarios", "Scenarios", "MARKET"),
    ("pos", "Positioning", "FLOW"),
    ("tape", "Options Flow", "FLOW"),
    ("greeks2", "Vanna & Charm", "VOLATILITY"),
    ("report", "Market Report", "ANALYSIS"),
    ("session", "Sessions & Profile", "STRUCTURE"),
    ("history", "Level History", "ANALYSIS"),
    ("analytics", "Analytics", "ANALYSIS"),
    ("settings", "Settings", "SYSTEM"),
    ("diagnostics", "Diagnostics", "SYSTEM"),
)

_NAV_SHORT = {
    "main": "OV", "map": "MM", "heat": "HM", "profile": "GP", "options": "OC", "levels": "LV", "scenarios": "SC",
    "pos": "PS", "tape": "OF", "greeks2": "VC", "report": "MR", "history": "LH",
    "session": "SP", "analytics": "AN", "settings": "SE", "diagnostics": "DG",
}

_ACCENT_TOKENS = {
    "blue": {"--color-info": "#22d3ee", "--color-info-rgb": "34, 211, 238", "--color-border-focus": "#22d3ee"},
    "teal": {"--color-info": "#2dd4bf", "--color-info-rgb": "45, 212, 191", "--color-border-focus": "#2dd4bf"},
    "gold": {"--color-info": "#f6c85f", "--color-info-rgb": "246, 200, 95", "--color-border-focus": "#f6c85f"},
}
_MARKET_TIMEZONE = ZoneInfo("America/New_York")


def terminal_navigation_pages() -> tuple[str, ...]:
    """Return sidebar page ids in the same order Dash pattern outputs use."""
    return tuple(value for value, _, _ in _NAVIGATION)


def terminal_accent_style(accent: str | None) -> dict[str, str]:
    """Return scoped accent tokens without changing market-semantic colors."""
    return _ACCENT_TOKENS.get(str(accent or "").lower(), _ACCENT_TOKENS["blue"]).copy()


def market_time_text(timestamp: datetime, display_timezone: str = "America/New_York") -> str:
    """Format a market timestamp in a chosen display zone without changing session logic."""
    try:
        timezone = ZoneInfo(display_timezone)
    except (TypeError, ZoneInfoNotFoundError):
        timezone = _MARKET_TIMEZONE
    market_timestamp = timestamp.replace(tzinfo=_MARKET_TIMEZONE) if timestamp.tzinfo is None else timestamp
    localized = market_timestamp.astimezone(timezone)
    label = "ET" if timezone.key == "America/New_York" else (localized.tzname() or display_timezone)
    return f"{localized:%H:%M:%S} {label}"


def terminal_sidebar() -> html.Aside:
    """Build the persistent terminal navigation without page-specific logic."""
    groups: dict[str, list[tuple[str, str]]] = {}
    for value, label, group in _NAVIGATION:
        groups.setdefault(group, []).append((value, label))
    return html.Aside([
        html.Div([
            html.Span("G", className="terminal-logo-mark", **{"aria-hidden": "true"}),
            html.Div([
                html.Span("GAMMA", className="terminal-logo-name"),
                html.Span("MARKET INTELLIGENCE", className="terminal-logo-sub"),
            ]),
            html.Button("‹", id="terminal-sidebar-toggle", className="terminal-sidebar-toggle",
                        n_clicks=0, title="Collapse navigation", **{"aria-label": "Collapse navigation"}),
        ], className="terminal-logo"),
        html.Nav([
            html.Div([
                html.Span(group, className="terminal-nav-group-title"),
                html.Div([
                    html.Button([
                        html.Span(_NAV_SHORT[value], className="terminal-nav-short", **{"aria-hidden": "true"}),
                        html.Span(label, className="terminal-nav-long"),
                    ], id={"type": "terminal-nav-link", "page": value},
                       className="terminal-nav-item" + (" terminal-nav-item--active" if value == "main" else ""),
                       n_clicks=0, title=f"Open {label}")
                    for value, label in pages
                ], className="terminal-nav-items"),
            ], className="terminal-nav-group")
            for group, pages in groups.items()
        ], className="terminal-navigation", **{"aria-label": "Market analysis navigation"}),
        html.Div("Data source health and freshness", className="terminal-system-note terminal-sidebar-footer"),
    ], className="terminal-sidebar")
def terminal_intelligence_panel() -> html.Aside:
    """Persistent right-side intelligence panel with callback-owned slots."""
    return html.Aside([
        html.Div([
            html.Div([
                html.Span("MARKET INTELLIGENCE", className="terminal-panel-kicker"),
                html.Span(id="terminal-data-status", className="terminal-data-status"),
            ], className="terminal-panel-heading"),
            html.Div(id="terminal-market-state"),
        ], className="terminal-intelligence-section"),
        html.Div([
            html.Div([
                html.Span("KEY LEVELS", className="terminal-panel-kicker"),
                html.Span("Live relevance", className="terminal-panel-meta"),
            ], className="terminal-panel-heading"),
            html.Div(id="terminal-key-levels", className="terminal-level-list"),
        ], className="terminal-intelligence-section"),
        html.Div([
            html.Div([
                html.Span("LEVEL INSPECTOR", className="terminal-panel-kicker"),
                html.Span("Select a level", className="terminal-panel-meta"),
            ], className="terminal-panel-heading"),
            html.Div(id="terminal-level-inspector", className="terminal-inspector"),
        ], className="terminal-intelligence-section"),
        html.Div([
            html.Div([
                html.Span("ACTIVE SCENARIOS", className="terminal-panel-kicker"),
                html.Span("Conditional", className="terminal-panel-meta"),
            ], className="terminal-panel-heading"),
            html.Div(id="terminal-scenarios", className="terminal-scenario-list"),
        ], className="terminal-intelligence-section terminal-intelligence-section--grow"),
        html.Div([
            html.Div([
                html.Span("MARKET ALERTS", className="terminal-panel-kicker"),
                html.Span("Opt-in", className="terminal-panel-meta"),
            ], className="terminal-panel-heading"),
            html.Div(id="terminal-alerts", className="terminal-alert-list"),
        ], className="terminal-intelligence-section"),
        html.Div([
            html.Div([
                html.Span("SCENARIO INSPECTOR", className="terminal-panel-kicker"),
                html.Span("Select a scenario", className="terminal-panel-meta"),
            ], className="terminal-panel-heading"),
            html.Div(id="terminal-scenario-inspector", className="terminal-inspector"),
        ], className="terminal-intelligence-section"),
    ], className="terminal-intelligence")


def terminal_statusbar() -> html.Footer:
    return html.Footer([
        html.Span(id="terminal-status-symbol", className="terminal-status-symbol"),
        html.Span(id="terminal-status-session"),
        html.Span(id="terminal-status-timestamp", className="terminal-status-timestamp"),
        html.Span("Analytics are deterministic; scores are not probabilities.", className="terminal-status-note"),
    ], className="terminal-statusbar")


def terminal_topbar_market() -> html.Div:
    """Persistent global market readout populated from MarketState."""
    return html.Div([
        _topbar_metric("PRICE", "terminal-topbar-price"),
        _topbar_metric("CHANGE", "terminal-topbar-change"),
        _topbar_metric("SESSION", "terminal-topbar-session"),
        _topbar_metric("EXPIRY", "terminal-topbar-expiry"),
        _topbar_metric("DATA", "terminal-topbar-data"),
        _topbar_metric("UPDATED", "terminal-topbar-updated"),
    ], className="terminal-topbar-market")


def topbar_market_view(
    snapshot: MarketIntelligenceSnapshot | None,
    bucket: str = "--",
    display_timezone: str = "America/New_York",
) -> tuple[str, str, str, str, str, str]:
    """Format globally visible fields from the normalized market snapshot."""
    if snapshot is None:
        return ("--", "--", "UNKNOWN", str(bucket), "WAITING", "--")
    state = snapshot.state
    change = state.price_change
    change_percent = state.price_change_percent
    if change is None or change_percent is None:
        change_text = "Unavailable"
    else:
        change_text = f"{change:+,.2f} ({change_percent:+.2f}%)"
    return (
        _price(state.spot),
        change_text,
        state.session.value.replace("_", " "),
        str(bucket),
        state.data_status.upper(),
        market_time_text(state.timestamp, display_timezone),
    )


def _topbar_metric(label: str, identifier: str) -> html.Div:
    return html.Div([
        html.Span(label, className="terminal-topbar-label"),
        html.Span(id=identifier, className="terminal-topbar-value"),
    ], className="terminal-topbar-metric")


def intelligence_view(
    snapshot: MarketIntelligenceSnapshot | None,
    levels: Iterable[MarketLevel] | None = None,
    display_timezone: str = "America/New_York",
) -> tuple:
    """Render normalized backend outputs for all persistent terminal slots."""
    if snapshot is None:
        waiting = html.Div("Waiting for a validated options snapshot.", className="terminal-empty")
        return (
            waiting,
            waiting,
            waiting,
            "WAITING",
            "MARKET DATA UNAVAILABLE",
            "",
            "",
            "",
        )

    state = snapshot.state
    report = snapshot.report
    state_children = html.Div([
        html.Div([
            html.Span("SPOT", className="terminal-metric-label"),
            html.Span(_price(state.spot), className="terminal-spot-value"),
        ], className="terminal-spot"),
        html.Div([
            _state_metric("Gamma regime", state.gamma_regime.value.replace("_", " ")),
            _state_metric("Structure", state.structure.value.replace("_", " ")),
            _state_metric("Session", state.session.value),
            _state_metric("Volatility", _volatility_text(state.implied_volatility)),
            _state_metric("Positioning", state.positioning.replace("_", " ")),
        ], className="terminal-state-grid"),
        html.Div([
            html.Span("Why", className="terminal-why-label"),
            html.Span(" ".join(state.reasons) or "No structural explanation is available yet.", className="terminal-why"),
        ], className="terminal-why-row"),
    ], className="terminal-state")
    visible_levels = tuple(levels) if levels is not None else report.key_levels
    levels = _level_rows(visible_levels[:7], state.spot)
    scenarios = _scenario_rows(snapshot.scenarios[:3])
    status = state.data_status.upper()
    timestamp = market_time_text(state.timestamp, display_timezone)
    return (
        state_children,
        levels,
        scenarios,
        status,
        state.symbol,
        state.session.value.replace("_", " "),
        timestamp,
        f"{state.symbol}  {timestamp}",
    )


def _state_metric(label: str, value: str) -> html.Div:
    return html.Div([
        html.Span(label, className="terminal-mini-label"),
        html.Span(value, className="terminal-mini-value"),
    ], className="terminal-state-metric")


def _volatility_text(implied_volatility: float | None) -> str:
    return f"IV {implied_volatility:.1%}" if implied_volatility is not None else "Unavailable"


def _level_rows(levels: Iterable[MarketLevel], spot: float) -> list[html.Div]:
    output: list[html.Div] = []
    for level in levels:
        distance = level.distance_percent
        if distance is None and spot:
            distance = ((level.price - spot) / spot) * 100.0
        output.append(html.Button([
            html.Div([
                html.Span(level.level_type.value.replace("_", " "), className="terminal-level-type"),
                html.Span(level.status.value.replace("_", " "), className="terminal-level-status"),
            ], className="terminal-level-top"),
            html.Div([
                html.Span(_price(level.price), className="terminal-level-price"),
                html.Span(_level_evidence(level), className="terminal-level-evidence"),
                html.Span(f"{distance:+.2f}%" if distance is not None else "", className="terminal-level-distance"),
                html.Span(f"{level.strength}/100", className="terminal-level-strength"),
            ], className="terminal-level-values"),
        ], id={"type": "terminal-level", "level": level.id},
           className="terminal-level", n_clicks=0, title=f"Inspect {level.level_type.value} {level.price:g}"))
    return output or [html.Div("No unified levels available.", className="terminal-empty")]


def _level_evidence(level: MarketLevel) -> str:
    """Compactly identify the source metric most relevant to a level."""
    if level.gamma is not None and abs(level.gamma) > 0:
        return f"GEX {_metric(level.gamma)}"
    if level.open_interest is not None and level.open_interest > 0:
        return f"OI {_metric(level.open_interest)}"
    if level.volume is not None and level.volume > 0:
        return f"VOL {_metric(level.volume)}"
    return ""


def _scenario_rows(scenarios) -> list[html.Button]:
    output: list[html.Button] = []
    for scenario in scenarios:
        output.append(html.Button([
            html.Div([
                html.Span(scenario.title, className="terminal-scenario-title"),
                html.Span(scenario.direction.value, className="terminal-scenario-direction"),
            ], className="terminal-scenario-summary"),
            html.Span(scenario.trigger, className="terminal-scenario-trigger"),
        ], id={"type": "terminal-scenario", "scenario": scenario.id},
           className="terminal-scenario", n_clicks=0, title=f"Inspect {scenario.title}"))
    return output or [html.Div("No conditional scenarios available.", className="terminal-empty")]


def scenario_inspector_view(scenario: Scenario | None) -> html.Div:
    """Render a selected conditional scenario without adding forecast claims."""
    if scenario is None:
        return html.Div("Select an active scenario to inspect its conditions.", className="terminal-empty")
    support = scenario.supporting_data
    key_level = scenario.key_level
    return html.Div([
        html.Div([
            html.Span(scenario.direction.value, className="terminal-inspector-title"),
            html.Span(key_level.level_type.value.replace("_", " ") if key_level else "SCENARIO",
                      className="terminal-panel-meta"),
        ], className="terminal-inspector-head"),
        html.Strong(scenario.title, className="terminal-scenario-inspector-title"),
        _scenario_inspector_field("Trigger", scenario.trigger),
        _scenario_inspector_field("Conditions", html.Ul([html.Li(item) for item in scenario.conditions])),
        _scenario_inspector_field("Next levels", ", ".join(
            f"{level.level_type.value.replace('_', ' ')} {_price(level.price)}" for level in scenario.next_levels
        ) or "No next level is currently available."),
        _scenario_inspector_field("Invalidation", scenario.invalidation),
        html.Div([
            _scenario_inspector_metric("Gamma", str(support.get("gamma_regime", "UNKNOWN")).replace("_", " ")),
            _scenario_inspector_metric("Structure", str(support.get("market_structure", "UNKNOWN")).replace("_", " ")),
            _scenario_inspector_metric("Level", str(support.get("level_status", "UNKNOWN")).replace("_", " ")),
        ], className="terminal-scenario-inspector-metrics"),
    ], className="terminal-scenario-inspector")


def scenarios_view(snapshot: MarketIntelligenceSnapshot | None, display_timezone: str = "America/New_York") -> html.Div:
    """Render the generated conditional scenarios as a full analytical view."""
    if snapshot is None:
        return html.Div("Waiting for a validated market snapshot.", className="terminal-report-empty")
    scenarios = snapshot.scenarios
    if not scenarios:
        return html.Div("No conditional scenarios are available.", className="terminal-report-empty")
    return html.Div([
        html.Div([
            html.Div([
                html.Span("SCENARIO ENGINE", className="terminal-report-kicker"),
                html.H2(f"{snapshot.state.symbol} conditional scenarios", className="terminal-report-title"),
                html.P(
                    "Conditions and structural implications derived from the current normalized market state.",
                    className="terminal-report-subtitle",
                ),
            ]),
            html.Div([
                _diagnostic_metric("REGIME", snapshot.state.gamma_regime.value.replace("_", " ")),
                _diagnostic_metric("STRUCTURE", snapshot.state.structure.value.replace("_", " ")),
                _diagnostic_metric("AS OF", market_time_text(snapshot.state.timestamp, display_timezone)),
            ], className="terminal-report-snapshot"),
        ], className="terminal-report-header"),
        html.Div([
            _scenario_card(scenario)
            for scenario in scenarios
        ], className="terminal-scenario-page-grid"),
    ], className="terminal-scenarios-page")


def _scenario_card(scenario: Scenario) -> html.Section:
    key_level = scenario.key_level
    support = scenario.supporting_data
    return html.Section([
        html.Div([
            html.Span(scenario.direction.value, className="terminal-report-scenario-direction"),
            html.Span(
                f"{key_level.level_type.value.replace('_', ' ')} {_price(key_level.price)}"
                if key_level else "MARKET STATE",
                className="terminal-panel-meta",
            ),
        ], className="terminal-scenario-page-head"),
        html.H3(scenario.title),
        _scenario_page_field("Trigger", scenario.trigger),
        _scenario_page_field("Conditions", html.Ul([html.Li(condition) for condition in scenario.conditions])),
        _scenario_page_field("Structural implication", scenario.structural_implication),
        _scenario_page_field("Next levels", ", ".join(
            f"{level.level_type.value.replace('_', ' ')} {_price(level.price)}"
            for level in scenario.next_levels
        ) or "No next level is currently available."),
        _scenario_page_field("Invalidation", scenario.invalidation),
        html.Div([
            _scenario_inspector_metric("Gamma", str(support.get("gamma_regime", "UNKNOWN")).replace("_", " ")),
            _scenario_inspector_metric("Structure", str(support.get("market_structure", "UNKNOWN")).replace("_", " ")),
            _scenario_inspector_metric("Level", str(support.get("level_status", "UNKNOWN")).replace("_", " ")),
        ], className="terminal-scenario-inspector-metrics"),
    ], className="terminal-scenario-page-card")


def _scenario_page_field(label: str, value) -> html.Div:
    return html.Div([html.Span(label, className="terminal-scenario-label"), value], className="terminal-scenario-page-field")


def alerts_view(events: Iterable[dict[str, object]], *, enabled: bool) -> html.Div:
    """Render only alert events emitted by the deterministic monitor."""
    if not enabled:
        return html.Div("Disabled", className="terminal-alert-empty")
    entries = list(events)
    if not entries:
        return html.Div("No recent meaningful events.", className="terminal-alert-empty")
    return html.Div([
        html.Div([
            html.Div([
                html.Span(str(event.get("kind", "EVENT")).replace("_", " "),
                          className="terminal-alert-kind"),
                html.Span(_alert_time(event.get("timestamp")), className="terminal-alert-time"),
            ], className="terminal-alert-head"),
            html.Div(str(event.get("message", "")), className="terminal-alert-message"),
        ], className="terminal-alert")
        for event in entries
    ], className="terminal-alert-events")


def _alert_time(value: object) -> str:
    if not value:
        return ""
    text = str(value).replace("T", " ")
    return text[11:19] if len(text) >= 19 else text


def _scenario_inspector_field(label: str, value) -> html.Div:
    return html.Div([html.Span(label, className="terminal-scenario-label"), value], className="terminal-scenario-inspector-field")


def _scenario_inspector_metric(label: str, value: str) -> html.Div:
    return html.Div([html.Span(label), html.Strong(value)])


def level_inspector_view(payload: dict | None) -> html.Div:
    """Render the inspector payload produced by the application layer."""
    if not payload:
        return html.Div("Select a key level to inspect its source metrics.", className="terminal-empty")
    summary = payload["summary"]
    metrics = payload.get("metrics", {})
    context = payload.get("context", {})
    rows = [
        ("Strength", f"{summary['strength']}/100"),
        ("Status", summary["status"].replace("_", " ")),
        ("Source", summary.get("source", "UNKNOWN").replace("_", " ")),
        ("Session", summary.get("session", "UNKNOWN")),
        ("Position", context.get("position", "UNKNOWN").replace("_", " ")),
    ]
    if summary.get("distance_percent") is not None:
        rows.append(("Distance", f"{float(summary['distance_percent']):+.2f}%"))
    if context.get("spot") is not None:
        rows.append(("Spot", _price(float(context["spot"]))))
    for key, label in (("open_interest", "Open interest"), ("volume", "Volume"),
                       ("gamma", "Gamma"), ("delta", "Delta"),
                       ("vanna", "Vanna"), ("charm", "Charm")):
        if key in metrics:
            rows.append((label, _metric(metrics[key])))
    if metrics.get("expiration"):
        rows.append(("Expiration", _format_expiration(metrics["expiration"])))
    nearest_below = context.get("nearest_below")
    nearest_above = context.get("nearest_above")
    if isinstance(nearest_below, dict):
        rows.append(("Below", _level_reference_text(nearest_below)))
    if isinstance(nearest_above, dict):
        rows.append(("Above", _level_reference_text(nearest_above)))
    related_scenarios = context.get("related_scenarios", [])
    if related_scenarios:
        rows.append(("Scenarios", "; ".join(
            str(item.get("title", item.get("id", "SCENARIO")))
            for item in related_scenarios if isinstance(item, dict)
        )))
    return html.Div([
        html.Div([
            html.Span(summary["type"].replace("_", " "), className="terminal-inspector-title"),
            html.Span(_price(float(summary["price"])), className="terminal-inspector-price"),
        ], className="terminal-inspector-head"),
        html.Div([
            html.Div([html.Span(label), html.Span(value)])
            for label, value in rows
        ], className="terminal-inspector-metrics"),
        html.Div("Strength is a deterministic score based only on available source metrics.",
                 className="terminal-inspector-note"),
    ], className="terminal-inspector-content")


def _format_expiration(value: object) -> str:
    text = str(value).replace("T", " ")
    return text[:10] if len(text) >= 10 else text


def _level_reference_text(reference: dict) -> str:
    try:
        price = _price(float(reference["price"]))
    except (KeyError, TypeError, ValueError):
        price = "Unavailable"
    level_type = str(reference.get("type", "LEVEL")).replace("_", " ")
    return f"{level_type} {price}"


def filter_levels(
    snapshot: MarketIntelligenceSnapshot | None,
    *,
    level_types: Iterable[str] | None = None,
    sources: Iterable[str] | None = None,
    sessions: Iterable[str] | None = None,
) -> tuple[MarketLevel, ...]:
    """Apply display-only filters to normalized report levels."""
    if snapshot is None:
        return ()
    accepted_types = set(level_types or ())
    accepted_sources = set(sources or ())
    accepted_sessions = set(sessions or ())
    return tuple(level for level in snapshot.report.key_levels if (
        (not accepted_types or level.level_type.value in accepted_types)
        and (not accepted_sources or level.source.value in accepted_sources)
        and (not accepted_sessions or level.session.value in accepted_sessions)
    ))


def levels_view(snapshot: MarketIntelligenceSnapshot | None, levels: Iterable[MarketLevel] | None = None) -> html.Div:
    """Render the normalized key-level table without changing its ranking."""
    visible_levels = tuple(levels) if levels is not None else (snapshot.report.key_levels if snapshot else ())
    if snapshot is None or not visible_levels:
        return html.Div("No unified levels are available.", className="terminal-report-empty")
    rows = []
    for level in visible_levels:
        distance = level.distance_percent
        if distance is None and snapshot.state.spot:
            distance = (level.price - snapshot.state.spot) / snapshot.state.spot * 100.0
        rows.append(html.Tr([
            html.Td(html.Button(level.level_type.value.replace("_", " "),
                                id={"type": "terminal-level-page", "level": level.id}, n_clicks=0,
                                className="terminal-level-table-link", title=f"Inspect {level.id}")),
            html.Td(_price(level.price)),
            html.Td(f"{distance:+.2f}%" if distance is not None else "--"),
            html.Td(f"{level.strength}/100"),
            html.Td(level.status.value.replace("_", " ")),
            html.Td(level.source.value.replace("_", " ")),
            html.Td(level.session.value),
        ]))
    return html.Div([
        html.Table([
            html.Thead(html.Tr([html.Th(label) for label in ("Level", "Price", "Distance", "Strength", "Status", "Source", "Session")])),
            html.Tbody(rows),
        ], className="terminal-level-table"),
    ], className="terminal-level-table-scroll")


def market_report_view(snapshot: MarketIntelligenceSnapshot | None, display_timezone: str = "America/New_York") -> html.Div:
    """Render the automatic report as a focused analytical page."""
    if snapshot is None:
        return html.Div("Waiting for a validated market snapshot.", className="terminal-report-empty")
    report = snapshot.report
    state = snapshot.state
    summary = list(report.positioning_summary) + list(report.structure_summary)
    return html.Div([
        html.Div([
            html.Div([
                html.Span("MARKET REPORT", className="terminal-report-kicker"),
                html.H2(f"{state.symbol} market structure", className="terminal-report-title"),
                html.P(
                    f"{state.gamma_regime.value.replace('_', ' ')} | "
                    f"{state.structure.value.replace('_', ' ')} | {state.session.value}",
                    className="terminal-report-subtitle",
                ),
            ], className="terminal-report-head"),
            html.Div([
                html.Div([html.Span("SPOT"), html.Strong(_price(state.spot))]),
                html.Div([html.Span("DATA"), html.Strong(state.data_status)]),
                html.Div([html.Span("UPDATED"), html.Strong(market_time_text(state.timestamp, display_timezone))]),
            ], className="terminal-report-snapshot"),
        ], className="terminal-report-header"),
        html.Div([
            html.Section([
                html.H3("Positioning & structure"),
                html.Ul([html.Li(item) for item in summary] or [html.Li("No interpretation available yet.")]),
            ], className="terminal-report-section"),
            html.Section([
                html.H3("Relevant levels"),
                html.Div([
                    html.Div([
                        html.Span(level.level_type.value.replace("_", " ")),
                        html.Strong(_price(level.price)),
                        html.Small(f"{level.strength}/100 strength"),
                    ], className="terminal-report-level")
                    for level in report.key_levels[:10]
                ] or [html.Div("No levels available.", className="terminal-empty")]),
            ], className="terminal-report-section"),
        ], className="terminal-report-grid"),
        html.Section([
            html.H3("Conditional scenarios"),
            html.Div([
                html.Div([
                    html.Span(scenario.direction.value, className="terminal-report-scenario-direction"),
                    html.H4(scenario.title),
                    html.P(scenario.trigger),
                    html.P([html.Span("Invalidation: ", className="terminal-report-label"), scenario.invalidation]),
                ], className="terminal-report-scenario")
                for scenario in report.scenarios
            ] or [html.Div("No scenarios available.", className="terminal-empty")], className="terminal-report-scenarios"),
        ], className="terminal-report-section terminal-report-section--scenarios"),
    ], className="terminal-report")


def overview_briefing_view(snapshot: MarketIntelligenceSnapshot | None, display_timezone: str = "America/New_York") -> html.Div:
    """Render the command-center hierarchy from normalized levels and state."""
    if snapshot is None:
        return html.Div("Waiting for a validated market snapshot.", className="terminal-report-empty")
    state = snapshot.state
    levels = snapshot.report.key_levels
    priority = (
        "GEX_WALL", "CALL_WALL", "PUT_WALL", "OVH", "OVL", "POC", "VAH", "VAL",
    )
    selected = [
        next((level for level in levels if level.level_type.value == level_type), None)
        for level_type in priority
    ]
    selected = [level for level in selected if level is not None]
    scenario = snapshot.scenarios[0] if snapshot.scenarios else None
    return html.Div([
        html.Div([
            html.Div([
                html.Span("MARKET SNAPSHOT", className="terminal-report-kicker"),
                html.H2(f"{state.symbol} command center", className="terminal-report-title"),
                html.P(
                    f"{state.gamma_regime.value.replace('_', ' ')} | "
                    f"{state.structure.value.replace('_', ' ')} | {state.session.value}",
                    className="terminal-report-subtitle",
                ),
            ]),
            html.Div([
                _diagnostic_metric("SPOT", _price(state.spot)),
                _diagnostic_metric("DATA", state.data_status.upper()),
                _diagnostic_metric("UPDATED", market_time_text(state.timestamp, display_timezone)),
            ], className="terminal-report-snapshot"),
        ], className="terminal-report-header"),
        html.Div([
            html.Div([
                html.Span(level.level_type.value.replace("_", " ")),
                html.Strong(_price(level.price)),
                html.Small(f"{level.strength}/100 | {level.status.value.replace('_', ' ')}"),
            ], className="terminal-overview-level")
            for level in selected
        ] or [html.Div("No normalized levels are available.", className="terminal-empty")],
                 className="terminal-overview-levels"),
        html.Div([
            html.Span("CURRENT SCENARIO", className="terminal-scenario-label"),
            html.Strong(scenario.title if scenario else "No scenario is available."),
            html.Span(scenario.trigger if scenario else "", className="terminal-overview-scenario-trigger"),
            html.Span(scenario.invalidation if scenario else "", className="terminal-overview-scenario-invalidation"),
        ], className="terminal-overview-scenario"),
    ], className="terminal-overview-briefing")


def diagnostics_view(payload: dict | None) -> html.Div:
    """Render the backend diagnostics contract without inferring data health."""
    if not payload:
        return html.Div("Diagnostics are not available yet.", className="terminal-diagnostics-empty")

    metadata = payload.get("metadata", {})
    api_status = str(payload.get("api_status", "UNKNOWN"))
    websocket_status = str(payload.get("websocket_status", "UNKNOWN"))
    symbols = payload.get("symbols", [])
    issue = payload.get("last_error")
    return html.Div([
        html.Div([
            html.Div([
                html.Span("SYSTEM DIAGNOSTICS", className="terminal-report-kicker"),
                html.H2("Data health", className="terminal-report-title"),
                html.P(
                    "Current collector and snapshot status. Values come directly from the backend.",
                    className="terminal-report-subtitle",
                ),
            ]),
            html.Div([
                _diagnostic_metric("API", api_status),
                _diagnostic_metric("STREAM", websocket_status),
                _diagnostic_metric("MARKET", "OPEN" if metadata.get("market_open") else "CLOSED"),
            ], className="terminal-report-snapshot"),
        ], className="terminal-report-header"),
        html.Div(issue, className="terminal-diagnostics-error") if issue else None,
        html.Div([
            html.Div([
                html.Div([
                    html.Span(str(item.get("symbol", "UNKNOWN")), className="terminal-diagnostic-symbol"),
                    html.Span(str(item.get("data_status", "UNKNOWN")), className="terminal-diagnostic-status"),
                ], className="terminal-diagnostic-heading"),
                html.Div([
                    _diagnostic_detail("Last update", _diagnostic_time(item.get("last_update"))),
                    _diagnostic_detail("Age", _diagnostic_age(item.get("age_seconds"))),
                    _diagnostic_detail("Options", str(item.get("options_count", 0))),
                    _diagnostic_detail("Expirations", str(item.get("expiration_count", 0))),
                    _diagnostic_detail("Strikes", str(item.get("strike_count", 0))),
                    _diagnostic_detail("Source", str(item.get("source") or "Unavailable")),
                    _diagnostic_detail("Compute", _diagnostic_ms(item.get("calculation_ms"))),
                    _diagnostic_detail("Calculated", _diagnostic_time(item.get("last_calculation"))),
                ], className="terminal-diagnostic-details"),
                html.Div(str(item["last_error"]), className="terminal-diagnostic-error")
                if item.get("last_error") else None,
                _quality_view(item.get("quality")),
            ], className="terminal-diagnostic-card")
            for item in symbols
        ] or [html.Div("No symbol diagnostics have been collected.", className="terminal-diagnostics-empty")],
                  className="terminal-diagnostics-grid"),
    ], className="terminal-diagnostics")


def session_profile_view(payload: dict | None) -> html.Div:
    """Render regular and overnight levels produced by the profile service."""
    if not payload:
        return html.Div("Session profile is not available yet.", className="terminal-diagnostics-empty")
    sessions = payload.get("sessions", {})
    cards = [
        _session_profile_card("REGULAR SESSION", sessions.get("regular", {})),
        _session_profile_card("OVERNIGHT SESSION", sessions.get("overnight", {})),
    ]
    return html.Div([
        html.Div([
            html.Div([
                html.Span("SESSION PROFILE", className="terminal-report-kicker"),
                html.H2(f"{payload.get('symbol', 'MARKET')} session structure", className="terminal-report-title"),
                html.P(
                    "POC and value area use available bar weights; no missing bars are inferred.",
                    className="terminal-report-subtitle",
                ),
            ]),
            html.Div([
                _diagnostic_metric("TIMEZONE", str(payload.get("timezone", "UNKNOWN")).split("/")[-1]),
                _diagnostic_metric("AS OF", _diagnostic_time(payload.get("as_of"))),
                _diagnostic_metric("VALUE AREA", f"{float(payload.get('methodology', {}).get('value_area_fraction', 0)):.0%}"),
            ], className="terminal-report-snapshot"),
        ], className="terminal-report-header"),
        html.Div(cards, className="terminal-session-grid"),
    ], className="terminal-session")


def _session_profile_card(title: str, profile: dict) -> html.Section:
    if not profile or not profile.get("available"):
        content = html.Div("No saved bars for this session.", className="terminal-diagnostics-empty")
    else:
        levels = profile.get("levels", {})
        rows = [("Open", levels.get("open")), ("High", levels.get("high")), ("Low", levels.get("low")),
                ("Close", levels.get("close")), ("POC", levels.get("poc")),
                ("VAH", levels.get("vah")), ("VAL", levels.get("val"))]
        content = html.Div([
            html.Div([html.Span(label), html.Strong(_price(float(value)) if value is not None else "Unavailable")])
            for label, value in rows
        ], className="terminal-session-levels")
    return html.Section([
        html.Div([
            html.H3(title),
            html.Span(f"{profile.get('bar_count', 0)} bars | {profile.get('weight', 'Unavailable')}",
                      className="terminal-panel-meta"),
        ], className="terminal-session-heading"),
        content,
    ], className="terminal-session-card")


def _diagnostic_metric(label: str, value: str) -> html.Div:
    return html.Div([html.Span(label), html.Strong(value)], className="terminal-diagnostic-metric")


def _diagnostic_detail(label: str, value: str) -> html.Div:
    return html.Div([html.Span(label), html.Strong(value)])


def _diagnostic_age(value: object) -> str:
    if value is None:
        return "Unavailable"
    try:
        seconds = max(float(value), 0.0)
    except (TypeError, ValueError):
        return "Unavailable"
    return f"{seconds:.0f}s" if seconds < 60 else f"{seconds / 60:.1f}m"


def _diagnostic_ms(value: object) -> str:
    if value is None:
        return "Not measured"
    try:
        return f"{float(value):.1f} ms"
    except (TypeError, ValueError):
        return "Not measured"


def _quality_view(quality: object):
    if not isinstance(quality, dict):
        return None
    return html.Details([
        html.Summary("Data quality"),
        html.Div([
            _diagnostic_detail("Valid", str(quality.get("valid_record_count", 0))),
            _diagnostic_detail("Invalid", str(quality.get("invalid_record_count", 0))),
            _diagnostic_detail("Missing Greeks", str(quality.get("missing_greeks", 0))),
            _diagnostic_detail("Missing OI", str(quality.get("missing_open_interest", 0))),
            _diagnostic_detail("Missing volume", str(quality.get("missing_volume", 0))),
            _diagnostic_detail("Duplicate contracts", str(quality.get("duplicate_contracts", 0))),
        ], className="terminal-diagnostic-quality"),
    ], className="terminal-diagnostic-quality-details")


def _diagnostic_time(value: object) -> str:
    if not value:
        return "Unavailable"
    return str(value).replace("T", " ")[:19]


def options_chain_view(payload: dict | None) -> html.Div:
    """Render the application-owned options-chain payload as a dense table."""
    if not payload or not payload.get("rows"):
        return html.Div("No contracts match the selected options-chain filters.", className="terminal-report-empty")
    side = payload.get("side", "ALL")
    headers: list[str] = []
    if side in {"ALL", "CALLS"}:
        headers.extend(["Call OI", "Call vol", "Call GEX", "Call IV", "Call delta"])
    headers.append("Strike")
    if side in {"ALL", "PUTS"}:
        headers.extend(["Put delta", "Put IV", "Put GEX", "Put vol", "Put OI"])
    headers.extend(["Net GEX", "Context"])
    return html.Div([
        html.Div([
            html.Span(f"{payload['row_count']} strikes", className="terminal-chain-meta"),
            html.Span(f"Spot {_price(float(payload['spot']))}", className="terminal-chain-meta"),
        ], className="terminal-chain-summary"),
        html.Div([
            html.Table([
                html.Thead(html.Tr([html.Th(header) for header in headers])),
                html.Tbody([
                    _chain_row(row, side)
                    for row in payload["rows"]
                ]),
            ], className="terminal-chain-table"),
        ], className="terminal-chain-scroll"),
    ], className="terminal-chain")


def _chain_row(row: dict, side: str) -> html.Tr:
    cells: list[html.Td] = []
    if side in {"ALL", "CALLS"}:
        cells.extend([
            html.Td(_integer(row["call"]["open_interest"]), className="terminal-chain-call"),
            html.Td(_integer(row["call"]["volume"]), className="terminal-chain-call"),
            html.Td(_compact_money(row["call"]["gex"]), className="terminal-chain-call"),
            html.Td(_percent(row["call"].get("iv", 0.0)), className="terminal-chain-call"),
            html.Td(_decimal(row["call"].get("delta", 0.0)), className="terminal-chain-call"),
        ])
    cells.append(html.Td(_price(float(row["strike"])), className="terminal-chain-strike"))
    if side in {"ALL", "PUTS"}:
        cells.extend([
            html.Td(_decimal(row["put"].get("delta", 0.0)), className="terminal-chain-put"),
            html.Td(_percent(row["put"].get("iv", 0.0)), className="terminal-chain-put"),
            html.Td(_compact_money(row["put"]["gex"]), className="terminal-chain-put"),
            html.Td(_integer(row["put"]["volume"]), className="terminal-chain-put"),
            html.Td(_integer(row["put"]["open_interest"]), className="terminal-chain-put"),
        ])
    cells.extend([
        html.Td(_compact_money(row["net_gex"]), className="terminal-chain-net"),
        html.Td(" | ".join(row["flags"]), className="terminal-chain-flags"),
    ])
    class_name = "terminal-chain-row"
    if "ATM" in row["flags"]:
        class_name += " terminal-chain-row--atm"
    if any(flag in row["flags"] for flag in ("CALL WALL", "PUT WALL", "GEX WALL")):
        class_name += " terminal-chain-row--level"
    return html.Tr(cells, className=class_name)


def _price(value: float) -> str:
    return f"{value:,.2f}" if abs(value) < 10_000 else f"{value:,.0f}"


def _metric(value: float) -> str:
    if abs(float(value)) >= 1_000_000:
        return f"{float(value) / 1_000_000:,.2f}M"
    if abs(float(value)) >= 1_000:
        return f"{float(value):,.0f}"
    return f"{float(value):,.4g}"


def _integer(value: float) -> str:
    return f"{float(value):,.0f}" if value else "-"


def _percent(value: float) -> str:
    return f"{float(value):.1%}" if value else "-"


def _decimal(value: float) -> str:
    return f"{float(value):+.2f}" if value else "-"


def _compact_money(value: float) -> str:
    if not value:
        return "-"
    sign = "+" if value > 0 else "-"
    amount = abs(float(value))
    if amount >= 1_000_000_000:
        return f"{sign}{amount / 1_000_000_000:.2f}B"
    if amount >= 1_000_000:
        return f"{sign}{amount / 1_000_000:.1f}M"
    if amount >= 1_000:
        return f"{sign}{amount / 1_000:.0f}K"
    return f"{sign}{amount:.0f}"
