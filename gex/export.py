"""Shareable export: extract only data from the public CBOE source and exclude
anything from a paid source.

Why: Databento and broker-feed data are licensed for **personal,
non-redistributable use**. Metrics derived from the public CBOE source can be
shared.

Design principle—**exclude by default**: export only rows explicitly marked
`source == "cboe"`. Unknown or missing provenance is discarded, so an
incomplete migration or unexpected schema cannot leak data; at worst, the
export is empty.

Usage :
    python -m gex.export --migrate           # mark provenance of existing data
    python -m gex.export --out shared-data   # create the shareable export
"""
from __future__ import annotations

import argparse
import logging
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

from .config import SETTINGS

log = logging.getLogger(__name__)

SHAREABLE = "cboe"
PROVENANCE_FILE = "PROVENANCE.md"


# ------------------------------------------------------------------ migration

def migrate(dry_run: bool = False) -> dict[str, int]:
    """Add the `source` column to previously collected data.

    Documented one-time heuristic:
    - history: a row timestamped exactly 16:00:00 is from the Databento
      backfill (`build_day` uses that exact close time); any other time is from
      a live CBOE pull.
    - flows: all files predating this migration are from the backfill. Mark
      them "databento" deliberately; a false negative only withholds data.
    """
    stats = {"history_cboe": 0, "history_databento": 0, "flow_files": 0}

    hist_path = SETTINGS.data_dir / "history" / "metrics.parquet"
    if hist_path.exists():
        h = pd.read_parquet(hist_path)
        if "source" not in h.columns:
            ts = pd.to_datetime(h["timestamp"])
            is_backfill = ts.dt.time == datetime(2000, 1, 1, 16, 0, 0).time()
            h["source"] = pd.Series(SHAREABLE, index=h.index).mask(is_backfill, "databento")
            stats["history_cboe"] = int((~is_backfill).sum())
            stats["history_databento"] = int(is_backfill.sum())
            if not dry_run:
                h.to_parquet(hist_path, index=False)
        else:
            counts = h["source"].value_counts()
            stats["history_cboe"] = int(counts.get(SHAREABLE, 0))
            stats["history_databento"] = int(counts.get("databento", 0))

    for f in sorted((SETTINGS.data_dir / "flows").rglob("*.parquet")):
        d = pd.read_parquet(f)
        if "source" in d.columns:
            continue
        d["source"] = "databento"
        stats["flow_files"] += 1
        if not dry_run:
            d.to_parquet(f, index=False)

    return stats


# --------------------------------------------------------------------- export

