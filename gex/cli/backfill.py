"""Historical backfill from Databento OPRA (OPRA.PILLAR dataset).

Populates:
- data/history/metrics.parquet: one row per day and underlying (net GEX, zero
  gamma, P/C) from definition, statistics, and ohlcv-1d schemas
- data/flows/{SYM}/{day}.parquet: per-minute delta flow from ohlcv-1m

Documented approximations:
- IV is recovered by inverting Black-Scholes on the daily close.
- Daily spot is derived from put-call parity on liquid pairs
  (S = C - P + K·e^(-rT)), with no external spot source.
- Intraday contract delta uses the day's IV and spot; it is not recalculated
  minute by minute.

Billing safeguards:
- Request a free metadata quote before downloading; abort if > --max-cost.
- Keep raw DBN files in data/databento/; reruns do not redownload existing files.

Usage: python -m gex.backfill [--daily-days 31] [--intraday-days 7]
        [--max-cost 40] [--dry-run]
"""
from __future__ import annotations

import argparse
import io
import logging
import os
import re
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from .. import metrics, store
from ..calculations import greeks
from ..config import CONTRACT_MULTIPLIER, RISK_FREE_RATE, SETTINGS
from ..metrics import ET, YEAR_SECONDS

log = logging.getLogger(__name__)

DATASET = "OPRA.PILLAR"
PARENTS = ["SPX.OPT", "SPXW.OPT", "NDX.OPT", "NDXP.OPT"]
ROOT_TO_SYMBOL = {"SPX": "SPX", "SPXW": "SPX", "NDX": "NDX", "NDXP": "NDX"}
RAW_DIR_NAME = "databento"

# Databento reports the actually available bound in its 422 errors.
_AVAIL_RE = re.compile(r"available up to '([^']+)'")


def _avail_end_from_error(e) -> str | None:
    """Extract the available bound from a data_end_after_available_end error,
    reformatted as ISO 8601 with 'T' (a space would be mangled in the URL)."""
    m = _AVAIL_RE.search(str(e))
    return pd.Timestamp(m.group(1)).isoformat() if m else None


def _api_key() -> str:
    key = os.environ.get("DATABENTO_API_KEY")
    if not key and sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                key = winreg.QueryValueEx(k, "DATABENTO_API_KEY")[0]
        except OSError:
            pass
    if not key:
        raise RuntimeError("DATABENTO_API_KEY introuvable (env ou registre HKCU).")
    return key


def _client():
    import databento as db
    return db.Historical(key=_api_key())


def _raw_path(schema: str, start: date, end: date) -> Path:
    p = SETTINGS.data_dir / RAW_DIR_NAME / f"{schema}_{start}_{end}.dbn.zst"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def download(client, schema: str, start: date, end: date, query_end=None) -> Path:
    """Download a schema to a local DBN file (skip if already present).

    `end` names and caches the file; optional `query_end` is the bound actually
    sent to the API, allowing alignment with dataset availability without
    changing the cache name.
    """
    path = _raw_path(schema, start, end)
    if path.exists():
        log.info("%s : déjà téléchargé (%s)", schema, path.name)
        return path
    qend = query_end if query_end is not None else end
    log.info("Téléchargement %s %s→%s …", schema, start, qend)
    from databento.common.error import BentoClientError, BentoServerError
    import time as _time
    for attempt in range(4):
        try:
            data = client.timeseries.get_range(
                dataset=DATASET, symbols=PARENTS, stype_in="parent",
                schema=schema, start=str(start), end=str(qend),
            )
            break
        except BentoClientError as e:
            # Bound is still too late for this schema; adjust it once.
            avail = _avail_end_from_error(e)
            if avail is None or attempt == 3:
                raise
            log.warning("%s : borne recalée sur %s", schema, avail)
            qend = avail
        except BentoServerError as e:
            if attempt == 3:
                raise
            wait = 30 * (attempt + 1)
            log.warning("Passerelle Databento en erreur (%s), retry dans %d s…", e, wait)
            _time.sleep(wait)
    data.to_file(path)
    log.info("%s : %.1f Mo", schema, path.stat().st_size / 1e6)
    return path


