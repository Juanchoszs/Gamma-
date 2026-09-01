"""Minimal read-only JSON API attached to Dash's existing Flask server
(`app.server`), allowing an external tool (charting indicator or script) on the
SAME MACHINE to read current state without using the interface.

⚠️ License scope — do not confuse this with `gex.export`, which prepares an
export intended to be SHARED and therefore filters to `source == "cboe"`.
This stream is different: it serves ALL available data, including broker
account data (dxFeed), because a "personal use, non-redistributable" license
allows the account holder to use THEIR OWN data in THEIR OWN tools (for
example, a local charting indicator). It prohibits REDISTRIBUTING THAT DATA TO
THIRD PARTIES—someone else without their own account consuming this stream
remotely. Therefore this server must not be exposed beyond the local machine
(no port forwarding or external listening on 0.0.0.0).
"""
from __future__ import annotations

from datetime import datetime
from datetime import time as dt_time

import pandas as pd
from flask import Flask, jsonify, request

from .. import metrics
from ..metrics import ET, EXPIRY_BUCKETS
from ..application.scheduler import STATE


def _summary_dict(symbol: str, s) -> dict:
    return {
        "symbol": symbol,
        "source": s.source,
        "timestamp": s.timestamp.isoformat(),
        "spot": s.spot,
        "net_gex": s.net_gex,
        "net_gex_0dte": s.net_gex_0dte,
        "zero_gamma": s.zero_gamma,
        "net_dex": s.net_dex,
        "pc_oi": s.pc_oi,
        "pc_volume": s.pc_volume,
        "basis": s.basis,
    }


# Point threshold beyond which a reversal counts as a "true" retracement, per
# instrument. Used for n_reversals; intentionally simple and recalculable later
# from raw bars.
_REV_THRESHOLD = {"NQ": 30.0, "ES": 8.0, "SPX": 10.0, "NDX": 40.0,
                  "SPY": 1.0, "QQQ": 1.2}


def _count_reversals(closes, threshold: float) -> int:
    """Count reversals in the closing-price series exceeding `threshold`.

    Zigzag: track the high and low since the last pivot; a reversal of
    `threshold` from an extreme marks a pivot. The FIRST move establishing the
    initial trend does not count; only subsequent direction changes count.
    This objectively measures how many times the market reversed, independent
    of trader perception.
    """
    if not closes:
        return 0
    n, direction = 0, 0            # 0 unknown, +1 rising, -1 falling
    hi = lo = closes[0]
    for c in closes:
        hi, lo = max(hi, c), min(lo, c)
        if direction >= 0 and hi - c >= threshold:        # reversal from a high
            if direction == 1:                            # rising trend -> true reversal
                n += 1
            direction, hi, lo = -1, c, c
        elif direction <= 0 and c - lo >= threshold:      # rebound from a low
            if direction == -1:
                n += 1
            direction, hi, lo = 1, c, c
    return n


def _session_context(symbol: str, day: str, rev_threshold: float | None = None) -> dict:
    """OBJECTIVE market truth for a session, calculated from stored 1-minute
    bars (`store.load_prices`). Used by the research log to compare what really
    happened with survey perception.

    Works intraday (partial bars for the day) and at session end. Returns
    `available: False` when no bar exists for this symbol and day.
    """
    from datetime import date as _date, timedelta
    from .. import store

    bars = store.load_prices(symbol, day)
    d = _date.fromisoformat(day)
    out = {"symbol": symbol, "date": day, "weekday": d.weekday(), "available": False}
    if bars is None or bars.empty:
        return out
    bars = bars.sort_values("timestamp")
    o = float(bars["open"].iloc[0])
    hi = float(bars["high"].max())
    lo = float(bars["low"].min())
    last = float(bars["close"].iloc[-1])

    # Prior close and ATR (average daily range over about 14 days).
    prev_close, ranges = None, []
    probe = d
    for _ in range(20):
        probe -= timedelta(days=1)
        prior = store.load_prices(symbol, probe.isoformat())
        if prior is None or prior.empty:
            continue
        if prev_close is None:
            prev_close = float(prior.sort_values("timestamp")["close"].iloc[-1])
        ranges.append(float(prior["high"].max() - prior["low"].min()))
        if len(ranges) >= 14:
            break
    prev_atr = round(sum(ranges) / len(ranges), 2) if ranges else None

    rng = hi - lo
    thr = rev_threshold or _REV_THRESHOLD.get(symbol, 30.0)
    out.update({
        "available": True,
        "open": o, "high": hi, "low": lo, "close": last, "price": last,
        "prev_close": prev_close,
        "gap": round(o - prev_close, 2) if prev_close is not None else None,
        "prev_atr": prev_atr,
        "range": round(rng, 2),
        "max_up": round(hi - o, 2),
        "max_down": round(o - lo, 2),
        "close_location": round((last - lo) / rng, 3) if rng else None,
        "n_reversals": _count_reversals(bars["close"].tolist(), thr),
        "rev_threshold": thr,
    })
    return out


