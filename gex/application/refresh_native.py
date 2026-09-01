"""Native futures/index options refresh use cases."""
from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

from ..providers import futopt, idxopt
from .. import store
from ..calculations.native import build_native_summary
from ..metrics import ET, SummaryMetrics
from gex.providers.rtquote import credentials_present
from ..domain.state import STATE

log = logging.getLogger(__name__)

NATIVE_CACHE_FRESH_S = 300


def native_index_key(symbol: str) -> str:
    """Clé de stockage des chaînes d'indice natives.

    Volontairement DISTINCTE du symbole CBOE : les deux sources coexistent
    sur disque sans jamais se mélanger. Le natif porte les niveaux (il n'a
    pas les 15 min de retard), CBOE continue de tourner à 60 s pour le flux
    delta — qui a besoin d'une clé `contract` stable entre deux pulls et
    d'une cadence qu'une collecte native (~20 s par chaîne) ne peut pas
    tenir. L'interface, elle, n'expose qu'un seul symbole.
    """
    return f"{symbol}_RT"


def _seed_native_state(code: str, df: pd.DataFrame, ts: datetime) -> SummaryMetrics:
    """Populate STATE from a cached or freshly fetched native snapshot."""
    snap, summary = build_native_summary(code, df, ts)
    st = STATE.get(code)
    with STATE.lock:
        st.snapshot = snap
        st.enriched = df
        st.summary = summary
        st.last_feed_ts = snap.feed_timestamp
    return summary


def pull_native_options() -> None:
    """Chaînes d'options natives NQ et ES : construit, met à jour STATE, et
    persiste — sans identifiants courtier, ne fait rien.

    Coûte du temps (~90-280 s par sous-jacent, dominé par le rythme de
    livraison du serveur, pas par notre code) : APScheduler l'exécute dans
    son propre thread, ce qui ne retarde pas les pulls CBOE de 60 s.

    Avant de payer ce coût, on regarde si un snapshot persisté a moins de
    `NATIVE_CACHE_FRESH_S` : un redémarrage du process perd STATE (mémoire
    pure) mais pas le disque — sans ce court-circuit, chaque redémarrage
    (déploiement, crash) rejouait une collecte complète même si la dernière
    date d'il y a deux minutes. La cadence normale (15 min) dépasse toujours
    ce seuil, donc ce court-circuit ne saute jamais un vrai cycle de
    rafraîchissement, seulement les redémarrages rapprochés.

    Limite connue : ne calcule pas de flux delta (`flow_delta` suppose une
    colonne `contract` façon CBOE, absente ici) — les onglets Flux et Gamma
    échangé restent vides pour NQ/ES natifs. Le reste (niveaux, profil,
    heatmap, positionnement) fonctionne, ces fonctions ne demandant que les
    colonnes déjà produites par `futopt.enrich_native`.
    """
    if not credentials_present():
        return
    for code in ("NQ", "ES"):
        cached = store.load_latest_snapshot(code)
        if cached is not None:
            df_cached, ts = cached
            age_s = (datetime.now(ET) - ts.replace(tzinfo=ET)).total_seconds()
            if 0 <= age_s < NATIVE_CACHE_FRESH_S:
                _seed_native_state(code, df_cached, ts.replace(tzinfo=ET))
                log.info("%s (natif) : cache de %.0f s, collecte live sautée",
                         code, age_s)
                continue
        try:
            df = futopt.build_native_chain(code)
            if df is None or df.empty:
                continue
            now = datetime.now(ET)
            store.save_snapshot(
                code, df, now,
                source="dxfeed",
                snapshot_type="LIVE",
                data_quality="VALID",
                market_state="LIVE",
                schema_version=1,
            )
            summary = _seed_native_state(code, df, now)
            store.append_history(summary.as_row())
            log.info("%s (natif) pull ok — spot=%.2f netGEX=%.2f Bn zeroG=%s",
                     code, summary.spot, summary.net_gex / 1e9,
                     f"{summary.zero_gamma:.0f}" if summary.zero_gamma else "n/a")
        except Exception:  # noqa: BLE001 — un échec ne doit rien casser d'autre
            log.exception("%s : échec de la collecte native", code)


def pull_native_index() -> None:
    """Chaînes d'options d'indice natives (SPX, NDX) — sans compte, ne fait rien.

    Bien plus rapide que les chaînes sur future (~20 s contre ~90 s) depuis
    l'arrêt anticipé sur complétude, d'où une cadence plus serrée : le retard
    de 15 min de CBOE est précisément ce qu'on cherche à supprimer, le
    rafraîchir toutes les 15 min n'aurait aucun sens.
    """
    if not credentials_present():
        return
    for symbol in idxopt.NATIVE_INDEX:
        try:
            df = idxopt.build_native_chain(symbol)
            if df is None or df.empty:
                continue
            now = datetime.now(ET)
            key = native_index_key(symbol)
            store.save_snapshot(
                key, df, now,
                source="dxfeed",
                snapshot_type="LIVE",
                data_quality="VALID",
                market_state="LIVE",
                schema_version=1,
            )
            summary = _seed_native_state(key, df, now)
            store.append_history(summary.as_row())
            log.info("%s (indice natif) pull ok — spot=%.2f netGEX=%.2f Bn zeroG=%s",
                     symbol, summary.spot, summary.net_gex / 1e9,
                     f"{summary.zero_gamma:.0f}" if summary.zero_gamma else "n/a")
        except Exception:  # noqa: BLE001 — un échec ne doit rien casser d'autre
            log.exception("%s : échec de la chaîne d'indice native", symbol)