def _to_df(path: Path) -> pd.DataFrame:
    import databento as db
    return db.DBNStore.from_file(path).to_df()


# ---------------------------------------------------------------- referentiel

def load_definitions(path: Path) -> pd.DataFrame:
    df = _to_df(path).reset_index()
    df = df[df["instrument_class"].isin(["C", "P"])]
    root = df["raw_symbol"].str.split().str[0]
    out = pd.DataFrame(
        {
            "instrument_id": df["instrument_id"],
            "symbol": root.map(ROOT_TO_SYMBOL),
            "type": df["instrument_class"],
            "strike": df["strike_price"].astype(float),
            "expiry": pd.to_datetime(df["expiration"], utc=True)
            .dt.tz_convert(ET).dt.date,
        }
    ).dropna(subset=["symbol"])
    return out.drop_duplicates("instrument_id")


def load_open_interest(path: Path) -> pd.DataFrame:
    from databento_dbn import StatType
    df = _to_df(path).reset_index()
    df = df[df["stat_type"] == int(StatType.OPEN_INTEREST)]
    # Published around 10:30 UTC on the trading morning; the UTC date is correct.
    day = pd.to_datetime(df["ts_event"], utc=True).dt.date
    out = pd.DataFrame(
        {"day": day, "instrument_id": df["instrument_id"],
         "open_interest": df["quantity"].astype(float)}
    )
    # Keep the last publication of the day for each contract.
    return out.groupby(["day", "instrument_id"], as_index=False).last()


def load_eod(path: Path) -> pd.DataFrame:
    df = _to_df(path).reset_index()
    # ts_event is 00:00 UTC on the trading day (bar open). Keep the UTC date;
    # converting to ET would shift it by one day.
    day = pd.to_datetime(df["ts_event"], utc=True).dt.date
    return pd.DataFrame(
        {"day": day, "instrument_id": df["instrument_id"],
         "close": df["close"].astype(float), "volume": df["volume"].astype(float)}
    )


# ------------------------------------------------------------------ quotidien

# Official daily index closes. Put-call parity on EOD option closes is too noisy
# because trades are asynchronous (SPX AM versus SPXW PM).
SPOT_SOURCES = {
    "SPX": ("https://cdn.cboe.com/api/global/us_indices/daily_prices/SPX_History.csv",
            "%m/%d/%Y", "DATE", "SPX"),
    "NDX": ("https://fred.stlouisfed.org/graph/fredgraph.csv?id=NASDAQ100",
            "%Y-%m-%d", "observation_date", "NASDAQ100"),
}


def load_spots() -> dict[str, dict[date, float]]:
    import requests
    out: dict[str, dict[date, float]] = {}
    for sym, (url, fmt, datecol, valcol) in SPOT_SOURCES.items():
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        days = pd.to_datetime(df[datecol], format=fmt).dt.date
        vals = pd.to_numeric(df[valcol], errors="coerce")
        out[sym] = {d: float(v) for d, v in zip(days, vals) if np.isfinite(v)}
        log.info("Spots %s : %d jours (dernier %s)", sym, len(out[sym]), max(out[sym]))
    return out

def _t_years(expiries: pd.Series, day: date) -> np.ndarray:
    close_dt = datetime.combine(day, time(16, 0), tzinfo=ET)
    exp_dt = pd.to_datetime(expiries).dt.tz_localize(ET) + pd.Timedelta(hours=16)
    secs = (exp_dt - close_dt).dt.total_seconds().to_numpy()
    return np.maximum(secs, 300.0) / YEAR_SECONDS


