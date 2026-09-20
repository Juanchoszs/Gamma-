import { useEffect, useMemo, useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { TerminalShell, StatusBar, Topbar, WorkspaceHeader } from "./components/TerminalShell";
import { ErrorState, FlowControls, LoadingState, ModuleView, Overview } from "./components/TerminalModules";
import { useTerminalData } from "./hooks/useTerminalData";
import { CHARTS_BY_PAGE, DEFAULT_LAYERS } from "./app/constants";
import { createTranslator, normalizeLanguage } from "./app/i18n";

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: true, retry: 2 } },
});

const DEFAULT_FILTERS = {
  flowType: "ALL",
  flowSide: "ALL",
  flowExpiration: "ALL",
  minPremium: "0",
  minVolume: "0",
  window: "0.03",
  timeframe: "2d",
  metric: "gex",
  interval: "5m",
  historyDays: "5",
  series: ["calls", "puts", "net"],
  profileExpiry: "ALL",
  profileSide: "ALL",
  profileMode: "NET",
  expiryMapMetric: "gex",
  expiryMapExpiries: "10",
  expiryMapStrikes: "10",
};

const KNOWN_PAGES = new Set([
  "overview", "map", "heat", "profile", "chain", "levels", "scenarios", "positioning", "flow",
  "volatility", "report", "history", "session", "settings", "diagnostics",
]);

function pageFromPath(pathname) {
  const page = pathname.split("/").filter(Boolean)[0] || "overview";
  return KNOWN_PAGES.has(page) ? page : "overview";
}

function readFilters(params) {
  const series = (params.get("series") || DEFAULT_FILTERS.series.join(","))
    .split(",")
    .filter((value) => ["calls", "puts", "net"].includes(value));
  return {
    flowType: params.get("flow") || DEFAULT_FILTERS.flowType,
    flowSide: params.get("side") || DEFAULT_FILTERS.flowSide,
    flowExpiration: params.get("flow_exp") || DEFAULT_FILTERS.flowExpiration,
    minPremium: params.get("premium") || DEFAULT_FILTERS.minPremium,
    minVolume: params.get("volume") || DEFAULT_FILTERS.minVolume,
    window: params.get("window") || DEFAULT_FILTERS.window,
    timeframe: params.get("timeframe") || DEFAULT_FILTERS.timeframe,
    metric: params.get("metric") || DEFAULT_FILTERS.metric,
    interval: ["5m", "15m"].includes(params.get("interval")) ? params.get("interval") : DEFAULT_FILTERS.interval,
    historyDays: ["1", "3", "5"].includes(params.get("sessions")) ? params.get("sessions") : DEFAULT_FILTERS.historyDays,
    series: series.length ? series : DEFAULT_FILTERS.series,
    profileExpiry: params.get("profile_exp") || DEFAULT_FILTERS.profileExpiry,
    profileSide: params.get("profile_side") || DEFAULT_FILTERS.profileSide,
    profileMode: params.get("profile_mode") || DEFAULT_FILTERS.profileMode,
    expiryMapMetric: ["gex", "oi"].includes(params.get("expiry_metric")) ? params.get("expiry_metric") : DEFAULT_FILTERS.expiryMapMetric,
    expiryMapExpiries: ["3", "5", "10"].includes(params.get("expiry_count")) ? params.get("expiry_count") : DEFAULT_FILTERS.expiryMapExpiries,
    expiryMapStrikes: ["5", "10", "15"].includes(params.get("expiry_strikes")) ? params.get("expiry_strikes") : DEFAULT_FILTERS.expiryMapStrikes,
  };
}

