"""Live ingestion loop: APScheduler setup, cadences, and job registration."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, time

from apscheduler.schedulers.background import BackgroundScheduler

from . import backup, rates
from .application.flush_streams import flush_prices, flush_tape, flush_ticks
from .application.refresh_market import pull_all, pull_symbol, pull_vix
from .application.refresh_native import (
    NATIVE_CACHE_FRESH_S,
    native_index_key,
    pull_native_index,
    pull_native_options,
)
from .calculations.native import build_native_summary
from .config import SETTINGS
from .infrastructure.git_repository import push_data_repo
from .metrics import ET
from .state import STATE, GlobalState, UnderlyingState

log = logging.getLogger(__name__)

MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 15)


def market_is_open(now_et: datetime | None = None) -> bool:
    now_et = now_et or datetime.now(ET)
    if now_et.weekday() >= 5:
        return False
    return MARKET_OPEN <= now_et.time() <= MARKET_CLOSE


class _Cadence:
    """Trigger an action every N loop iterations."""

    def __init__(self, interval_s: int | None = None) -> None:
        self.count = 0
        interval_s = SETTINGS.snapshot_interval_s if interval_s is None else interval_s
        self.every = max(1, interval_s // SETTINGS.flow_interval_s)

    def tick(self) -> bool:
        due = self.count % self.every == 0
        self.count += 1
        return due


_CADENCE = _Cadence()
# Constituents follow their own cadence; they rely on daily open interest and do not need the same resolution as targets.
_CONSTITUENT_CADENCE = _Cadence(SETTINGS.constituent_interval_s)
_CONSTITUENT_SNAPSHOT = _Cadence(SETTINGS.constituent_snapshot_interval_s)


def start_scheduler() -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone="America/New_York")
    sched.add_job(
        pull_all,
        "interval",
        seconds=SETTINGS.flow_interval_s,
        max_instances=1,
        coalesce=True,
    )
    # Vidange plus fréquente que la minute : une bougie n'est écrite qu'une
    # fois close, ce décalage borne simplement la perte en cas d'arrêt brutal.
    sched.add_job(flush_prices, "interval", seconds=30, max_instances=1, coalesce=True)
    sched.add_job(flush_tape, "interval", seconds=30, max_instances=1, coalesce=True)
    # Options natives NQ/ES : cadence lâche (chaque cycle prend lui-même
    # ~90 s x 2), max_instances=1 empêche un cycle en cours d'en chevaucher
    # un autre si jamais il dépassait l'intervalle.
    sched.add_job(pull_native_options, "interval", minutes=15,
                  max_instances=1, coalesce=True)
    # Chaînes d'indice natives : ~20 s par chaîne (contre ~90 s sur future),
    # donc une cadence bien plus serrée — supprimer un retard de 15 min pour
    # rafraîchir toutes les 15 min n'aurait aucun sens.
    sched.add_job(pull_native_index, "interval", minutes=3,
                  max_instances=1, coalesce=True)
    # Capture tick-par-tick CONTINUE (24/5) : le collecteur (démarré au boot,
    # cf. run.py) agrège en mémoire, ce job vide vers le parquet journalier de
    # NQ/ES toutes les 60 s. Session dxLink dédiée, sans jamais toucher le flux
    # spot du dashboard.
    sched.add_job(flush_ticks, "interval", seconds=60, max_instances=1, coalesce=True)
    sched.add_job(push_data_repo, "cron", day_of_week="mon-fri", hour=16, minute=20)
    # Sauvegarde distante après le push git : elle porte ce que GitHub refuse
    # (archives Databento de plus de 100 Mo). Sans rclone configuré, l'appel
    # journalise et se retire.
    sched.add_job(backup.run, "cron", day_of_week="mon-fri", hour=16, minute=30)
    # Taux sans risque : le SOFR de la veille est publié ~8h ET, on le récupère
    # à 8h15 pour la journée (cf. gex/rates). Le week-end reprend le dernier
    # ouvré, ce qui convient.
    sched.add_job(rates.refresh, "cron", day_of_week="mon-fri", hour=8, minute=15)
    sched.start()
    # Premier chargement du taux au démarrage (dans un thread : ne pas bloquer
    # le lancement sur un appel réseau ; repli sur la constante si indisponible).
    threading.Thread(target=rates.refresh, daemon=True).start()
    # Premier pull immédiat (même hors marché : affiche le dernier état connu).
    threading.Thread(target=pull_all, kwargs={"force": True}, daemon=True).start()
    # Idem pour NQ/ES natifs : sans cet appel, ils resteraient invisibles dans
    # l'interface jusqu'à la première exécution planifiée (jusqu'à 15 min).
    threading.Thread(target=pull_native_options, daemon=True).start()
    threading.Thread(target=pull_native_index, daemon=True).start()
    return sched


__all__ = [
    "ET",
    "MARKET_CLOSE",
    "MARKET_OPEN",
    "NATIVE_CACHE_FRESH_S",
    "STATE",
    "GlobalState",
    "UnderlyingState",
    "_Cadence",
    "build_native_summary",
    "flush_prices",
    "flush_tape",
    "flush_ticks",
    "market_is_open",
    "native_index_key",
    "pull_all",
    "pull_native_index",
    "pull_native_options",
    "pull_symbol",
    "pull_vix",
    "push_data_repo",
    "start_scheduler",
]
