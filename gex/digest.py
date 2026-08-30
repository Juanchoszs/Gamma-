"""GEX dashboard application."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

PARIS = ZoneInfo("Europe/Paris")


SYMBOLS = ("SPX", "SPY", "NDX", "QQQ", "ES", "NQ")


VIX_SEUIL = 16.0
VIX_IMPACT = 20.0




VIX_GRADES = (
    (12.0, "Complaisance", "😴"),
    (16.0, "Calme", "🟢"),
    (20.0, "Normal-haut", "🟡"),
    (25.0, "Élevé", "🟠"),
    (35.0, "Stress", "🔴"),
    (float("inf"), "Panique", "🚨"),
)
FORT_PERCENTILE = 0.67
FORT_MIN_HISTORY = 20


COLORS = {"green": 0x2ECC71, "orange": 0xE67E22, "red": 0xE74C3C}





_LECTURE_RISQUE = {
    ("Gamma Positif", "Delta Négatif"): "Réduire le risque sur les shorts | Long avec très peu de risque",
    ("Gamma Positif", "Delta Positif"): "Réduire le risque sur les longs | Short avec très peu de risque",
}







FAMILLES = {
    "S&P":    {"principal": "SPX", "poids": {"SPX": 3, "SPY": 2, "ES": 1}},
    "Nasdaq": {"principal": "NDX", "poids": {"NDX": 3, "QQQ": 2, "NQ": 1}},
}


FAMILLE_FORT_SEUIL = -1.5
_CONF_RANG = {"faible": 0, "moyenne": 1, "forte": 2}


@dataclass
class Digest:
    header: str
    lines: list[str]
    vix_line: str | None
    verdict: str
    color: str
    confidence: str | None = None
    signature: tuple = field(default_factory=tuple)
    families: dict = field(default_factory=dict)
    close_message: str = ""

    def to_text(self) -> str:
        parts = [self.header, ""] + self.lines
        if self.vix_line:
            parts.append(self.vix_line)
        parts += ["", self.verdict]
        if self.confidence:
            parts.append(f"Confiance : {self.confidence.capitalize()}")
        return "\n".join(parts)

    @property
    def discord_color(self) -> int:
        return COLORS[self.color]


def vix_grade(vix: float | None) -> dict | None:
    """Build the requested dashboard output."""
    if vix is None:
        return None
    for sup, label, emoji in VIX_GRADES:
        if vix < sup:
            return {"label": label, "emoji": emoji}
    return {"label": VIX_GRADES[-1][1], "emoji": VIX_GRADES[-1][2]}


def _header(now: datetime) -> str:
    p = now.astimezone(PARIS)
    off = int((p.utcoffset() or pd.Timedelta(0)).total_seconds() // 3600)
    return f"État du gamma à {p.hour}h{p.minute:02d} GMT{off:+d} (Paris)"


def _is_fort(net_gex: float, hist) -> bool:
    """Internal helper."""
    if net_gex >= 0 or hist is None:
        return False
    ref = pd.Series(list(hist), dtype="float64").dropna().abs()
    if len(ref) < FORT_MIN_HISTORY:
        return False
    return bool((ref < abs(net_gex)).mean() >= FORT_PERCENTILE)


def classify(net_gex: float, net_dex: float, hist=None) -> dict:
    """Build the requested dashboard output."""
    fort = _is_fort(net_gex, hist)
    if fort:
        gamma = "Fort Gamma Négatif"
    elif net_gex < 0:
        gamma = "Gamma Négatif"
    else:
        gamma = "Gamma Positif"
    delta_pos = net_dex >= 0
    delta = "Delta Positif" if delta_pos else "Delta Négatif"

    gloss = "Dealers long gamma" if delta_pos else "Dealers short gamma"
    return {"gamma": gamma, "delta": delta, "gloss": gloss,
            "neg": net_gex < 0, "fort": fort}




_GAMMA_EN = {"Gamma Positif": "Positive Gamma", "Gamma Négatif": "Negative Gamma",
             "Fort Gamma Négatif": "Strong Negative Gamma"}
_DELTA_EN = {"Delta Positif": "Positive Delta", "Delta Négatif": "Negative Delta"}
_LECTURE_RISQUE_EN = {
    ("Gamma Positif", "Delta Négatif"): "Reduce risk on shorts | Long with very little risk",
    ("Gamma Positif", "Delta Positif"): "Reduce risk on longs | Short with very little risk",
}


def symbol_reading(net_gex: float, net_dex: float, hist=None,
                   lang: str = "fr") -> dict:
    """Build the requested dashboard output."""
    c = classify(net_gex, net_dex, hist)
    if lang == "en":
        gamma, delta = _GAMMA_EN.get(c["gamma"], c["gamma"]), _DELTA_EN.get(c["delta"], c["delta"])
        lecture = _LECTURE_RISQUE_EN.get((c["gamma"], c["delta"]))
    else:
        gamma, delta = c["gamma"], c["delta"]
        lecture = _LECTURE_RISQUE.get((c["gamma"], c["delta"]))
    text = f"{gamma} - {delta} ({c['gloss']})"
    if lecture:
        text += f"\n→ {lecture}"
    return {"text": text, "gamma": c["gamma"]}


def build_digest(rows: list[dict], vix: float | None = None,
                 now: datetime | None = None, vix_seuil: float = VIX_SEUIL) -> Digest:
    """Build the requested dashboard output."""
    now = now or datetime.now(PARIS)
    by_symbol = {r["symbol"]: r for r in rows if r.get("symbol") in SYMBOLS
                 and r.get("net_gex") is not None}



    groupes: dict[tuple, list[str]] = {}
    etats: dict[str, dict] = {}
    for sym in SYMBOLS:
        r = by_symbol.get(sym)
        if r is None:
            continue
        c = classify(float(r["net_gex"]), float(r.get("net_dex") or 0.0),
                     r.get("hist"))
        etats[sym] = c
        groupes.setdefault((c["gamma"], c["delta"], c["gloss"]), []).append(sym)

    lines = []
    for (gamma, delta, gloss), syms in groupes.items():
        lines.append(f"{gamma} - {delta} ({gloss}) sur {_liste(syms)}")
        lecture = _LECTURE_RISQUE.get((gamma, delta))
        if lecture:
            lines.append(f"→ {lecture}")

    vix_line = (f"VIX supérieur à {int(vix_seuil)} ! (actuellement {vix:.2f})"
                if vix is not None and vix > vix_seuil else None)

    color, verdict, familles = _verdict(etats, vix, vix_seuil)
    confidence = _confiance_globale(familles)



    signature = tuple(sorted((nom, f["statut"]) for nom, f in familles.items()))
    signature += (("couleur", color),)
    return Digest(_header(now), lines, vix_line, verdict, color, confidence,
                  signature, familles, _close_message(etats))


def _liste(syms: list[str]) -> str:
    """Internal helper."""
    if len(syms) == 1:
        return syms[0]
    return ", ".join(syms[:-1]) + " et " + syms[-1]


def _intensite(c: dict) -> int:
    """Internal helper."""
    if c["fort"]:
        return -2
    return -1 if c["neg"] else 1


def _famille(etats: dict[str, dict], poids: dict[str, int],
             principal: str) -> dict | None:
    """Internal helper."""
    presents = {s: etats[s] for s in poids if s in etats}
    if not presents:
        return None
    w = sum(poids[s] for s in presents)
    score = sum(poids[s] * _intensite(presents[s]) for s in presents) / w

    principal_present = principal in presents
    principal_fort = principal_present and presents[principal]["fort"]
    if principal_fort or (not principal_present and score <= FAMILLE_FORT_SEUIL):
        statut = "fort_neg"
    elif score < 0:
        statut = "neg"
    else:
        statut = "pos"

    signes = {1 if _intensite(c) > 0 else -1 for c in presents.values()}
    contradiction = len(signes) > 1
    complet = w == sum(poids.values())
    if not principal_present or contradiction:
        confiance = "faible"
    elif complet:
        confiance = "forte"
    else:
        confiance = "moyenne"
    return {"score": score, "statut": statut, "confiance": confiance}


def _confiance_globale(familles: dict[str, dict]) -> str | None:
    """Internal helper."""
    if not familles:
        return None
    return min((f["confiance"] for f in familles.values()),
               key=lambda c: _CONF_RANG[c])


def _verdict(etats: dict[str, dict], vix: float | None,
             vix_seuil: float) -> tuple[str, str, dict[str, dict]]:
    """Internal helper."""
    familles = {}
    for nom, spec in FAMILLES.items():
        r = _famille(etats, spec["poids"], spec["principal"])
        if r is not None:
            familles[nom] = r

    n_neg = sum(1 for f in familles.values() if f["statut"] in ("neg", "fort_neg"))
    fort = any(f["statut"] == "fort_neg" for f in familles.values())
    vix_haut = vix is not None and vix >= VIX_IMPACT

    if fort or n_neg >= 2:
        return "red", "Trading contrarien déconseillé sur session US.", familles
    if n_neg == 1:
        return "orange", "Trading contrarien risqué sur session US.", familles
    if vix_haut:
        return ("orange",
                "Trading contrarien risqué sur session US — forte amplitude attendue.",
                familles)
    return "green", _verdict_vert(etats), familles



_CLOSE_SYMBOLS = ("NQ", "ES")
_ARTICLES = {"NQ": "le NQ", "ES": "l'ES", "SPX": "le SPX", "NDX": "le NDX",
             "SPY": "le SPY", "QQQ": "le QQQ"}


def _join_syms(syms: list[str]) -> str:
    """Internal helper."""
    labels = [_ARTICLES.get(s, s) for s in syms]
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + " et " + labels[-1]


def _close_message(etats: dict[str, dict]) -> str:
    """Internal helper."""
    long_, short_, ampli = [], [], []
    for sym in _CLOSE_SYMBOLS:
        e = etats.get(sym)
        if e is None:
            continue
        if e["neg"]:
            ampli.append(sym)
        elif e["delta"] == "Delta Négatif":
            long_.append(sym)
        else:
            short_.append(sym)

    parts = []
    if long_:
        parts.append(f"**long** sur {_join_syms(long_)}")
    if short_:
        parts.append(f"**short** sur {_join_syms(short_)}")
    milieu = ("Actuellement les Market Makers sont " + " et ".join(parts) + "."
              if parts else "")
    if ampli:
        v = "est" if len(ampli) == 1 else "sont"
        amp = _join_syms(ampli)
        amp = amp[:1].upper() + amp[1:]
        warn = (f"⚠️ {amp} {v} en régime **amplificateur de mouvement** — ça "
                f"risque de mal se passer.")
        milieu = f"{milieu} {warn}" if milieu else warn
    if not milieu:
        milieu = "Positionnement des Market Makers indéterminé (pas de données NQ/ES)."

    return ("🔒 Stop le trading contrarien si tu n'es pas en position ; si tu es en "
            "position, sors dès que tu peux. " + milieu +
            " Verrouille ton trading et va profiter de ta soirée. 🌙")


def _verdict_vert(etats: dict[str, dict]) -> str:
    """Internal helper."""
    n_neg = sum(1 for e in etats.values() if e["delta"] == "Delta Négatif")
    n_pos = sum(1 for e in etats.values() if e["delta"] == "Delta Positif")
    if n_neg > n_pos:
        return ("Trading contrarien sur session US : très peu de risque sur les "
                "longs, risqué sur les shorts.")
    if n_pos > n_neg:
        return ("Trading contrarien sur session US : très peu de risque sur les "
                "shorts, risqué sur les longs.")
    return "Trading contrarien avec peu de risque sur session US."







def _preferred_key(symbol: str) -> str:
    """Internal helper."""
    from .rtquote import credentials_present
    from .scheduler import STATE
    if symbol in ("SPX", "NDX", "SPY", "QQQ") and credentials_present():
        rt = STATE.get(f"{symbol}_RT")
        with STATE.lock:
            if rt.summary is not None:
                return f"{symbol}_RT"
    return symbol


def _current_vix() -> float | None:
    from .rtquote import QUOTES, credentials_present
    from . import store
    live = QUOTES.price("VIX") if credentials_present() else None
    if live:
        return float(live)
    hist = store.load_index_spot("vix")
    if not hist.empty:
        return float(hist.sort_values("timestamp")["vix"].iloc[-1])
    return None


def current_digest(now: datetime | None = None) -> Digest:
    """Build the requested dashboard output."""
    from . import store
    from .scheduler import STATE
    rows = []
    for sym in SYMBOLS:
        key = _preferred_key(sym)
        st = STATE.get(key)
        with STATE.lock:
            s = st.summary
        if s is None:
            continue
        hist = store.load_history(key)
        rows.append({
            "symbol": sym,
            "net_gex": s.net_gex,
            "net_dex": s.net_dex,
            "hist": hist["net_gex"] if not hist.empty and "net_gex" in hist else None,
        })
    return build_digest(rows, vix=_current_vix(), now=now)