def _close_context(symbol: str, day: str) -> dict:
    """Session-close pinning: did price stick to a strike/GEX wall at 16:00 ET?
    Derived on demand from raw data (around-16:00 chain snapshot and bars);
    nothing is stored. Returns `available: False` if either source is missing.
    """
    from .. import pinning, store

    out = {"symbol": symbol, "date": day, "available": False}

    # Chain closest to 16:00 ET: native (_RT) first, then CBOE.
    chain = None
    for key in (f"{symbol}_RT", symbol):
        chain = store.load_snapshot_near(key, day)
        if chain is not None and not chain.empty:
            break
    if chain is None or chain.empty or "strike" not in chain or "gex" not in chain:
        out["reason"] = "pas de snapshot de chaîne pour cette séance"
        return out

    bars = store.load_prices(symbol, day)
    if bars is None or bars.empty:
        out["reason"] = "pas de bougies (prix de clôture indisponible)"
        return out
    bars = bars.sort_values("timestamp")
    target = pd.Timestamp(f"{day} 16:00:00")
    ts = pd.to_datetime(bars["timestamp"])
    close_price = float(bars["close"].iloc[(ts - target).abs().values.argmin()])

    # Pre-close window, 15:50–16:00 ET (strike crossings).
    window = bars[(ts.dt.time >= dt_time(15, 50)) & (ts.dt.time <= dt_time(16, 0))]
    window_closes = [float(c) for c in window["close"].tolist()] or None

    out.update({"available": True})
    out.update(pinning.pin_metrics(chain, close_price, window_closes))
    return out


def _tick_context(symbol: str, day: str, entry: float | None = None,
                  stop: float | None = None, direction: int = 1) -> dict:
    """Tick-resolution close window (raw capture from 15:45–16:05 ET).

    Provides excursion metrics before/after the close and, when `entry`/`stop`
    are supplied, replays whether a stop would have been hit. Returns
    `available: False` when no ticks were captured (broker account required).
    """
    from .. import store
    from ..calculations import tickstats

    ticks = store.load_ticks(symbol, day)
    out = {"symbol": symbol, "date": day}
    if ticks is None or ticks.empty:
        out.update({"available": False, "reason": "pas de ticks capturés cette séance"})
        return out
    split = datetime.combine(datetime.fromisoformat(day).date(),
                             dt_time(16, 0), ET).timestamp()
    out.update(tickstats.window_metrics(ticks, split))
    if entry is not None and stop is not None:
        out["stop_check"] = tickstats.stop_swept(ticks, entry, stop, direction, after_ts=split)
    return out


def _preferred(symbol: str) -> str:
    """Return the STATE key to read: native _RT when configured and populated,
    otherwise the base symbol. This matches the interface's `app.chain_state`
    rule so the API shows what the dashboard shows.
    """
    from ..providers.rtquote import credentials_present
    if symbol in ("SPX", "NDX", "SPY", "QQQ") and credentials_present():
        rt = STATE.get(f"{symbol}_RT")
        with STATE.lock:
            if rt.summary is not None:
                return f"{symbol}_RT"
    return symbol


def _current_summary(symbol: str):
    """Return `(summary, enriched)` for this symbol, regardless of source."""
    st = STATE.get(_preferred(symbol))
    with STATE.lock:
        s, df = st.summary, st.enriched
    if s is None:
        return None, None
    return s, df