def _filter_shareable(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only rows explicitly marked CBOE (exclude by default)."""
    if "source" not in df.columns:
        return df.iloc[0:0]
    return df[df["source"] == SHAREABLE]


def export(out_dir: Path) -> dict:
    """Write the shareable portion of the data to out_dir."""
    out_dir = Path(out_dir)
    report = {"history_rows": 0, "history_excluded": 0,
              "flow_files": 0, "flow_rows": 0, "flow_excluded": 0,
              "days": [], "symbols": set()}

    # --- history
    hist_path = SETTINGS.data_dir / "history" / "metrics.parquet"
    if hist_path.exists():
        h = pd.read_parquet(hist_path)
        keep = _filter_shareable(h)
        report["history_rows"] = len(keep)
        report["history_excluded"] = len(h) - len(keep)
        if len(keep):
            dest = out_dir / "history" / "metrics.parquet"
            dest.parent.mkdir(parents=True, exist_ok=True)
            keep.to_parquet(dest, index=False)
            report["symbols"] |= set(keep["symbol"].unique())

    # --- flows (one file per day and underlying)
    for f in sorted((SETTINGS.data_dir / "flows").rglob("*.parquet")):
        d = pd.read_parquet(f)
        keep = _filter_shareable(d)
        report["flow_excluded"] += len(d) - len(keep)
        if keep.empty:
            continue
        dest = out_dir / "flows" / f.parent.name / f.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        keep.to_parquet(dest, index=False)
        report["flow_files"] += 1
        report["flow_rows"] += len(keep)
        report["days"].append(f.stem)
        report["symbols"].add(f.parent.name)

    report["days"] = sorted(set(report["days"]))
    report["symbols"] = sorted(report["symbols"])
    if report["history_rows"] or report["flow_files"]:
        _write_provenance(out_dir, report)
    return report


def _write_provenance(out_dir: Path, report: dict) -> None:
    """Write provenance information so recipients know what they received and
    under which conditions."""
    days = report["days"]
    span = f"{days[0]} → {days[-1]}" if days else "—"
    (out_dir / PROVENANCE_FILE).write_text(f"""# Provenance des données

Export généré le {datetime.now():%Y-%m-%d %H:%M} par
[gex-dashboard](https://github.com/Darthreign/gex-dashboard)
(`python -m gex.export`).

## Ce que contient cet export

- **Source unique : l'endpoint public *delayed* de CBOE**, gratuit et
  accessible sans compte.
- Il ne s'agit pas de cotations brutes mais de **métriques dérivées** calculées
  localement : GEX net, Gamma Flip, put/call ratios, agrégats de flux delta.
- Sous-jacents : {', '.join(report['symbols']) or '—'}
- Historique : {report['history_rows']} lignes
- Flux : {report['flow_files']} fichiers-jour, {report['flow_rows']} barres ({span})

## Ce qu'il ne contient pas

Toute donnée issue d'une **source payante** (Databento, flux courtier) est
exclue par construction : seules les lignes explicitement marquées
`source = "cboe"` sont exportées. Ces sources sont soumises à une licence
d'usage personnel non redistribuable.

Lignes écartées à ce titre : {report['history_excluded']} en historique,
{report['flow_excluded']} en flux.

## Utilisation

Copier `history/` et `flows/` dans le dossier `data/` de votre propre
instance. Vos collectes ultérieures s'y ajouteront normalement.

Fourni **sans garantie**, à titre informatif, et ne constituant pas un conseil
en investissement — voir l'[avertissement](https://github.com/Darthreign/gex-dashboard/blob/main/DISCLAIMER.md).
""", encoding="utf-8")


# ----------------------------------------------------------------------- main

def main() -> None:
    from .logsetup import setup_logging
    setup_logging()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--migrate", action="store_true",
                    help="marque la provenance des données déjà collectées")
    ap.add_argument("--out", type=Path, default=None,
                    help="dossier de destination de l'export")
    ap.add_argument("--force", action="store_true",
                    help="écrase le dossier de destination s'il existe")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.migrate:
        s = migrate(dry_run=a.dry_run)
        log.info("Migration%s — historique : %d CBOE / %d Databento ; "
                 "%d fichiers de flux marqués",
                 " (simulation)" if a.dry_run else "",
                 s["history_cboe"], s["history_databento"], s["flow_files"])

    if a.out:
        if a.out.exists():
            if not a.force:
                raise SystemExit(f"{a.out} existe déjà — utiliser --force pour l'écraser.")
            shutil.rmtree(a.out)
        r = export(a.out)
        if not r["history_rows"] and not r["flow_files"]:
            log.warning("Export VIDE : aucune donnée marquée '%s'. "
                        "Lancer --migrate d'abord, ou collecter en live.", SHAREABLE)
            return
        log.info("Export vers %s", a.out)
        log.info("  historique : %d lignes (%d exclues)",
                 r["history_rows"], r["history_excluded"])
        log.info("  flux       : %d fichiers, %d barres (%d exclues)",
                 r["flow_files"], r["flow_rows"], r["flow_excluded"])
        log.info("  %s joint", PROVENANCE_FILE)

    if not a.migrate and not a.out:
        ap.print_help()


if __name__ == "__main__":
    main()