function TerminalApp() {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [controlsOpen, setControlsOpen] = useState(false);
  const [layers, setLayers] = useState(DEFAULT_LAYERS);
  const [filters, setFilters] = useState(() => readFilters(searchParams));
  const page = pageFromPath(location.pathname);
  const symbol = searchParams.get("symbol") || "SPY";
  const bucket = searchParams.get("bucket") || "ALL";
  const language = normalizeLanguage(searchParams.get("lang") || localStorage.getItem("gamma-language") || "en");
  const t = useMemo(() => createTranslator(language), [language]);
  const searchKey = searchParams.toString();
  const data = useTerminalData({ symbol, bucket, overlayFilters: filters, chartNames: CHARTS_BY_PAGE[page] || [], language, includePriceHistory: page === "overview", includeExpiryMap: page === "profile" });

  useEffect(() => {
    setFilters(readFilters(new URLSearchParams(searchKey)));
  }, [searchKey]);

  useEffect(() => {
    document.title = `${symbol} · Gamma Market Intelligence`;
  }, [symbol]);

  useEffect(() => {
    localStorage.setItem("gamma-language", language);
    document.documentElement.lang = language;
  }, [language]);

  const updateQuery = (updates, { replace = true } = {}) => {
    const next = new URLSearchParams(searchParams);
    Object.entries(updates).forEach(([key, value]) => {
      if (value === undefined || value === null || value === "") next.delete(key);
      else next.set(key, value);
    });
    navigate({ pathname: location.pathname || "/", search: next.toString() ? `?${next.toString()}` : "" }, { replace });
  };

  const updateFilters = (nextValue) => {
    const next = typeof nextValue === "function" ? nextValue(filters) : nextValue;
    setFilters(next);
    updateQuery({
      flow: next.flowType === DEFAULT_FILTERS.flowType ? null : next.flowType,
      side: next.flowSide === DEFAULT_FILTERS.flowSide ? null : next.flowSide,
      flow_exp: next.flowExpiration === DEFAULT_FILTERS.flowExpiration ? null : next.flowExpiration,
      premium: next.minPremium === DEFAULT_FILTERS.minPremium ? null : next.minPremium,
      volume: next.minVolume === DEFAULT_FILTERS.minVolume ? null : next.minVolume,
      window: next.window === DEFAULT_FILTERS.window ? null : next.window,
      timeframe: next.timeframe === DEFAULT_FILTERS.timeframe ? null : next.timeframe,
      metric: next.metric === DEFAULT_FILTERS.metric ? null : next.metric,
      interval: next.interval === DEFAULT_FILTERS.interval ? null : next.interval,
      sessions: next.historyDays === DEFAULT_FILTERS.historyDays ? null : next.historyDays,
      series: next.series.join(",") === DEFAULT_FILTERS.series.join(",") ? null : next.series.join(","),
      profile_exp: next.profileExpiry === DEFAULT_FILTERS.profileExpiry ? null : next.profileExpiry,
      profile_side: next.profileSide === DEFAULT_FILTERS.profileSide ? null : next.profileSide,
      profile_mode: next.profileMode === DEFAULT_FILTERS.profileMode ? null : next.profileMode,
      expiry_metric: next.expiryMapMetric === DEFAULT_FILTERS.expiryMapMetric ? null : next.expiryMapMetric,
      expiry_count: next.expiryMapExpiries === DEFAULT_FILTERS.expiryMapExpiries ? null : next.expiryMapExpiries,
      expiry_strikes: next.expiryMapStrikes === DEFAULT_FILTERS.expiryMapStrikes ? null : next.expiryMapStrikes,
    });
  };

  const navigateTo = (nextPage) => {
    navigate({ pathname: nextPage === "overview" ? "/" : `/${nextPage}`, search: location.search });
    setMobileOpen(false);
  };

  const changeLanguage = (nextLanguage) => updateQuery({ lang: normalizeLanguage(nextLanguage) });

  const selectedSymbol = data.activeSymbol || symbol;
  const content = useMemo(() => {
    if (data.status === "pending" && !data.state) return <LoadingState t={t} />;
    if (data.status === "error" && !data.state) return <ErrorState error={data.error} onRetry={data.refresh} t={t} />;
    if (page === "overview") return <Overview data={data} symbol={selectedSymbol} filters={filters} setFilters={updateFilters} layers={layers} setLayers={setLayers} controlsOpen={controlsOpen} setControlsOpen={setControlsOpen} language={language} t={t} />;
    return <ModuleView page={page} data={data} symbol={selectedSymbol} filters={filters} setFilters={updateFilters} language={language} t={t} />;
  }, [controlsOpen, data, filters, layers, language, page, selectedSymbol, t]);

  return <>
    <a className="skip-link" href="#main-content">Skip to main content</a>
    <TerminalShell page={page} collapsed={collapsed} mobileOpen={mobileOpen} language={language} t={t} onToggle={(value) => {
      if (typeof value === "boolean") setMobileOpen(value);
      else setCollapsed((current) => !current);
    }} onNavigate={navigateTo}>
      <Topbar symbol={selectedSymbol} symbols={data.symbols} bucket={bucket} language={language} onLanguageChange={changeLanguage} t={t} onSymbolChange={(value) => updateQuery({ symbol: value })} onBucketChange={(value) => updateQuery({ bucket: value })} status={data.status} isFetching={data.isFetching} onRefresh={data.refresh} onSettings={() => navigateTo("settings")} onMenu={() => setMobileOpen(true)} />
      <main id="main-content" className="workspace-pro">{page !== "overview" && <WorkspaceHeader data={data} symbol={selectedSymbol} onControls={() => setControlsOpen((value) => !value)} t={t} />}{data.error && <div className="error-banner-pro"><span>{data.error.message}</span><button onClick={data.refresh}>{t("state.retry")}</button></div>}{data.isStale && <div className="stale-notice" role="status">{t("state.staleNotice", "Showing the last valid snapshot while the engine refreshes.")}</div>}{page !== "overview" && controlsOpen && <FlowControls filters={filters} setFilters={updateFilters} t={t} />}{content}</main>
      <StatusBar data={data} symbol={selectedSymbol} t={t} />
    </TerminalShell>
  </>;
}

export default function App() {
  return <QueryClientProvider client={queryClient}><BrowserRouter basename="/terminal/"><TerminalApp /></BrowserRouter></QueryClientProvider>;
}
