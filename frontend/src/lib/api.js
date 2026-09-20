const API_ROOT = "/api/v1";

export async function fetchJson(path, { signal } = {}) {
  const response = await fetch(path, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.error || `Request failed (${response.status})`);
  }
  return response.json();
}

export async function safeFetchJson(path, options) {
  try {
    return await fetchJson(path, options);
  } catch {
    return null;
  }
}

export function apiPath(symbol, resource, params = {}) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") search.set(key, value);
  });
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return `${API_ROOT}/${encodeURIComponent(symbol)}${resource}${suffix}`;
}

export function bucketParam(bucket) {
  return bucket === "ALL" ? "Tout" : bucket === "WEEKLY" ? "Semaine" : bucket === "MONTHLY" ? "Mois" : bucket;
}

export async function fetchTerminalSnapshot({ symbol, bucket, overlayFilters, signal }) {
  const query = { bucket: bucketParam(bucket) };
  const overlayQuery = {
    ...query,
    flow_type: overlayFilters.flowType,
    flow_side: overlayFilters.flowSide,
    flow_expiration: overlayFilters.flowExpiration,
    min_premium: overlayFilters.minPremium,
    min_volume: overlayFilters.minVolume,
    window: overlayFilters.window,
    timeframe: overlayFilters.timeframe,
  };
  const [state, map, overlay, scenarios, report, chain, session, history, alerts, summary, regime, vix, digest, diagnostics] = await Promise.all([
    fetchJson(apiPath(symbol, "/market/state", query), { signal }),
    fetchJson(apiPath(symbol, "/market/map", query), { signal }),
    fetchJson(apiPath(symbol, "/market/overlay", overlayQuery), { signal }),
    safeFetchJson(apiPath(symbol, "/market/scenarios", query), { signal }),
    safeFetchJson(apiPath(symbol, "/market/report", query), { signal }),
    safeFetchJson(apiPath(symbol, "/options/chain", { range_pct: 5, side: "ALL" }), { signal }),
    safeFetchJson(apiPath(symbol, "/market/session"), { signal }),
    safeFetchJson(apiPath(symbol, "/market/levels/history", { bucket: "Tout" }), { signal }),
    safeFetchJson(apiPath(symbol, "/market/alerts", query), { signal }),
    safeFetchJson(apiPath(symbol, "/summary"), { signal }),
    safeFetchJson(apiPath(symbol, "/regime"), { signal }),
    safeFetchJson("/api/v1/vix", { signal }),
    safeFetchJson("/api/v1/digest", { signal }),
    safeFetchJson("/api/v1/diagnostics", { signal }),
  ]);
  return {
    state,
    map,
    overlay,
    scenarios: scenarios?.scenarios || [],
    report,
    chain,
    session,
    history,
    alerts: alerts?.alerts || [],
    summary,
    regime,
    vix,
    digest,
    diagnostics,
  };
}

export async function fetchCoreSnapshot({ symbol, bucket, overlayFilters, language = "en", signal }) {
  const query = { bucket: bucketParam(bucket) };
  const overlayQuery = {
    ...query,
    flow_type: overlayFilters.flowType,
    flow_side: overlayFilters.flowSide,
    flow_expiration: overlayFilters.flowExpiration,
    min_premium: overlayFilters.minPremium,
    min_volume: overlayFilters.minVolume,
    window: overlayFilters.window,
    timeframe: overlayFilters.timeframe,
    lang: language,
  };
  const [state, map, overlay, summary, regime, vix] = await Promise.all([
    fetchJson(apiPath(symbol, "/market/state", { ...query, lang: language }), { signal }),
    fetchJson(apiPath(symbol, "/market/map", query), { signal }),
    fetchJson(apiPath(symbol, "/market/overlay", overlayQuery), { signal }),
    safeFetchJson(apiPath(symbol, "/summary"), { signal }),
    safeFetchJson(apiPath(symbol, "/regime"), { signal }),
    safeFetchJson("/api/v1/vix", { signal }),
  ]);
  return { state, map, overlay, summary, regime, vix };
}

export async function fetchDetailSnapshot({ symbol, bucket, language = "en", signal }) {
  const query = { bucket: bucketParam(bucket) };
  const [scenarios, report, chain, session, history, alerts, digest, diagnostics] = await Promise.all([
    safeFetchJson(apiPath(symbol, "/market/scenarios", { ...query, lang: language }), { signal }),
    safeFetchJson(apiPath(symbol, "/market/report", { ...query, lang: language }), { signal }),
    safeFetchJson(apiPath(symbol, "/options/chain", { range_pct: 5, side: "ALL" }), { signal }),
    safeFetchJson(apiPath(symbol, "/market/session"), { signal }),
    safeFetchJson(apiPath(symbol, "/market/levels/history", { bucket: "Tout" }), { signal }),
    safeFetchJson(apiPath(symbol, "/market/alerts", query), { signal }),
    safeFetchJson(`/api/v1/digest?lang=${language}`, { signal }),
    safeFetchJson("/api/v1/diagnostics", { signal }),
  ]);
  return {
    scenarios: scenarios?.scenarios || [],
    report,
    chain,
    session,
    history,
    alerts: alerts?.alerts || [],
    digest,
    diagnostics,
  };
}

export async function fetchChartSuite({ symbol, bucket, chartNames, window, metric, series, profileExpiry, profileSide, profileMode, language = "en", signal }) {
  const params = {
    names: chartNames.join(","),
    bucket: bucketParam(bucket),
    window,
    scale: symbol,
    metric: metric || "gex",
    series: Array.isArray(series) ? series.join(",") : series,
    profile_exp: profileExpiry,
    profile_side: profileSide,
    profile_mode: profileMode,
    lang: language,
  };
  return fetchJson(apiPath(symbol, "/market/charts", params), { signal });
}

export async function fetchPriceHistory({ symbol, days = "5", interval = "5m", signal }) {
  return fetchJson(apiPath(symbol, "/market/prices/history", { days, interval }), { signal });
}

export async function fetchExpiryExposureMap({ symbol, metric = "gex", expiries = "10", strikes = "10", signal }) {
  return fetchJson(apiPath(symbol, "/market/expiry-map", { metric, expiries, strikes }), { signal });
}

export function normalizeOverlay(overlay) {
  if (!overlay) return { priceSeries: [], previousPriceSeries: [], levels: [], bubbles: [], currentPrice: null };
  return {
    ...overlay,
    priceSeries: Array.isArray(overlay.price_series) ? overlay.price_series : [],
    previousPriceSeries: Array.isArray(overlay.previous_price_series) ? overlay.previous_price_series : [],
    levels: Array.isArray(overlay.gex_levels) ? overlay.gex_levels : [],
    bubbles: Array.isArray(overlay.flow_bubbles) ? overlay.flow_bubbles : [],
    currentPrice: overlay.current_price === null || overlay.current_price === undefined || overlay.current_price === ""
      ? null
      : (Number.isFinite(Number(overlay.current_price)) ? Number(overlay.current_price) : null),
  };
}
