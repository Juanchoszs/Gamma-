"""GEX dashboard application."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
from mcp.server.fastmcp import FastMCP

from .. import store
from ..config import SETTINGS, UNDERLYINGS
from ..metrics import ET, regime_read
from ..providers.rtquote import QUOTES, credentials_present

mcp = FastMCP("gex-data")


def _latest_snapshot_path(symbol: str) -> Path | None:
    root = SETTINGS.data_dir / "snapshots" / symbol
    if not root.exists():
        return None
    files = sorted(root.rglob("*.parquet"))
    return files[-1] if files else None


def _preferred_symbol(symbol: str) -> str:
    """Choose the real-time symbol when fresh native data is available."""
    key = f"{symbol}_RT"
    path = SETTINGS.data_dir / "history" / "metrics.parquet"
    if not path.exists():
        return symbol
    try:
        df = pd.read_parquet(path, columns=["symbol"])
    except Exception:
        return symbol
    return key if (df["symbol"] == key).any() else symbol


def _check_symbol(symbol: str) -> str:
    symbol = symbol.upper()
    if symbol not in UNDERLYINGS:
        raise ValueError(f"Symbole inconnu {symbol} — choix : {list(UNDERLYINGS)}")
    return symbol


@mcp.tool()
def get_gex_summary(symbol: str = "SPX") -> str:
    """Return the latest summary metrics and their intraday change."""
    symbol = _preferred_symbol(_check_symbol(symbol))
    path = SETTINGS.data_dir / "history" / "metrics.parquet"
    if not path.exists():
        return "Aucun historique — le dashboard n'a pas encore tourné."
    df = pd.read_parquet(path)
    df = df[df["symbol"] == symbol].sort_values("timestamp")
    if df.empty:
        return f"Aucune donnée pour {symbol}."
    last = df.iloc[-1].to_dict()
    last["timestamp"] = str(last["timestamp"])
    out = {"dernier": last, "nb_snapshots": len(df)}
    if len(df) > 1:
        first = df.iloc[0]
        out["variation_du_jour"] = {
            "net_gex": float(df.iloc[-1]["net_gex"] - first["net_gex"]),
            "spot": float(df.iloc[-1]["spot"] - first["spot"]),
        }
    return json.dumps(out, default=str)


@mcp.tool()
def get_gex_by_strike(symbol: str = "SPX", top_n: int = 15) -> str:
    """Return the strongest gamma walls from the latest snapshot."""
    symbol = _preferred_symbol(_check_symbol(symbol))
    path = _latest_snapshot_path(symbol)
    if path is None:
        return "Aucun snapshot — le dashboard n'a pas encore tourné."
    df = pd.read_parquet(path)
    agg = df.groupby("strike").agg(
        gex_net=("gex", "sum"), oi=("open_interest", "sum")
    ).reset_index()
    agg["abs_gex"] = agg["gex_net"].abs()
    top = agg.nlargest(top_n, "abs_gex").sort_values("strike")
    rows = [
        {
            "strike": float(r.strike),
            "gex_net_dollars": float(r.gex_net),
            "cote": "calls (support/pin)" if r.gex_net > 0 else "puts (accélération)",
            "open_interest": float(r.oi),
        }
        for r in top.itertuples()
    ]
    return json.dumps({"snapshot": path.name, "murs_de_gamma": rows})


def _vix_context() -> dict | None:
    """Return live VIX context, falling back to delayed CBOE data."""
    vix_hist = store.load_index_spot("vix")
    day_open = None
    delayed_last = None
    delayed_nb_points = 0
    if not vix_hist.empty:
        vix_hist = vix_hist.sort_values("timestamp")
        today = str(pd.to_datetime(vix_hist["timestamp"].iloc[-1]).date())
        today_rows = vix_hist[pd.to_datetime(vix_hist["timestamp"]).dt.strftime("%Y-%m-%d") == today]
        if not today_rows.empty:
            day_open = float(today_rows["vix"].iloc[0])
            delayed_last = float(today_rows["vix"].iloc[-1])
            delayed_nb_points = len(today_rows)

    vix_live = QUOTES.price("VIX") if credentials_present() else None
    if vix_live is not None:
        return {
            "dernier": vix_live,
            "source": "dxfeed_live",
            "variation_du_jour": (vix_live - day_open) if day_open is not None else None,
        }
    if delayed_last is not None:
        return {
            "dernier": delayed_last,
            "source": "cboe_delaye",
            "variation_du_jour": (delayed_last - day_open) if delayed_nb_points > 1 else None,
        }
    return None


@mcp.tool()
def get_market_context(symbol: str = "SPX") -> str:
    """Return a concise gamma, delta, wall, and VIX market overview."""
    symbol = _preferred_symbol(_check_symbol(symbol))
    metrics_path = SETTINGS.data_dir / "history" / "metrics.parquet"
    if not metrics_path.exists():
        return "Aucun historique — le dashboard n'a pas encore tourné."
    hist = pd.read_parquet(metrics_path)
    hist = hist[hist["symbol"] == symbol].sort_values("timestamp")
    if hist.empty:
        return f"Aucune donnée pour {symbol}."
    last = hist.iloc[-1]
    spot = float(last["spot"])
    zero_gamma = float(last["zero_gamma"]) if pd.notna(last.get("zero_gamma")) else None
    net_dex = float(last["net_dex"]) if pd.notna(last.get("net_dex")) else 0.0

    regime = regime_read(
        float(last["net_gex"]), net_dex,
        dex_history=hist["net_dex"] if "net_dex" in hist.columns else None,
    )

    walls = json.loads(get_gex_by_strike(symbol, 15))["murs_de_gamma"]
    calls_above = [w for w in walls if w["strike"] > spot and w["gex_net_dollars"] > 0]
    puts_below = [w for w in walls if w["strike"] < spot and w["gex_net_dollars"] < 0]
    call_wall = min(calls_above, key=lambda w: w["strike"]) if calls_above else None
    put_wall = max(puts_below, key=lambda w: w["strike"]) if puts_below else None

    vix_ctx = _vix_context()

    out = {
        "symbol": symbol,
        "spot": spot,
        "net_gex": float(last["net_gex"]),
        "zero_gamma": zero_gamma,
        "spot_vs_zero_gamma": (spot - zero_gamma) if zero_gamma is not None else None,
        "regime": {
            "severite": regime["severity"],
            "cle": regime["i18n_key"],
            "gex_frein": regime["gex_frein"],
            "magnitude_dex": regime["magnitude"],
        },
        "pc_oi": float(last["pc_oi"]) if pd.notna(last.get("pc_oi")) else None,
        "mur_call_proche": call_wall,
        "mur_put_proche": put_wall,
        "vix": vix_ctx,
    }
    return json.dumps(out, default=str)


@mcp.tool()
def get_flow_delta(symbol: str = "SPX", day: str | None = None) -> str:
    """Return recent intraday option delta flow and daily totals."""
    symbol = _check_symbol(symbol)
    day = day or datetime.now(ET).strftime("%Y-%m-%d")
    path = SETTINGS.data_dir / "flows" / symbol / f"{day}.parquet"
    if not path.exists():
        return f"Aucun flux pour {symbol} le {day}."
    df = pd.read_parquet(path).sort_values("timestamp")
    recent = df.tail(30)[["timestamp", "flow_total", "flow_0dte"]]
    recent["timestamp"] = recent["timestamp"].astype(str)
    return json.dumps(
        {
            "jour": day,
            "cumul_flow_total": float(df["flow_total"].sum()),
            "cumul_flow_0dte": float(df["flow_0dte"].sum()),
            "dernieres_barres": recent.to_dict("records"),
        }
    )


@mcp.tool()
def get_history(symbol: str = "SPX", last_n: int = 50) -> str:
    """Return recent summary-metric history for an underlying."""
    symbol = _preferred_symbol(_check_symbol(symbol))
    path = SETTINGS.data_dir / "history" / "metrics.parquet"
    if not path.exists():
        return "Aucun historique."
    df = pd.read_parquet(path)
    df = df[df["symbol"] == symbol].sort_values("timestamp").tail(last_n)
    df["timestamp"] = df["timestamp"].astype(str)
    return json.dumps(df.to_dict("records"))


@mcp.tool()
def get_reports(last_n: int = 5) -> str:
    """Return the latest scheduled-task reports."""
    from ..infrastructure.logsetup import read_reports
    return read_reports(last_n)


@mcp.tool()
def get_log_tail(lines: int = 50, level: str | None = None) -> str:
    """Return the tail of the technical log, optionally filtered by level."""
    from ..infrastructure.logsetup import LOG_FILE
    if not LOG_FILE.exists():
        return "Aucun log (le dashboard n'a pas encore tourné avec la journalisation)."
    rows = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    if level:
        rows = [r for r in rows if f" {level.upper()} " in r]
    return "\n".join(rows[-lines:]) or "Aucune ligne correspondante."


def main() -> None:
    """Run the application."""
    mcp.run()


if __name__ == "__main__":
    main()
