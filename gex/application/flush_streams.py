"""Drain in-memory market streams onto disk."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from .. import flowtape, roll, store
from ..metrics import ET
from ..rtquote import PUBLIC_QUOTES, QUOTES
from ..tickcapture import CAPTURE

log = logging.getLogger(__name__)


def _flush_bars(bars: list, source: str) -> None:
    """Écrit sur disque les bougies 1 min achevées, quelle que soit la
    source (compte courtier ou repli public délayé — cf. flush_prices)."""
    if not bars:
        return
    by_symbol: dict[str, list[dict]] = {}
    for symbol, bar in bars:
        ts = datetime.fromtimestamp(bar.minute, tz=UTC).astimezone(ET).replace(tzinfo=None)
        by_symbol.setdefault(symbol, []).append({
            "timestamp": ts, "open": bar.open, "high": bar.high,
            "low": bar.low, "close": bar.close, "ticks": bar.ticks,
            "source": source,
        })
    for symbol, rows in by_symbol.items():
        try:
            store.append_prices(symbol, rows, rows[0]["timestamp"])
        except Exception:  # noqa: BLE001 — une écriture ratée ne doit rien casser
            log.exception("Échec écriture des prix %s", symbol)


def flush_prices() -> None:
    """Écrit sur disque les bougies 1 min achevées par le flux temps réel.

    Sans identifiants courtier, `QUOTES.drain_bars()` renvoie une liste vide
    (la couche temps réel payante est inerte), mais `PUBLIC_QUOTES` — le
    repli gratuit délayé sur NQ/ES (cf. rtquote.PublicDelayedQuotes) —
    construit ses propres bougies de la même façon et doit être vidé lui
    aussi : sans cette ligne, ses bougies s'accumulaient en mémoire sans
    jamais être écrites, et le Heatmap retombait sur le repli grossier
    (un point par pull, ~10 min) même là où un spot délayé existait déjà.

    Provenance marquée à l'écriture : "dxfeed" (courtier, licence usage
    personnel non redistribuable) ou "dxfeed_public" (flux démo public,
    délayé ~15-20 min) — les deux exclues de l'export par défaut (cf.
    gex/export.py, qui n'autorise que source == "cboe"), mais distinguées
    pour ne jamais laisser croire que l'une est l'autre.
    """
    _flush_bars(QUOTES.drain_bars(), "dxfeed")
    _flush_bars(PUBLIC_QUOTES.drain_bars(), "dxfeed_public")


def flush_tape() -> None:
    """Écrit les barres d'order flow signé achevées (cf. gex/flowtape.py).

    Même logique que `flush_prices` : le collecteur agrège en mémoire (~2,4 M
    de prints par séance, hors de question de les persister un par un), seules
    les barres d'une minute touchent le disque.
    """
    bars = flowtape.TAPE.drain_bars()
    if not bars:
        return
    by_symbol: dict[str, list[dict]] = {}
    for symbol, bar in bars:
        ts = datetime.fromtimestamp(bar.minute, tz=UTC).astimezone(ET).replace(tzinfo=None)
        by_symbol.setdefault(symbol, []).append(bar.as_row(symbol, ts))
    for symbol, rows in by_symbol.items():
        try:
            store.append_tape(symbol, rows, rows[0]["timestamp"])
        except Exception:  # noqa: BLE001 — une écriture ratée ne doit rien casser
            log.exception("Échec écriture de l'order flow %s", symbol)


def flush_ticks() -> None:
    """Écrit sur disque le brut tick-par-tick accumulé par la capture continue
    (cf. gex/tickcapture). Même logique que flush_prices/flush_tape : le
    collecteur agrège en mémoire, seul le flush touche le disque — ici vers le
    parquet JOURNALIER de chaque contrat, chaque tick rangé selon sa SÉANCE CME,
    définie en HEURE DE NEW YORK : 18:00 ET (ouverture) -> 16:59 ET (clôture) du
    lendemain, soit `date = (heure ET + 6h).date()`.

    ⚠️ Surtout PAS un découpage à l'heure de Paris : Paris ne vaut ET+6 que
    lorsque les deux zones sont en heure d'été en même temps. Pendant les ~3
    semaines par an où les bascules US et UE sont décalées (mi-mars, fin
    octobre), l'écart tombe à 5 h et le fichier commence à 19:00 ET au lieu de
    18:00 — la séance est alors coupée au mauvais endroit. L'ET est la seule
    référence stable, parce que c'est celle du marché lui-même."""
    buf = CAPTURE.drain()
    for symbol, per_contract in buf.items():
        # 1. Regrouper par (séance, contrat) et cumuler le volume de CHAQUE
        #    contrat — y compris celui qu'on n'écrira pas : c'est cette mesure
        #    qui décidera du dominant de la séance suivante (cf. gex/roll).
        by_day: dict[str, dict[str, list]] = {}
        volumes: dict[str, dict[str, float]] = {}
        for contract, rows in per_contract.items():
            for r in rows:
                # +6 h : 18:00 ET (ouverture) bascule sur minuit, donc la date
                # obtenue EST celle de la séance, y compris la partie du soir.
                sess = (datetime.fromtimestamp(r["ts"], tz=UTC).astimezone(ET)
                        + timedelta(hours=6))
                day = sess.strftime("%Y-%m-%d")
                by_day.setdefault(day, {}).setdefault(contract, []).append((sess, r))
                volumes.setdefault(day, {})[contract] = (
                    volumes.setdefault(day, {}).get(contract, 0) + (r.get("volume") or 0))

        for day, per_c in by_day.items():
            try:
                roll.record_volumes(symbol, day, volumes.get(day, {}))
            except Exception:  # noqa: BLE001 — l'état de roll ne doit rien bloquer
                log.exception("Capture tick : échec mémorisation des volumes %s", symbol)
            # 2. N'écrire que le contrat dominant : la série sur disque reste
            #    une série CONTINUE, comparable au jeu de référence. L'ordre
            #    passé est celui du courtier ([actif, suivant]) : c'est lui qui
            #    sert de repli tant qu'aucun volume de veille n'est connu.
            contracts = [c for c in CAPTURE.contract_order(symbol) if c in per_c]
            contracts += [c for c in per_c if c not in contracts]
            keep = roll.dominant(symbol, day, contracts)
            items = per_c.get(keep) or []
            if not items:
                continue
            rows_day = [it[1] for it in items]
            try:
                store.append_ticks(symbol, rows_day, items[0][0])
            except Exception:  # noqa: BLE001 — une écriture ratée ne doit rien casser
                log.exception("Capture tick : échec écriture %s", symbol)