def spot_from_parity(chain: pd.DataFrame, day: date) -> float | None:
    """Put-call parity spot S = C - P + K·e^(-rT), median of liquid pairs on
    the nearest expiration at least five days away."""
    expiries = sorted(e for e in chain["expiry"].unique()
                      if (e - day).days >= 5)
    if not expiries:
        return None
    e = chain[chain["expiry"] == expiries[0]]
    # Duplicate strikes can occur (SPX and SPXW roots on one expiry); keep the
    # most-traded contract for each strike.
    e = e.sort_values("volume").drop_duplicates(["type", "strike"], keep="last")
    calls = e[e["type"] == "C"].set_index("strike")["close"]
    puts = e[e["type"] == "P"].set_index("strike")["close"]
    vol = e.groupby("strike")["volume"].sum()
    common = calls.index.intersection(puts.index)
    common = vol.loc[common].nlargest(20).index
    if len(common) < 3:
        return None
    t = _t_years(pd.Series([expiries[0]] * len(common)), day)
    s = calls.loc[common].to_numpy() - puts.loc[common].to_numpy() \
        + common.to_numpy() * np.exp(-RISK_FREE_RATE * t)
    med = float(np.median(s))
    # Safeguard: if pairs diverge (>2% median dispersion), closes are
    # inconsistent; skip the day.
    if np.median(np.abs(s - med)) / med > 0.02:
        return None
    return med


def build_day(chain: pd.DataFrame, symbol: str, day: date,
              spot: float | None = None, persist_chain: bool = False) -> dict | None:
    """Convert a day's joined chain (OI + close) into a history row.

    `persist_chain` also saves the reconstructed chain as a snapshot, allowing
    levels to be recalculated later (backtest). Otherwise the reconstruction is
    discarded after aggregation and backtesting is limited to live sessions.

    Timestamp at 16:00: these data describe the close, including the day's
    settlement open interest published the following morning. Dating it earlier
    would imply it was known sooner.
    """
    if spot is None:
        spot = spot_from_parity(chain, day)
    if spot is None or not np.isfinite(spot):
        log.warning("%s %s : spot indisponible (source externe et parité), jour ignoré",
                    symbol, day)
        return None
    t = _t_years(chain["expiry"], day)
    iv = greeks.implied_vol(
        chain["close"].to_numpy(), spot, chain["strike"].to_numpy(),
        t, RISK_FREE_RATE, (chain["type"] == "C").to_numpy(),
    )
    valid = np.isfinite(iv)
    d = chain.loc[valid].copy()
    d["iv"] = iv[valid]
    d["t_years"] = t[valid]
    is_call = (d["type"] == "C").to_numpy()
    g = greeks.gamma(spot, d["strike"], d["t_years"], RISK_FREE_RATE, d["iv"])
    dc = greeks.call_delta(spot, d["strike"], d["t_years"], RISK_FREE_RATE, d["iv"])
    d["gamma_bs"] = g
    d["delta_bs"] = np.where(is_call, dc, dc - 1.0)
    sign = np.where(is_call, 1.0, -1.0)
    d["gex"] = sign * g * d["open_interest"] * CONTRACT_MULTIPLIER * spot**2 * 0.01
    d["dex"] = -1.0 * d["delta_bs"] * d["open_interest"] * CONTRACT_MULTIPLIER * spot
    d["spot"] = float(spot)
    zg = metrics.zero_gamma(d, spot)
    if persist_chain:
        try:
            store.save_snapshot(
                symbol, d, datetime.combine(day, time(16, 0)),
                source="databento",
                snapshot_type="HISTORICAL",
                data_quality="VALID",
                market_state="HISTORICAL",
                schema_version=1,
            )
        except Exception:  # noqa: BLE001 — history takes priority over snapshot
            log.exception("%s %s : échec d'écriture du snapshot", symbol, day)
    oi_c = d.loc[is_call, "open_interest"].sum()
    oi_p = d.loc[~is_call, "open_interest"].sum()
    v_c = d.loc[is_call, "volume"].sum()
    v_p = d.loc[~is_call, "volume"].sum()
    return {
        "timestamp": datetime.combine(day, time(16, 0)),
        "symbol": symbol,
        "spot": spot,
        "net_gex": float(d["gex"].sum()),
        "zero_gamma": zg,
        "pc_oi": float(oi_p / oi_c) if oi_c else float("nan"),
        "pc_volume": float(v_p / v_c) if v_c else float("nan"),
        "net_gex_0dte": float(d.loc[d["expiry"] == day, "gex"].sum()),
        "net_dex": float(d["dex"].sum()),
        # Paid, personal-use data; excluded from shareable exports.
        "source": "databento",
        "_deltas": d[["instrument_id", "delta_bs", "expiry"]],
        "_spot": spot,
    }


