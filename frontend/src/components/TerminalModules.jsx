import { Suspense, lazy } from "react";
import { Activity, AlertTriangle, ChevronRight, Database, Filter, Info, Layers3, RefreshCw, Table2 } from "lucide-react";
import OverlayTable from "./OverlayTable";
import ChartDeck from "./ChartDeck";
import MetricStrip from "./MetricStrip";
import { CHARTS_BY_PAGE, FLOW_SERIES, PROFILE_EXPIRATIONS } from "../app/constants";
import { formatCompact, formatDateTime, formatMoney, formatPercent, formatPrice, displayLabel, translateLabel } from "../lib/format";
import OptionsExposureHeatmap from "./OptionsExposureHeatmap";
import ExpiryExposureMap from "./ExpiryExposureMap";

const TerminalChart = lazy(() => import("./TerminalChart"));

export function LoadingState({ label, t }) {
  const translate = t || ((key, fallback) => fallback);
  return <div className="state-panel state-panel--loading"><span className="loading-bar" /><strong>{label || translate("state.loading", "Loading market snapshot")}</strong><small>{translate("state.syncing", "Synchronizing with the Python market engine.")}</small></div>;
}

export function ErrorState({ error, onRetry, t }) {
  const translate = t || ((key, fallback) => fallback);
  return <div className="state-panel state-panel--error"><AlertTriangle size={18} /><strong>{translate("state.unavailable", "Market data unavailable")}</strong><small>{error?.message || "The terminal could not complete this snapshot."}</small><button className="button-secondary" onClick={onRetry}><RefreshCw size={14} /> {translate("state.retry", "Retry")}</button></div>;
}

export function EmptyState({ title = "No data for this view", body = "The engine has not returned a usable snapshot for the current selection." }) {
  return <div className="state-panel"><Info size={18} /><strong>{title}</strong><small>{body}</small></div>;
}

export function FlowControls({ filters, setFilters, t }) {
  const translate = t || ((key, fallback) => fallback);
  const set = (key, value) => setFilters((current) => ({ ...current, [key]: value }));
  return <section className="controls-panel" aria-label="Overlay filters"><div className="controls-heading"><div><span className="eyebrow"><Filter size={12} /> {translate("controls.eyebrow", "OVERLAY CONTROLS")}</span><strong>{translate("controls.title", "Filter the tape and analytics surface")}</strong></div><small>{translate("controls.note", "All figures continue to use the Python engine contract.")}</small></div><div className="control-row"><div className="control-group"><span>{translate("common.flowType", "Flow type")}</span><div className="control-segment">{[["ALL", translate("common.all", "All")], ["CALLS", translate("common.calls", "Calls")], ["PUTS", translate("common.puts", "Puts")]].map(([value, label]) => <button key={value} className={filters.flowType === value ? "is-active" : ""} onClick={() => set("flowType", value)} aria-pressed={filters.flowType === value}>{label}</button>)}</div></div><div className="control-group"><span>{translate("common.side", "Side")}</span><select value={filters.flowSide} onChange={(event) => set("flowSide", event.target.value)} aria-label={translate("common.side", "Side")}><option value="ALL">{translate("controls.allSides", "All sides")}</option><option value="BUY">{translate("common.buy", "Buy")}</option><option value="SELL">{translate("common.sell", "Sell")}</option><option value="UNKNOWN">{translate("common.unknown", "Unknown")}</option></select></div><div className="control-group"><span>{translate("common.expiration", "Expiration")}</span><select value={filters.flowExpiration} onChange={(event) => set("flowExpiration", event.target.value)} aria-label={translate("common.expiration", "Expiration")}><option value="ALL">{translate("controls.allExpirations", "All expirations")}</option><option value="0DTE">0DTE</option><option value="1DTE">1DTE</option><option value="WEEKLY">Weekly</option><option value="MONTHLY">Monthly</option></select></div><label className="control-group"><span>{translate("common.minPremium", "Min premium")}</span><input type="number" min="0" step="10000" value={filters.minPremium} onChange={(event) => set("minPremium", event.target.value)} /></label><label className="control-group"><span>{translate("common.minVolume", "Min volume")}</span><input type="number" min="0" step="1" value={filters.minVolume} onChange={(event) => set("minVolume", event.target.value)} /></label><label className="control-group"><span>{translate("common.chartWindow", "Chart window")}</span><select value={filters.window} onChange={(event) => set("window", event.target.value)} aria-label={translate("common.chartWindow", "Chart window")}><option value="0.02">±2%</option><option value="0.03">±3%</option><option value="0.05">±5%</option><option value="0.08">±8%</option><option value="0.15">±15%</option></select></label><label className="control-group"><span>{translate("common.heatmapMetric", "Heatmap metric")}</span><select value={filters.metric} onChange={(event) => set("metric", event.target.value)} aria-label={translate("common.heatmapMetric", "Heatmap metric")}><option value="gex">GEX</option><option value="oi">Open interest</option><option value="vol">Volume</option></select></label><label className="control-group"><span>{translate("common.priceHistory", "Price history")}</span><select value={filters.historyDays} onChange={(event) => set("historyDays", event.target.value)} aria-label={translate("common.priceHistory", "Price history")}><option value="1">1 {translate("common.sessions", "sessions")}</option><option value="3">3 {translate("common.sessions", "sessions")}</option><option value="5">5 {translate("common.sessions", "sessions")}</option></select></label><label className="control-group"><span>{translate("common.candleInterval", "Candle interval")}</span><select value={filters.interval} onChange={(event) => set("interval", event.target.value)} aria-label={translate("common.candleInterval", "Candle interval")}><option value="5m">5m</option><option value="15m">15m</option></select></label></div></section>;
}

