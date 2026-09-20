"""Serializable DTOs for GAMMA market-intelligence outputs."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from gex.application.market_intelligence.service import MarketIntelligenceSnapshot
from gex.domain.market.intelligence import (
    MarketLevel,
    MarketReport,
    MarketState,
    Scenario,
)


def snapshot_to_dict(snapshot: MarketIntelligenceSnapshot) -> dict[str, Any]:
    """Convert a market-intelligence snapshot into an API-ready structure."""
    return {
        "state": market_state_to_dict(snapshot.state),
        "scenarios": [scenario_to_dict(scenario) for scenario in snapshot.scenarios],
        "report": market_report_to_dict(snapshot.report),
    }


def market_report_to_dict(report: MarketReport, lang: str = "en") -> dict[str, Any]:
    payload = {
        "symbol": report.symbol,
        "timestamp": _iso(report.timestamp),
        "market_state": market_state_to_dict(report.market_state),
        "key_levels": [market_level_to_dict(level) for level in report.key_levels],
        "scenarios": [scenario_to_dict(scenario, lang=lang) for scenario in report.scenarios],
        "positioning_summary": list(report.positioning_summary),
        "structure_summary": list(report.structure_summary),
    }
    if lang == "es":
        for key in ("gamma_regime", "structure", "session", "data_status", "positioning"):
            if key in payload["market_state"]:
                payload["market_state"][key] = _translate_enum(payload["market_state"][key])
        payload["positioning_summary"] = [_translate_analysis(text) for text in payload["positioning_summary"]]
        payload["structure_summary"] = [_translate_analysis(text) for text in payload["structure_summary"]]
        payload["market_state"]["reasons"] = [_translate_analysis(text) for text in payload["market_state"]["reasons"]]
    return payload


def _translate_analysis(value: object) -> object:
    if not isinstance(value, str):
        return value
    replacements = (
        ("Call concentration:", "Concentracion call:"),
        ("Put concentration:", "Concentracion put:"),
        ("Major gamma concentration:", "Concentracion mayor de gamma:"),
        (" with strength ", " con fuerza "),
        (" is classified as ", " esta clasificado como "),
        (" in CLOSED session.", " en sesion CERRADA."),
        (" in OPEN session.", " en sesion ABIERTA."),
        ("Gamma regime is ", "El regimen gamma es "),
        ("Gamma regime classified as ", "El regimen gamma esta clasificado como "),
        ("; data status is ", "; estado de datos: "),
        (" from net GEX input.", " a partir del GEX neto."),
        ("Data status is ", "El estado de datos es "),
        ("Gamma concentration:", "Concentracion gamma:"),
        ("Gamma concentration", "Concentracion gamma"),
        ("Major gamma level is ", "El nivel gamma mayor es "),
        ("Major OI reference is ", "La referencia principal de OI es "),
        ("Major volume reference is ", "La referencia principal de volumen es "),
        ("Nearest support candidate is ", "El soporte mas cercano es "),
        ("Nearest resistance candidate is ", "La resistencia mas cercana es "),
        ("Spot structure is ", "La estructura del spot es "),
        ("relative to major gamma", "respecto a gamma mayor"),
        ("with open interest", "con open interest"),
        ("with volume", "con volumen"),
        ("Price is TESTING", "El precio esta EN PRUEBA"),
        ("Active scenario:", "Escenario activo:"),
        ("Price holds ", "El precio mantiene "),
        ("Option data unavailable", "Datos de opciones no disponibles"),
        ("ABOVE_MAJOR_GAMMA", "POR ENCIMA DE GAMMA MAYOR"),
        ("BELOW_MAJOR_GAMMA", "POR DEBAJO DE GAMMA MAYOR"),
        ("NEGATIVE_GAMMA", "GAMMA NEGATIVA"),
        ("POSITIVE_GAMMA", "GAMMA POSITIVA"),
        ("NEUTRAL_GAMMA", "GAMMA NEUTRAL"),
        ("DATA_STALE", "DATOS DESACTUALIZADOS"),
        ("DATA_LIVE", "DATOS EN VIVO"),
        ("LOW_GAMMA", "GAMMA BAJA"),
        ("HIGH_GAMMA", "GAMMA ALTA"),
        ("GEX_WALL", "MURO GEX"),
        ("VOLUME_NODE", "NODO DE VOLUMEN"),
        ("PUT_HEAVY", "PREDOMINIO PUT"),
        ("CALL_HEAVY", "PREDOMINIO CALL"),
        ("CLOSED", "CERRADA"),
        ("TESTING", "EN PRUEBA"),
        ("No valid option data", "No hay datos de opciones validos"),
        ("Positive gamma", "Gamma positiva"),
        ("Negative gamma", "Gamma negativa"),
        ("Neutral gamma", "Gamma neutral"),
        ("positive gamma", "gamma positiva"),
        ("negative gamma", "gamma negativa"),
        ("neutral gamma", "gamma neutral"),
        ("Call Wall", "Muro call"),
        ("Put Wall", "Muro put"),
        ("Gamma Flip", "Gamma flip"),
        ("Zero Gamma", "Gamma cero"),
        ("CALL_WALL", "MURO CALL"),
        ("PUT_WALL", "MURO PUT"),
        ("GAMMA_FLIP", "GIRO GAMMA"),
        ("DELAYED", "RETRASADO"),
        ("STALE", "DESACTUALIZADO"),
        ("LIVE", "EN VIVO"),
        (" at ", " en "),
        ("Positioning", "Posicionamiento"),
        ("positioning", "posicionamiento"),
        ("Structure", "Estructura"),
        ("structure", "estructura"),
        ("support", "soporte"),
        ("resistance", "resistencia"),
        ("above", "por encima de"),
        ("below", "por debajo de"),
        ("near", "cerca de"),
        ("current price", "precio actual"),
        ("spot", "spot"),
        ("dealers", "dealers"),
        ("dealer", "dealer"),
        ("flow", "flujo"),
        ("options", "opciones"),
        ("volatility", "volatilidad"),
        ("Invalidation", "Invalidacion"),
        ("Trigger", "Activacion"),
    )
    translated = value
    for source, target in replacements:
        translated = translated.replace(source, target)
    return translated


def _translate_enum(value: object) -> object:
    if not isinstance(value, str):
        return value
    return {
        "POSITIVE_GAMMA": "GAMMA POSITIVA",
        "NEGATIVE_GAMMA": "GAMMA NEGATIVA",
        "NEUTRAL_GAMMA": "GAMMA NEUTRAL",
        "ABOVE_MAJOR_GAMMA": "POR ENCIMA DE GAMMA MAYOR",
        "BELOW_MAJOR_GAMMA": "POR DEBAJO DE GAMMA MAYOR",
        "REGULAR": "REGULAR",
        "OVERNIGHT": "OVERNIGHT",
        "DATA_LIVE": "DATOS EN VIVO",
        "DATA_STALE": "DATOS DESACTUALIZADOS",
        "LIVE": "EN VIVO",
        "DELAYED": "RETRASADO",
        "STALE": "DESACTUALIZADO",
        "UNKNOWN": "DESCONOCIDO",
        "PUT_HEAVY": "PREDOMINIO PUT",
        "CALL_HEAVY": "PREDOMINIO CALL",
        "BALANCED": "EQUILIBRADO",
        "CLOSED": "CERRADA",
        "OPEN": "ABIERTA",
        "GEX_ENGINE": "MOTOR GEX",
        "SESSION_PROFILE": "PERFIL DE SESION",
        "LOW_GAMMA": "GAMMA BAJA",
        "HIGH_GAMMA": "GAMMA ALTA",
        "VOLUME_NODE": "NODO DE VOLUMEN",
    }.get(value, value)


def _translate_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    translated = dict(scenario)
    for key in ("title", "trigger", "structural_implication", "invalidation"):
        translated[key] = _translate_analysis(translated.get(key))
    translated["conditions"] = [_translate_analysis(value) for value in translated.get("conditions", [])]
    return translated


def market_state_to_dict(state: MarketState, lang: str = "en") -> dict[str, Any]:
    payload: dict[str, Any] = {
        "symbol": state.symbol,
        "timestamp": _iso(state.timestamp),
        "spot": state.spot,
        "gamma_regime": state.gamma_regime.value,
        "structure": state.structure.value,
        "session": state.session.value,
        "data_status": state.data_status,
        "reasons": list(state.reasons),
    }
    _set_optional(payload, "previous_spot", state.previous_spot)
    _set_optional(payload, "price_change", state.price_change)
    _set_optional(payload, "price_change_percent", state.price_change_percent)
    _set_optional(payload, "implied_volatility", state.implied_volatility)
    _set_optional(payload, "positioning", state.positioning if state.positioning != "UNKNOWN" else None)
    _set_optional(payload, "nearest_support", _maybe_level(state.nearest_support))
    _set_optional(payload, "nearest_resistance", _maybe_level(state.nearest_resistance))
    _set_optional(payload, "major_gamma_level", _maybe_level(state.major_gamma_level))
    if lang == "es":
        for key in ("gamma_regime", "structure", "session", "data_status", "positioning"):
            if key in payload:
                payload[key] = _translate_enum(payload[key])
        payload["reasons"] = [_translate_analysis(text) for text in payload["reasons"]]
    return payload


def scenario_to_dict(scenario: Scenario, lang: str = "en") -> dict[str, Any]:
    payload = {
        "id": scenario.id,
        "title": scenario.title,
        "direction": scenario.direction.value,
        "trigger": scenario.trigger,
        "key_level": _maybe_level(scenario.key_level),
        "conditions": list(scenario.conditions),
        "structural_implication": scenario.structural_implication,
        "invalidation": scenario.invalidation,
        "next_levels": [market_level_to_dict(level) for level in scenario.next_levels],
        "supporting_data": _clean_mapping(scenario.supporting_data),
    }
    return _translate_scenario(payload) if lang == "es" else payload


def market_level_to_dict(level: MarketLevel) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": level.id,
        "type": level.level_type.value,
        "price": level.price,
        "source": level.source.value,
        "timestamp": _iso(level.timestamp),
        "strength": level.strength,
        "session": level.session.value,
        "status": level.status.value,
    }
    optional_values = {
        "distance_percent": level.distance_percent,
        "expiration": _maybe_iso(level.expiration),
        "volume": level.volume,
        "open_interest": level.open_interest,
        "gamma": level.gamma,
        "delta": level.delta,
        "vanna": level.vanna,
        "charm": level.charm,
        "metadata": _clean_mapping(level.metadata),
    }
    for key, value in optional_values.items():
        _set_optional(payload, key, value)
    return payload


def _maybe_level(level: MarketLevel | None) -> dict[str, Any] | None:
    if level is None:
        return None
    return market_level_to_dict(level)


def _set_optional(payload: dict[str, Any], key: str, value: Any) -> None:
    if value is None:
        return
    if value == {}:
        return
    payload[key] = value


def _clean_mapping(mapping: Mapping[str, object]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in mapping.items():
        cleaned[key] = _clean_value(value)
    return {key: value for key, value in cleaned.items() if value is not None}


def _clean_value(value: object) -> Any:
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return _clean_mapping(value)
    if isinstance(value, tuple | list):
        return [_clean_value(item) for item in value if item is not None]
    return value


def _maybe_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _iso(value)


def _iso(value: datetime) -> str:
    return value.isoformat()