# ------------------------------------------------------------------- intraday

def build_flows(minute_df: pd.DataFrame, deltas: pd.DataFrame, spot: float,
                symbol: str, day: date) -> pd.DataFrame:
    m = minute_df.merge(deltas, on="instrument_id", how="inner")
    signed = m["volume"] * m["delta_bs"] * CONTRACT_MULTIPLIER * spot
    m = m.assign(signed=signed, is_0dte=m["expiry"] == day)
    grouped = m.groupby("minute").agg(
        flow_total=("signed", "sum"),
        contracts_traded=("volume", "sum"),
    )
    flow_0dte = m[m["is_0dte"]].groupby("minute")["signed"].sum()
    grouped["flow_0dte"] = flow_0dte.reindex(grouped.index, fill_value=0.0)
    grouped["flow_calls"] = m[m["delta_bs"] > 0].groupby("minute")["signed"].sum() \
        .reindex(grouped.index, fill_value=0.0)
    grouped["flow_puts"] = m[m["delta_bs"] <= 0].groupby("minute")["signed"].sum() \
        .reindex(grouped.index, fill_value=0.0)
    grouped = grouped.reset_index().rename(columns={"minute": "timestamp"})
    grouped["source"] = "databento"   # not redistributable
    return grouped


# ----------------------------------------------------------------------- main