function ChartSuiteControls({ page, filters, setFilters, t }) {
  const translate = t || ((key, fallback) => fallback);
  const set = (key, value) => setFilters((current) => ({ ...current, [key]: value }));
  if (page === "profile") {
    return <section className="chart-suite-controls" aria-label="Gamma profile controls">
      <div className="chart-suite-controls-heading"><span className="eyebrow">{translate("controls.profile", "PROFILE CONTROLS")}</span><small>{translate("controls.profileNote", "Same expiry, side and mode controls as the Dash research view.")}</small></div>
      <div className="control-row">
        <label className="control-group"><span>{translate("common.expiry", "Expiry")}</span><select value={filters.profileExpiry} onChange={(event) => set("profileExpiry", event.target.value)} aria-label={translate("common.profileExpiry", "Profile expiry")}>{PROFILE_EXPIRATIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <div className="control-group"><span>{translate("common.side", "Side")}</span><div className="control-segment">{[["ALL", translate("common.all", "All")], ["CALLS", translate("common.calls", "Calls")], ["PUTS", translate("common.puts", "Puts")]].map(([value, label]) => <button key={value} className={filters.profileSide === value ? "is-active" : ""} onClick={() => set("profileSide", value)} aria-pressed={filters.profileSide === value}>{label}</button>)}</div></div>
        <div className="control-group"><span>{translate("common.mode", "Mode")}</span><div className="control-segment">{[["NET", translate("common.net", "Net")], ["ABSOLUTE", translate("common.absolute", "Absolute")]].map(([value, label]) => <button key={value} className={filters.profileMode === value ? "is-active" : ""} onClick={() => set("profileMode", value)} aria-pressed={filters.profileMode === value}>{label}</button>)}</div></div>
      </div>
    </section>;
  }
  if (page === "flow") {
    return <section className="chart-suite-controls" aria-label="Flow chart controls">
      <div className="chart-suite-controls-heading"><span className="eyebrow">{translate("controls.flow", "FLOW SERIES")}</span><small>{translate("controls.flowNote", "Choose the traces rendered by Gamma Flow and signed Tape.")}</small></div>
      <div className="control-row"><div className="control-group"><span>{translate("common.visibleSeries", "Visible series")}</span><div className="control-segment">{FLOW_SERIES.map(([value, label]) => { const active = filters.series.includes(value); return <button key={value} className={active ? "is-active" : ""} onClick={() => { const next = active ? filters.series.filter((item) => item !== value) : [...filters.series, value]; set("series", next.length ? next : [value]); }} aria-pressed={active}>{label}</button>; })}</div></div></div>
    </section>;
  }
  return null;
}

export function Overview({ data, symbol, filters, setFilters, layers, setLayers, controlsOpen, setControlsOpen, language, t }) {
  const chartOverlay = data.priceHistory?.rows?.length ? { ...data.overlay, priceSeries: data.priceHistory.rows } : data.overlay;
  return <div className="overview-page">
    <div className="overview-intro"><div><span className="eyebrow">{t("overview.eyebrow")}</span><h2>{t("overview.title")}</h2><p>{t("overview.subtitle")}</p></div><button className="button-secondary" onClick={() => setControlsOpen((value) => !value)}><Filter size={14} /> {controlsOpen ? t("shell.hideControls") : t("shell.showControls")}</button></div>
    {controlsOpen && <FlowControls filters={filters} setFilters={setFilters} t={t} />}
    <MetricStrip data={data} t={t} />
    <div className="overview-grid"><section className="surface-pro chart-surface-pro"><Suspense fallback={<LoadingState label={t("chart.loading", "Loading chart engine")} t={t} />}><TerminalChart overlay={chartOverlay} priceHistory={data.priceHistory} layers={layers} t={t} onToggleLayer={(key) => setLayers((current) => ({ ...current, [key]: !current[key] }))} /></Suspense></section><aside className="insight-rail"><InsightLevels data={data} t={t} /><div className="rail-rule" /><InsightFlow data={data} t={t} /></aside></div>
    <OptionsExposureHeatmap data={data} t={t} />
    <ChartDeck data={data} names={CHARTS_BY_PAGE.overview} title={t("overview.legacyTitle")} eyebrow={t("charts.parity", "LEGACY PARITY / LIVE")} language={language} t={t} />
    <div className="below-chart-grid"><section className="surface-pro panel-pro"><PanelHeading eyebrow={t("overview.ledger")} title={t("overview.eventTable")} icon={<Table2 size={14} />} /><details className="table-disclosure"><summary>{t("overview.openTable")} <ChevronRight size={14} /></summary><OverlayTable overlay={data.overlay} t={t} /></details></section><section className="surface-pro panel-pro"><PanelHeading eyebrow={t("overview.regime")} title={t("overview.context")} icon={<Layers3 size={14} />} /><ContextReadout data={data} symbol={symbol} t={t} /></section></div>
  </div>;
}

function PanelHeading({ eyebrow, title, icon }) {
  return <div className="panel-heading-pro"><div><span className="eyebrow">{eyebrow}</span><h3>{title}</h3></div>{icon}</div>;
}

function translateText(t, key, fallback) {
  return t ? t(key, fallback) : fallback;
}

function InsightLevels({ data, t }) {
  const translate = t || ((key, fallback) => fallback);
  const levels = (data.map?.levels || data.overlay?.levels || []).filter((level) => Number.isFinite(Number(level.price))).slice(0, 8);
  return <div><div className="rail-heading-pro"><span className="eyebrow">{translate("view.keyLevels", "KEY LEVELS")}</span><span className="live-label">{translateLabel(data.overlay?.freshness || "LIVE", translate)}</span></div>{levels.length ? <div className="level-list-pro">{levels.map((level) => <div className="level-row-pro" key={level.id || `${level.type}-${level.price}`}><i style={{ background: levelColor(level) }} /><div><strong>{translateLabel(level.name || level.type, translate)}</strong><small>{translateLabel(level.status || level.source || "active", translate)}</small></div><b>{formatPrice(level.price)}</b></div>)}</div> : <EmptyState title={translate("view.noLevels", "No levels")} />}</div>;
}

function InsightFlow({ data, t }) {
  const translate = t || ((key, fallback) => fallback);
  const bubbles = data.overlay?.bubbles || [];
  return <div><div className="rail-heading-pro"><span className="eyebrow">{translate("view.flowPulse", "FLOW PULSE")}</span><span className="panel-meta">{bubbles.length} {translate("common.events", "EVENTS")}</span></div>{bubbles.length ? <div className="flow-pulse-list">{bubbles.slice(-5).reverse().map((bubble) => <div className="flow-pulse-row" key={bubble.id}><span className={`flow-pulse-dot flow-pulse-dot--${bubble.option_type === "CALL" ? "call" : "put"}`} /><div><strong>{bubble.option_type} {formatPrice(bubble.strike)}</strong><small>{formatMoney(bubble.premium)} · {bubble.side === "UNKNOWN" ? translate("common.unknown", "side unknown") : bubble.side}</small></div><b>{formatDateTime(bubble.timestamp).split(",").at(-1)}</b></div>)}</div> : <EmptyState title={translate("view.noLiveFlow", "No live flow")} body={translate("view.noLiveFlowNote", "No tape events match the current overlay filters.")} />}</div>;
}

function ContextReadout({ data, symbol, t }) {
  const translate = t || ((key, fallback) => fallback);
  const state = data.state || {};
  const digest = data.digest || {};
  return <div className="context-readout"><div className="context-verdict"><span className="eyebrow">{symbol} / {translate("view.engineVerdict", "ENGINE VERDICT")}</span><strong>{translateLabel(state.gamma_regime || digest.verdict || "WAITING", translate)}</strong><p>{state.reasons?.[0] || digest.lines?.[0] || translate("report.waiting", "The next normalized snapshot will appear here.")}</p></div><div className="context-values"><div><span>{translate("report.positioning", "Positioning")}</span><b>{translateLabel(state.positioning, translate)}</b></div><div><span>{translate("report.structure", "Structure")}</span><b>{translateLabel(state.structure, translate)}</b></div><div><span>{translate("view.dataAge", "Data age")}</span><b>{data.overlay?.freshness_age_seconds != null ? `${Math.round(data.overlay.freshness_age_seconds)}s` : "--"}</b></div></div></div>;
}

export function ModuleView({ page, data, symbol, filters, setFilters, language, t }) {
  const headers = {
    map: ["MARKET MAP", "Structure around spot", "Normalized GEX and levels by strike"],
    heat: ["HEATMAPS", "Liquidity concentration", "Numeric legend with call, net and put exposure"],
    profile: ["GEX & GAMMA", "Exposure profile", "Call and put concentration by strike"],
    chain: ["OPTIONS CHAIN", "Contract positioning", `${data.chain?.row_count || 0} strikes · ${data.chain?.available_expirations?.length || 0} expirations`],
    levels: ["KEY LEVELS", "Unified market levels", "GEX engine and session profile"],
    scenarios: ["SCENARIOS", "Conditional market paths", "Engine-derived context without prediction claims"],
    positioning: ["POSITIONING", "Dealer positioning", "Net exposure around the current price"],
    flow: ["OPTIONS FLOW", "Tape and activity", "Aggregated live flow with explicit data quality"],
    volatility: ["VANNA & CHARM", "Volatility context", "Available engine outputs, without fabricated fields"],
    report: ["MARKET REPORT", "Positioning brief", "Generated from the normalized snapshot"],
    history: ["LEVEL HISTORY", "Observed levels over time", "Persisted snapshots, not inferred paths"],
    session: ["SESSION PROFILE", "Overnight and regular structure", data.session?.timezone || "Session profile"],
    diagnostics: ["DIAGNOSTICS", "Data and engine health", "Provider quality and freshness"],
    settings: ["SETTINGS", "Terminal preferences", "Presentation settings and migration status"],
  };
  const [rawEyebrow, rawTitle, rawNote] = headers[page] || headers.settings;
  const eyebrow = t(`module.${page}.eyebrow`, rawEyebrow);
  const title = t(`module.${page}.title`, rawTitle);
  const note = t(`module.${page}.note`, rawNote);
  return <div className="module-page">
    <div className="module-header"><div><span className="eyebrow">{eyebrow}</span><h2>{title}</h2></div><span className="section-note">{note}</span></div>
    <ChartSuiteControls page={page} filters={filters} setFilters={setFilters} t={t} />
    {page === "profile" && <ExpiryExposureMap data={data} filters={filters} setFilters={setFilters} t={t} />}
    <ChartDeck data={data} names={CHARTS_BY_PAGE[page]} title={`${title} ${t("charts.suite", "chart suite")}`} language={language} t={t} />
    {page === "heat" && <OptionsExposureHeatmap data={data} t={t} />}
    {page === "map" && <MarketMap data={data} t={t} />}
    {(page === "profile" || page === "positioning") && <Profile data={data} t={t} />}
    {page === "chain" && <ChainTable chain={data.chain} t={t} />}
    {page === "levels" && <Levels data={data} t={t} />}
    {page === "scenarios" && <ScenarioView data={data} t={t} language={language} />}
    {page === "flow" && <FlowView data={data} t={t} />}
    {page === "volatility" && <VolatilityView data={data} t={t} language={language} />}
    {page === "report" && <ReportView report={data.report} t={t} language={language} />}
    {page === "history" && <HistoryView history={data.history} t={t} />}
    {page === "session" && <SessionView session={data.session} t={t} />}
    {page === "diagnostics" && <DiagnosticsView diagnostics={data.diagnostics} symbol={symbol} t={t} />}
    {page === "settings" && <SettingsView t={t} />}
  </div>;
}

function MarketMap({ data, t }) {
  const translate = t || ((key, fallback) => fallback);
  const map = data.map || {};
  const rows = nearestStrikeRows(map.rows, map.spot, 30);
  const maxOpenInterest = Math.max(...rows.flatMap((row) => [Number(row.call_open_interest) || 0, Number(row.put_open_interest) || 0]), 1);
  const levelPrices = (map.levels || []).map((level) => Number(level.price)).filter(Number.isFinite);

  return <div className="module-grid module-grid--wide"><section className="surface-pro panel-pro"><PanelHeading eyebrow={translate("view.strikeMap", "STRIKE MAP")} title={translate("view.openInterestByStrike", "Open interest strength by strike")} icon={<Database size={14} />} /><div className="map-positioning-legend" aria-label={translate("view.oiStrengthNote", "Bar length is proportional to open interest on a shared scale.")}><span><i className="map-bar map-bar--call" />{translate("view.callOI", "Call OI")}</span><b>{translate("view.sharedScale", "Shared OI scale")}</b><span><i className="map-bar map-bar--put" />{translate("view.putOI", "Put OI")}</span></div><div className="map-rows-pro" role="list">{rows.map((row) => {
    const callOi = Number(row.call_open_interest) || 0;
    const putOi = Number(row.put_open_interest) || 0;
    const keyLevel = levelPrices.some((price) => Math.abs(price - Number(row.strike)) < 0.001);
    return <div className={`map-row-pro ${keyLevel ? "is-key-level" : ""}`} key={row.strike} role="listitem" title={`${formatPrice(row.strike)} · ${translate("view.callOI", "Call OI")}: ${formatCompact(callOi)} · ${translate("view.putOI", "Put OI")}: ${formatCompact(putOi)}`} aria-label={`${formatPrice(row.strike)}. ${translate("view.callOI", "Call OI")} ${formatCompact(callOi)}. ${translate("view.putOI", "Put OI")} ${formatCompact(putOi)}.`}><span>{formatPrice(row.strike)}</span><div className="map-oi-lane map-oi-lane--call" aria-hidden="true"><i className="map-bar map-bar--call" style={{ width: `${barWidth(callOi, maxOpenInterest)}%` }} /></div><div className="map-oi-lane map-oi-lane--put" aria-hidden="true"><i className="map-bar map-bar--put" style={{ width: `${barWidth(putOi, maxOpenInterest)}%` }} /></div><b className="map-oi-readout"><span className="text-call">C {formatCompact(callOi)}</span><span className="text-put">P {formatCompact(putOi)}</span></b></div>;
  })}</div></section><LevelsPanel data={data} t={t} /></div>;
}

function Profile({ data, t }) { const rows = (data.map?.rows || []).slice(-24); const max = Math.max(...rows.map((row) => Math.max(Math.abs(Number(row.call_gex) || 0), Math.abs(Number(row.put_gex) || 0))), 1); const translate = t || ((key, fallback) => fallback); return <section className="surface-pro panel-pro"><PanelHeading eyebrow={translate("view.gammaProfile", "GAMMA PROFILE")} title={translate("view.callPutExposure", "Call and put exposure")} icon={<Layers3 size={14} />} /><div className="profile-pro">{rows.map((row) => <div className="profile-row-pro" key={row.strike}><span>{formatPrice(row.strike)}</span><div className="profile-track"><i className="profile-call" style={{ width: `${Math.min(100, Math.abs(Number(row.call_gex) || 0) / max * 100)}%` }} /><i className="profile-put" style={{ width: `${Math.min(100, Math.abs(Number(row.put_gex) || 0) / max * 100)}%` }} /></div><b>{formatMoney(row.net_gex)}</b></div>)}</div></section>; }

function ChainTable({ chain, t }) { const rows = chain?.rows || []; const translate = t || ((key, fallback) => fallback); if (!rows.length) return <EmptyState title={translate("view.noOptionRows", "No option chain rows")} />; return <div className="surface-pro panel-pro"><div className="table-scroll"><table className="data-table-pro"><thead><tr><th>{translate("view.strike", "Strike")}</th><th>{translate("view.callOI", "Call OI")}</th><th>{translate("view.callGEX", "Call GEX")}</th><th>{translate("view.putOI", "Put OI")}</th><th>{translate("view.putGEX", "Put GEX")}</th><th>{translate("view.netGEX", "Net GEX")}</th><th>{translate("view.flags", "Flags")}</th></tr></thead><tbody>{rows.map((row) => <tr key={row.strike}><td className="strong-cell">{formatPrice(row.strike)}</td><td className="text-call">{formatCompact(row.call?.open_interest)}</td><td className="text-call">{formatMoney(row.call?.gex)}</td><td className="text-put">{formatCompact(row.put?.open_interest)}</td><td className="text-put">{formatMoney(row.put?.gex)}</td><td className={Number(row.net_gex) >= 0 ? "text-call" : "text-put"}>{formatMoney(row.net_gex)}</td><td>{(row.flags || []).join(" · ") || "--"}</td></tr>)}</tbody></table></div></div>; }

function Levels({ data, t }) { const translate = t || ((key, fallback) => fallback); return <div className="module-grid"><LevelsPanel data={data} t={t} /><section className="surface-pro panel-pro"><PanelHeading eyebrow={translate("view.levelStatus", "LEVEL STATUS")} title={translate("view.sourceCondition", "Source and condition")} icon={<Info size={14} />} /><div className="level-detail-list">{(data.map?.levels || []).map((level) => <div key={level.id} className="level-detail-row"><span className="level-marker" style={{ background: levelColor(level) }} /><strong>{translateLabel(level.type, translate)}</strong><span>{translateLabel(level.source, translate)}</span><b>{formatPrice(level.price)}</b><small>{translateLabel(level.status, translate)}</small></div>)}</div></section></div>; }

function LevelsPanel({ data, t }) { const translate = t || ((key, fallback) => fallback); return <section className="surface-pro panel-pro"><PanelHeading eyebrow={translate("view.keyLevels", "KEY LEVELS")} title={translate("view.priceAnchors", "Price map anchors")} icon={<Layers3 size={14} />} /><div className="level-list-pro">{(data.map?.levels || data.overlay?.levels || []).slice(0, 10).map((level) => <div className="level-row-pro" key={level.id || `${level.type}-${level.price}`}><i style={{ background: levelColor(level) }} /><div><strong>{translateLabel(level.name || level.type, translate)}</strong><small>{translateLabel(level.status || level.source || "active", translate)}</small></div><b>{formatPrice(level.price)}</b></div>)}</div></section>; }

function ScenarioView({ data, t, language }) { const translate = t || ((key, fallback) => fallback); return <div className="module-grid"><section className="surface-pro panel-pro"><PanelHeading eyebrow={translate("view.scenarioEngine", "SCENARIO ENGINE")} title={translate("view.conditionalPaths", "Conditional paths")} icon={<Layers3 size={14} />} /><div className="scenario-list-pro">{(data.scenarios || []).map((scenario) => <article className="scenario-card-pro" key={scenario.id || scenario.title}><span>{translateLabel(scenario.direction || "CONDITIONAL", translate)}</span><strong>{scenario.title}</strong><p>{scenario.trigger || scenario.description || translate("view.conditionPending", "Condition pending.")}</p><small>{translate("view.invalidation", "Invalidation")}: {scenario.invalidation || "--"}</small></article>)}</div></section><ReportView report={data.report} t={t} language={language} /></div>; }

function FlowView({ data, t }) { const translate = t || ((key, fallback) => fallback); return <div className="module-grid"><section className="surface-pro panel-pro"><PanelHeading eyebrow={translate("view.recentTape", "RECENT TAPE")} title={translate("view.aggregatedActivity", "Aggregated activity")} icon={<WavesIcon />} /><div className="flow-pulse-list">{(data.overlay?.bubbles || []).map((bubble) => <div className="flow-pulse-row" key={bubble.id}><span className={`flow-pulse-dot flow-pulse-dot--${bubble.option_type === "CALL" ? "call" : "put"}`} /><div><strong>{bubble.option_type} {formatPrice(bubble.strike)}</strong><small>{formatMoney(bubble.premium)} · {formatCompact(bubble.volume)} {translate("view.contracts", "contracts")}</small></div><b>{bubble.side === "UNKNOWN" ? translate("common.unknown", "UNKNOWN") : bubble.side}</b></div>)}</div></section><section className="surface-pro panel-pro"><PanelHeading eyebrow={translate("view.alerts", "ALERTS")} title={translate("view.transitionEvents", "Transition events")} icon={<AlertTriangle size={14} />} />{data.alerts?.length ? data.alerts.map((alert) => <div className="alert-row-pro" key={alert.id || alert.type}><strong>{translateLabel(alert.type, translate)}</strong><span>{alert.message || alert.description || translate("view.transitionDetected", "Transition detected")}</span></div>) : <EmptyState title={translate("view.noActiveTransitions", "No active transitions")} body={translate("view.alertNote", "Alerts are opt-in transition events from the same intelligence snapshot.")} />}</section></div>; }

function VolatilityView({ data, t, language }) { const translate = t || ((key, fallback) => fallback); return <div className="module-grid"><section className="surface-pro panel-pro"><PanelHeading eyebrow={translate("view.volatility", "VOLATILITY")} title={translate("view.vixRegime", "VIX and regime")} icon={<Layers3 size={14} />} /><div className="large-readout"><span>VIX</span><strong>{data.vix?.available ? formatPrice(data.vix.vix) : "--"}</strong><small>{data.vix?.grade?.label || data.vix?.grade || translate("view.noLiveVolatility", "No live volatility reading")}</small></div></section><ReportView report={data.report} t={t} language={language} /></div>; }

function ReportView({ report, t, language = "en" }) { const state = report?.market_state || {}; const translate = t || ((key, fallback) => fallback); const summaries = report?.structure_summary || report?.positioning_summary || state.reasons || []; return <section className="surface-pro panel-pro"><PanelHeading eyebrow={translate("report.eyebrow", "MARKET REPORT")} title={translate("report.title", "Positioning brief")} icon={<Info size={14} />} /><div className="report-pro"><strong>{translateLabel(state.gamma_regime || "WAITING", translate)}</strong><p>{summaries[0] || translate("report.waiting", "Waiting for the next normalized snapshot.")}</p>{summaries.length > 1 && <p className="report-secondary-line">{summaries[1]}</p>}<div className="report-stats"><div><span>{translate("report.positioning", "Positioning")}</span><b>{translateLabel(state.positioning, translate)}</b></div><div><span>{translate("report.structure", "Structure")}</span><b>{translateLabel(state.structure, translate)}</b></div><div><span>{translate("report.status", "Status")}</span><b>{translateLabel(state.data_status, translate)}</b></div></div></div></section>; }

function HistoryView({ history, t }) { const series = history?.series || []; const translate = t || ((key, fallback) => fallback); return <section className="surface-pro panel-pro"><PanelHeading eyebrow={translate("view.levelHistory", "LEVEL HISTORY")} title={history?.day || translate("view.savedObservations", "Saved observations")} icon={<LineIcon />} /><div className="history-pro">{series.slice(0, 10).map((item) => <div className="history-row-pro" key={item.id}><span>{displayLabel(item.id)}</span><div>{(item.points || []).slice(-12).map((point, index) => <i key={`${point.timestamp}-${index}`} style={{ height: `${Math.max(10, Math.min(100, Number(point.price) % 100))}%` }} />)}</div><b>{formatPrice(item.points?.at(-1)?.price)}</b></div>)}</div></section>; }

function SessionView({ session, t }) { const sessions = Object.values(session?.sessions || {}); const translate = t || ((key, fallback) => fallback); return <div className="module-grid">{sessions.map((item) => <section className="surface-pro panel-pro" key={item.session}><PanelHeading eyebrow={item.session} title={item.available ? translate("view.profileAvailable", "Profile available") : translate("view.noProfile", "No profile")} icon={<Database size={14} />} /><div className="report-stats">{Object.entries(item.levels || {}).map(([key, value]) => <div key={key}><span>{key}</span><b>{formatPrice(value)}</b></div>)}</div></section>)}</div>; }

function DiagnosticsView({ diagnostics, symbol, t }) { const current = diagnostics?.symbols?.find((item) => item.symbol === symbol) || diagnostics?.symbols?.[0]; const translate = t || ((key, fallback) => fallback); return <div className="module-grid"><section className="surface-pro panel-pro"><PanelHeading eyebrow={translate("view.dataQuality", "DATA QUALITY")} title={current?.symbol || symbol} icon={<Database size={14} />} /><div className="report-stats">{[[translate("view.status", "Status"), current?.data_status], [translate("view.options", "Options"), current?.options_count], [translate("view.strikes", "Strikes"), current?.strike_count], [translate("view.expirations", "Expirations"), current?.expiration_count], [translate("view.age", "Age"), current?.age_seconds ? `${Math.round(current.age_seconds)}s` : "--"], [translate("view.source", "Source"), current?.source]].map(([key, value]) => <div key={key}><span>{key}</span><b>{value ?? "--"}</b></div>)}</div></section><section className="surface-pro panel-pro"><PanelHeading eyebrow={translate("view.engineStatus", "ENGINE STATUS")} title={translate("view.systemHealth", "System health")} icon={<ShieldIcon />} /><div className="report-stats">{[["API", diagnostics?.api_status], ["WebSocket", diagnostics?.websocket_status], [translate("view.symbols", "Symbols"), diagnostics?.metadata?.symbol_count], [translate("view.market", "Market"), diagnostics?.metadata?.market_open ? "OPEN" : "CLOSED"]].map(([key, value]) => <div key={key}><span>{key}</span><b>{value ?? "--"}</b></div>)}</div></section></div>; }

function SettingsView({ t }) { const translate = t || ((key, fallback) => fallback); return <section className="surface-pro panel-pro"><PanelHeading eyebrow={translate("view.settings", "TERMINAL SETTINGS")} title={translate("view.implementationStatus", "Implementation status")} icon={<Layers3 size={14} />} /><div className="settings-grid-pro"><div><span>{translate("view.frontend", "Frontend")}</span><b>{translate("settings.react", "React + Tailwind + Lightweight Charts")}</b></div><div><span>{translate("view.dataLayer", "Data layer")}</span><b>{translate("settings.query", "TanStack Query · 10s refresh")}</b></div><div><span>{translate("view.engine", "Engine")}</span><b>{translate("settings.python", "Python domain services")}</b></div><div><span>{translate("view.fallback", "Fallback")}</span><b>{translate("settings.dash", "Dash remains available")}</b></div></div></section>; }

function nearestStrikeRows(rows, spot, count) { return [...(rows || [])].sort((left, right) => Math.abs(Number(left.strike) - Number(spot)) - Math.abs(Number(right.strike) - Number(spot))).slice(0, count).sort((left, right) => Number(left.strike) - Number(right.strike)); }
function barWidth(value, max) { const amount = Math.abs(Number(value) || 0); const ceiling = Number(max) || 1; return Math.max(0, Math.min(100, amount / ceiling * 100)); }
function levelColor(level) { if (level.side === "C" || level.type === "CALL_WALL" || level.color_key === "call_wall") return "var(--call)"; if (level.side === "P" || level.type === "PUT_WALL" || level.color_key === "put_wall") return "var(--put)"; return "var(--flip)"; }
function WavesIcon() { return <WavesIconPlaceholder />; }
function WavesIconPlaceholder() { return <Activity size={14} />; }
function LineIcon() { return <Table2 size={14} />; }
function ShieldIcon() { return <AlertTriangle size={14} />; }
