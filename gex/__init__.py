"""GEX Dashboard package.

Re-exports modules for backward compatibility with existing imports.
"""
from __future__ import annotations

# Core modules (moved to subpackages)
from . import calculations, config, domain, infrastructure, providers, storage, ui, api, application, cli, analysis

# Re-export commonly used modules at package root for backward compatibility
from . import metrics
from . import store

# Calculations
from .calculations import gex as _gex
from .calculations import greeks, flow, gamma_flip, levels, native, regime, pinning, tickstats

# Analysis
from .analysis import backtest, run

# Application workflows
from .application import refresh_market, refresh_native, flush_streams, digest, export, roll, scheduler
from .application import scheduler as scheduler_module
scheduler = scheduler_module  # backward compat: gex.scheduler.STATE
from .application.scheduler import STATE as SCHEDULER_STATE
from .api import mcp as mcp_server_module
mcp_server = mcp_server_module  # backward compat: gex.mcp_server

# Providers
from .providers import ingest, rtquote, futopt, idxopt, flowtape, tickcapture, tt_auth, tt_web

# Domain
from .domain import models, quality, market_state, state

# Infrastructure
from .infrastructure import logsetup, rates, git_repository

# CLI
from .cli import backfill, pricehist, backup

# API
from .api import register_api

# UI
from .ui import app as ui_app, i18n, scales
from .ui.app import GUIDE_ANCHORS, guided, tv_levels_string
from .ui import i18n as ui_i18n
i18n = ui_i18n  # backward compat: gex.i18n

# Compatibility aliases for existing imports
__all__ = [
    "calculations",
    "config",
    "domain",
    "infrastructure",
    "providers",
    "storage",
    "ui",
    "api",
    "application",
    "cli",
    "metrics",
    "store",
    # calculations
    "greeks",
    "flow",
    "gamma_flip",
    "levels",
    "native",
    "regime",
    "pinning",
    "tickstats",
    # analysis
    "backtest",
    "run",
    # application
    "refresh_market",
    "refresh_native",
    "flush_streams",
    "digest",
    "export",
    "roll",
    "scheduler",
    "scheduler_module",
    "SCHEDULER_STATE",
    "mcp_server",
    "mcp_server_module",
    # providers
    "ingest",
    "rtquote",
    "futopt",
    "idxopt",
    "flowtape",
    "tickcapture",
    "tt_auth",
    "tt_web",
    # domain
    "models",
    "quality",
    "market_state",
    "state",
    # infrastructure
    "logsetup",
    "rates",
    "git_repository",
    # cli
    "backfill",
    "pricehist",
    "backup",
    # api
    "register_api",
    # ui
    "ui_app",
    "i18n",
    "scales",
    "GUIDE_ANCHORS",
    "guided",
    "tv_levels_string",
]