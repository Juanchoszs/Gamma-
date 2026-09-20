import { lazy, Suspense } from "react";
import { BarChart3, CircleAlert } from "lucide-react";

const PlotlyChart = lazy(() => import("./PlotlyChart"));

const LABELS = {
  "options-flow-overlay": "Options flow overlay",
  "overview-market-map": "Overview market map",
  "gex-strike": "GEX by strike",
  "dex-strike": "DEX by strike",
  flow: "Options flow",
  gflow: "Gamma flow",
  tape: "Tape activity",
  "gex-history": "GEX history",
  "spot-zg": "Spot vs gamma flip",
  smile: "IV smile",
  "market-map-chart": "Market map",
  "unified-level-map": "Unified level map",
  profile: "Gamma profile",
  "profile-exp": "Profile by expiry",
  vex: "Vanna exposure",
  cex: "Charm exposure",
  "heatmap-intraday": "Intraday heatmap",
  "heatmap-bubbles": "Contract bubbles",
  "heatmap-term": "Term structure heatmap",
  "heatmap-hist": "Heatmap history",
  "heatmap-overlay": "GEX heatmap overlay",
  "pos-dist-graph": "Position distribution",
  "oi-change": "Open interest change",
  "pos-hist-graph": "Positioning history",
  "vol-surface": "Volatility surface",
  "iv-term-structure": "IV term structure",
  "gex-by-expiry": "GEX by expiry",
  "oi-by-expiry": "Open interest by expiry",
  "level-history-chart": "Level history",
};

const LABELS_ES = {
  "options-flow-overlay": "Overlay de flujo de opciones",
  "overview-market-map": "Mapa de mercado",
  "gex-strike": "GEX por strike",
  "dex-strike": "DEX por strike",
  flow: "Flujo de opciones",
  gflow: "Flujo gamma",
  tape: "Actividad del tape",
  "gex-history": "Historico GEX",
  "spot-zg": "Spot vs gamma flip",
  smile: "Sonrisa de IV",
  "market-map-chart": "Mapa de mercado",
  "unified-level-map": "Mapa unificado de niveles",
  profile: "Perfil gamma",
  "profile-exp": "Perfil por vencimiento",
  vex: "Exposicion vanna",
  cex: "Exposicion charm",
  "heatmap-intraday": "Heatmap intradia",
  "heatmap-bubbles": "Burbujas de contratos",
  "heatmap-term": "Heatmap por vencimiento",
  "heatmap-hist": "Historico del heatmap",
  "heatmap-overlay": "Overlay heatmap GEX",
  "pos-dist-graph": "Distribucion de posicionamiento",
  "oi-change": "Cambio de open interest",
  "pos-hist-graph": "Historico de posicionamiento",
  "vol-surface": "Superficie de volatilidad",
  "iv-term-structure": "Estructura temporal IV",
  "gex-by-expiry": "GEX por vencimiento",
  "oi-by-expiry": "Open interest por vencimiento",
  "level-history-chart": "Historico de niveles",
};

export function chartLabel(name, language = "en") {
  return (language === "es" ? LABELS_ES[name] : LABELS[name]) || name.replaceAll("-", " ");
}

export default function ChartDeck({ data, names, title = "Analytics carried from Dash", eyebrow = "CHART CATALOG", language = "en", t }) {
  const translate = t || ((key, fallback) => fallback);
  if (!names?.length) return null;
  const available = names.filter((name) => data.charts?.[name]);
  const loading = data.chartsStatus === "pending" || data.chartsStatus === "loading";
  const failed = data.chartsStatus === "error";
  const missing = names.filter((name) => !loading && data.charts && data.charts[name] === null);
  const partialErrors = Object.keys(data.chartErrors || {}).length;
  return <section className="chart-deck" aria-label={title}>
      <div className="chart-deck-heading">
      <div><span className="eyebrow"><BarChart3 size={12} /> {eyebrow}</span><h3>{title}</h3></div>
      <span className="section-note">{loading ? translate("charts.syncing", "Synchronizing figures") : `${available.length}/${names.length} ${translate("charts.liveFigures", "live figures")} · ${translate("charts.backend", "backend-owned calculations")}`}</span>
    </div>
    {loading && <div className="chart-deck-notice chart-deck-notice--loading" role="status"><span className="status-dot status-dot--live" /> {translate("charts.loadingCatalog", "Loading the Dash chart catalog for this view.")}</div>}
    {(failed || missing.length > 0 || partialErrors > 0) && <div className="chart-deck-notice" role="status"><CircleAlert size={14} /> {failed ? translate("charts.failed", "The chart service could not refresh this suite.") : translate("charts.partial", "Some figures are unavailable for this symbol or session.")}</div>}
    <div className="chart-deck-grid">
      {names.map((name) => <article className="chart-tile" key={name}>
        <div className="chart-tile-heading"><strong>{chartLabel(name, language)}</strong><span>{loading ? translate("charts.loading", "LOADING") : data.charts?.[name] ? translate("charts.live", "LIVE") : translate("charts.empty", "EMPTY")}</span></div>
        <Suspense fallback={<div className="plotly-empty">{translate("charts.loadingEngine", "Loading chart engine...")}</div>}>
          <PlotlyChart figure={data.charts?.[name]} label={chartLabel(name, language)} loading={loading} language={language} t={t} />
        </Suspense>
      </article>)}
    </div>
  </section>;
}