def run(daily_days: int, intraday_days: int, max_cost: float, dry_run: bool,
        end: date | None = None, persist_chains: bool = True) -> None:
    """Save reconstructed chains as snapshots when `persist_chains` is enabled,
    making their levels replayable for backtests. This uses disk space only;
    raw files have already been downloaded."""
    client = _client()
    end = end or (date.today() - timedelta(days=1))
    daily_start = end - timedelta(days=daily_days)
    intra_start = end - timedelta(days=intraday_days)

    # Align the end bound with REAL availability: get_dataset_range lags the
    # latest publication, so probe with a free quote. On overflow, Databento
    # returns the real bound in the error; reformat it as ISO so the 'T' avoids
    # mangling the URL space. This is robust for daily runs and the 10:00 job.
    from databento.common.error import BentoClientError

    query_end = end
    probe_schema = "ohlcv-1m" if intraday_days > 0 else "ohlcv-1d"
    probe_start = intra_start if intraday_days > 0 else daily_start
    try:
        client.metadata.get_cost(dataset=DATASET, symbols=PARENTS, stype_in="parent",
                                 schema=probe_schema, start=str(probe_start), end=str(end))
    except BentoClientError as e:
        avail = _avail_end_from_error(e)
        if avail is None:
            raise
        query_end = avail
        log.info("Borne de fin calée sur la disponibilité réelle : %s", query_end)

    plan = [("definition", daily_start), ("statistics", daily_start),
            ("ohlcv-1d", daily_start)]
    if intraday_days > 0:
        plan.append(("ohlcv-1m", intra_start))

    total = 0.0
    for schema, start in plan:
        if _raw_path(schema, start, end).exists():
            continue
        c = client.metadata.get_cost(dataset=DATASET, symbols=PARENTS,
                                     stype_in="parent", schema=schema,
                                     start=str(start), end=str(query_end))
        log.info("Devis %-12s %s→%s : %.2f $", schema, start, query_end, c)
        total += c
    log.info("Coût total des téléchargements restants : %.2f $ (plafond %.2f $)", total, max_cost)
    if total > max_cost:
        raise SystemExit(f"Coût {total:.2f} $ > plafond {max_cost} $ — abandon.")
    if dry_run:
        log.info("--dry-run : arrêt avant téléchargement.")
        return

    paths = {schema: download(client, schema, start, end, query_end=query_end)
             for schema, start in plan}

    defs = load_definitions(paths["definition"])
    oi = load_open_interest(paths["statistics"])
    eod = load_eod(paths["ohlcv-1d"])
    log.info("Référentiel : %d contrats ; OI : %d lignes ; EOD : %d lignes",
             len(defs), len(oi), len(eod))

    hist_path = SETTINGS.data_dir / "history" / "metrics.parquet"
    existing = pd.read_parquet(hist_path) if hist_path.exists() else pd.DataFrame()
    existing_keys = set()
    if not existing.empty:
        existing_keys = {(r.symbol, pd.Timestamp(r.timestamp).date())
                         for r in existing.itertuples()}

    chains = (
        eod.merge(oi, on=["day", "instrument_id"], how="left")
        .fillna({"open_interest": 0.0})
        .merge(defs, on="instrument_id", how="inner")
    )

    day_results: dict[tuple[str, date], dict] = {}
    new_rows = []
    spots = load_spots()
    for (symbol, day), chain in chains.groupby(["symbol", "day"]):
        if day.weekday() >= 5:  # weekend publication artifacts
            continue
        res = build_day(chain, symbol, day, spots.get(symbol, {}).get(day),
                        persist_chain=persist_chains)
        if res is None:
            continue
        day_results[(symbol, day)] = res
        if (symbol, day) not in existing_keys:
            new_rows.append({k: v for k, v in res.items() if not k.startswith("_")})
    if new_rows:
        merged = pd.concat([existing, pd.DataFrame(new_rows)], ignore_index=True)
        merged = merged.sort_values(["symbol", "timestamp"])
        hist_path.parent.mkdir(parents=True, exist_ok=True)
        merged.to_parquet(hist_path, index=False)
    log.info("Historique quotidien : %d jours ajoutés", len(new_rows))

    # flux intraday
    if "ohlcv-1m" not in paths:
        log.info("Flux intraday : ignoré (--intraday-days 0)")
        return
    m1 = _to_df(paths["ohlcv-1m"]).reset_index()
    ts = pd.to_datetime(m1["ts_event"], utc=True).dt.tz_convert(ET)
    m1 = pd.DataFrame({
        "minute": ts.dt.tz_localize(None),
        "day": ts.dt.date,
        "instrument_id": m1["instrument_id"],
        "volume": m1["volume"].astype(float),
    }).merge(defs[["instrument_id", "symbol"]], on="instrument_id", how="inner")

    n_files = 0
    for (symbol, day), mday in m1.groupby(["symbol", "day"]):
        res = day_results.get((symbol, day))
        if res is None:
            continue
        out_path = SETTINGS.data_dir / "flows" / symbol / f"{day}.parquet"
        if out_path.exists():
            continue  # do not overwrite days collected live
        flows = build_flows(mday, res["_deltas"], res["_spot"], symbol, day)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        flows.to_parquet(out_path, index=False)
        n_files += 1
    log.info("Flux intraday : %d fichiers jour écrits", n_files)


def main() -> None:
    from .logsetup import setup_logging
    setup_logging()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--daily-days", type=int, default=31)
    ap.add_argument("--intraday-days", type=int, default=7)
    ap.add_argument("--max-cost", type=float, default=40.0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-chains", action="store_true",
                    help="ne pas enregistrer les chaînes reconstruites "
                         "(elles servent au backtest de niveaux)")
    ap.add_argument("--end", type=lambda s: date.fromisoformat(s), default=None,
                    help="borne de fin EXCLUSIVE (défaut : hier)")
    a = ap.parse_args()
    run(a.daily_days, a.intraday_days, a.max_cost, a.dry_run, end=a.end,
        persist_chains=not a.no_chains)


if __name__ == "__main__":
    main()