def register_api(app) -> None:
    """Register on a Dash app (using `.server`) or directly on a Flask app."""
    server: Flask = app.server if hasattr(app, "server") else app

    @server.after_request
    def _cors(resp):
        # This server is local-only; that is the actual safeguard, not CORS.
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp

    @server.route("/api/v1/symbols")
    def _symbols():
        out = []
        with STATE.lock:
            items = list(STATE.per_symbol.items())
        for symbol, st in items:
            if st.summary is not None:
                out.append(symbol)
        return jsonify(sorted(out))

    @server.route("/api/v1/<symbol>/summary")
    def _summary(symbol):
        symbol = symbol.upper()
        s, _ = _current_summary(symbol)
        if s is None:
            return jsonify({"error": "indisponible (pas encore de premier pull)"}), 404
        return jsonify(_summary_dict(symbol, s))

    @server.route("/api/v1/<symbol>/levels")
    def _levels(symbol):
        symbol = symbol.upper()
        s, df = _current_summary(symbol)
        if s is None or df is None:
            return jsonify({"error": "indisponible (pas encore de premier pull)"}), 404
        # Single level source (metrics.compute_levels): same walls as the
        # dashboard. structural_spot is prior close (magnitude); live_spot is
        # the current session spot (side). `?bucket=` selects expiries.
        from ..ui.app import market_is_open, ref_spot as _ref_spot
        bucket = request.args.get("bucket", "0DTE")
        if bucket not in EXPIRY_BUCKETS:
            bucket = "0DTE"
        structural = _ref_spot(symbol, s.spot)
        live = s.spot if market_is_open() else structural
        res = metrics.compute_levels(df, structural, live, bucket=bucket)
        levels, keys = res["levels"], res["keys"]
        hvl = metrics.zero_gamma(df, s.spot, weight_col="volume")

        # Optional scale conversion: ?scale=NQ expresses NDX levels in NQ
        # prices, useful when trading the future using index-derived levels.
        scale = request.args.get("scale")
        xf = (lambda v: v)
        if scale and scale.upper() != symbol:
            from ..ui.app import _transform_for
            xf, _, _ = _transform_for(symbol, scale.upper())

        def _t(v):
            return float(xf(v)) if isinstance(v, (int, float)) else v

        return jsonify({
            "symbol": symbol,
            "scale": (scale.upper() if scale else symbol),
            "spot": _t(s.spot),
            "zero_gamma": _t(s.zero_gamma),
            "hvl": _t(hvl),
            "key_levels": {k: _t(v) for k, v in keys.items()},
            "gex_walls": [
                {"strike": _t(float(r.strike)), "gex": float(r.gex), "expiry": str(r.expiry)}
                for r in levels.itertuples()
            ],
        })

    @server.route("/api/v1/<symbol>/regime")
    def _regime(symbol):
        symbol = symbol.upper()
        s, _ = _current_summary(symbol)
        if s is None:
            return jsonify({"error": "indisponible (pas encore de premier pull)"}), 404
        r = metrics.regime_read(s.net_gex, s.net_dex)
        return jsonify({
            "symbol": symbol,
            "gex_frein": r["gex_frein"],
            "dex_sign": r["dex_sign"],
            "severity": r["severity"],
            "disclaimer": "Lecture mécanique de la couverture dealers, pas un signal d'entrée.",
        })

    @server.route("/api/v1/<symbol>/strikes")
    def _strikes(symbol):
        symbol = symbol.upper()
        bucket = request.args.get("bucket", "Tout")
        s, df = _current_summary(symbol)
        if s is None or df is None:
            return jsonify({"error": "indisponible (pas encore de premier pull)"}), 404
        if bucket in EXPIRY_BUCKETS:
            today = datetime.now(ET).date()
            df = df[metrics.bucket_mask(df, bucket, today)]
        cols = ["strike", "type", "expiry", "open_interest", "gex", "dex"]
        rows = df[cols].copy()
        rows["expiry"] = rows["expiry"].astype(str)
        return jsonify({
            "symbol": symbol, "spot": s.spot, "bucket": bucket,
            "rows": rows.to_dict(orient="records"),
        })

    @server.route("/api/v1/<symbol>/session_context")
    def _session(symbol):
        """Objective session market truth (OHLC, gap, prior ATR, excursions,
        reversals) for the research log.

        `?date=YYYY-MM-DD` (default: current ET day). `?rev=` overrides the
        reversal threshold. Intraday, returns the current state (partial bars).
        """
        symbol = symbol.upper()
        day = request.args.get("date") or datetime.now(ET).date().isoformat()
        rev = request.args.get("rev", type=float)
        return jsonify(_session_context(symbol, day, rev))

    @server.route("/api/v1/<symbol>/close_context")
    def _close(symbol):
        """Close pinning at 16:00 ET: distance to strike/GEX wall, pin ratio,
        and pre-close crossings. `?date=YYYY-MM-DD` defaults to the current ET day.
        """
        symbol = symbol.upper()
        day = request.args.get("date") or datetime.now(ET).date().isoformat()
        return jsonify(_close_context(symbol, day))

    @server.route("/api/v1/<symbol>/tick_context")
    def _tick(symbol):
        """Tick close window. `?date=`; `?entry=&stop=&dir=long|short` replays
        whether a stop would have been hit.
        """
        symbol = symbol.upper()
        day = request.args.get("date") or datetime.now(ET).date().isoformat()
        entry = request.args.get("entry", type=float)
        stop = request.args.get("stop", type=float)
        direction = -1 if request.args.get("dir", "long").lower().startswith("s") else 1
        return jsonify(_tick_context(symbol, day, entry, stop, direction))

    @server.route("/api/v1/vix")
    def _vix():
        """Current VIX and digest threshold."""
        from ..application import digest as digest_mod
        v = digest_mod._current_vix()
        if v is None:
            return jsonify({"available": False})
        return jsonify({"available": True, "vix": round(float(v), 2),
                        "seuil": digest_mod.VIX_SEUIL,
                        "above": bool(v > digest_mod.VIX_SEUIL),
                        "grade": digest_mod.vix_grade(float(v))})

    @server.route("/api/v1/digest")
    def _digest():
        """Gamma-state verdict ready for distribution (see gex/digest.py).

        A Discord bot consumes the text, color, and regime `signature` (to post
        only on a real change). Returns derived analysis, never the raw chain.
        """
        from ..application import digest as digest_mod
        d = digest_mod.current_digest()
        return jsonify({
            "header": d.header,
            "lines": d.lines,
            "vix_line": d.vix_line,
            "verdict": d.verdict,
            "color": d.color,
            "discord_color": d.discord_color,
            "confidence": d.confidence,
            "families": d.families,
            "close_message": d.close_message,
            "text": d.to_text(),
            "signature": list(d.signature),
        })