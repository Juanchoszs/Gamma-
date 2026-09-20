import { Grid3X3, Table2 } from "lucide-react";
import { formatCompact, formatMoney, formatPrice } from "../lib/format";

function valueTone(value) {
  if (!Number.isFinite(value) || value === 0) return "zero";
  return value > 0 ? "positive" : "negative";
}

function intensity(value, max) {
  if (!Number.isFinite(value) || max <= 0) return 0;
  return Math.min(1, Math.log1p(Math.abs(value)) / Math.log1p(max));
}

function signedCompact(value) {
  if (!Number.isFinite(value)) return "--";
  return `${value > 0 ? "+" : ""}${formatCompact(value)}`;
}

function levelPrice(levels, type) {
  const level = (levels || []).find((item) => item.type === type);
  return Number.isFinite(Number(level?.price)) ? formatPrice(level.price) : "--";
}

export default function ExpiryExposureMap({ data, filters, setFilters, t }) {
  const translate = t || ((key, fallback) => fallback);
  const map = data?.expiryMap;
  const metric = map?.metric || filters.expiryMapMetric;
  const expirations = Array.isArray(map?.expirations) ? map.expirations : [];
  const rows = Array.isArray(map?.rows) ? map.rows : [];
  const values = rows.flatMap((row) => row.values || []).filter(Number.isFinite);
  const max = Math.max(...values.map((value) => Math.abs(value)), 1);
  const metricLabel = metric === "oi" ? translate("expiryMap.oi", "Open interest") : translate("expiryMap.gex", "Net GEX");
  const totalLabel = metric === "oi" ? translate("expiryMap.oiByExpiry", "OI by expiry") : translate("expiryMap.gexByExpiry", "Net GEX by expiry");
  const scaleLabel = metric === "oi" ? `${formatCompact(0)} to ${formatCompact(max)}` : `${formatMoney(-max)} to ${formatMoney(max)}`;
  const set = (key, value) => setFilters((current) => ({ ...current, [key]: value }));
  const totalFormat = metric === "oi" ? formatCompact : formatMoney;
  const summary = [
    [translate("metric.spot", "Spot"), formatPrice(map?.spot)],
    [metricLabel, totalFormat((map?.expiry_totals || []).reduce((total, value) => total + (Number(value) || 0), 0))],
    [translate("metric.callWall", "Call Wall"), levelPrice(data?.map?.levels, "CALL_WALL")],
    [translate("metric.putWall", "Put Wall"), levelPrice(data?.map?.levels, "PUT_WALL")],
    [translate("metric.gammaFlip", "Gamma Flip"), levelPrice(data?.map?.levels, "GAMMA_FLIP")],
  ];

  return <section className="surface-pro expiry-map" data-chart-id="expiry-exposure-map">
    <header className="expiry-map-heading">
      <div><span className="eyebrow">{translate("expiryMap.eyebrow", "EXPIRY EXPOSURE")}</span><h3>{translate("expiryMap.title", "GEX / OI by strike and expiry")}</h3><p>{translate("expiryMap.note", "Current options chain, aggregated by the Python market engine.")}</p></div>
      <Grid3X3 size={16} aria-hidden="true" />
    </header>
    <div className="expiry-map-controls">
      <label><span>{translate("expiryMap.metric", "Metric")}</span><select value={filters.expiryMapMetric} onChange={(event) => set("expiryMapMetric", event.target.value)} aria-label={translate("expiryMap.metric", "Metric")}><option value="gex">{translate("expiryMap.gex", "Net GEX")}</option><option value="oi">{translate("expiryMap.oi", "Open interest")}</option></select></label>
      <label><span>{translate("expiryMap.nearestExpiries", "Nearest expiries")}</span><select value={filters.expiryMapExpiries} onChange={(event) => set("expiryMapExpiries", event.target.value)} aria-label={translate("expiryMap.nearestExpiries", "Nearest expiries")}><option value="3">3</option><option value="5">5</option><option value="10">10</option></select></label>
      <label><span>{translate("expiryMap.strikesEachSide", "Strikes each side")}</span><select value={filters.expiryMapStrikes} onChange={(event) => set("expiryMapStrikes", event.target.value)} aria-label={translate("expiryMap.strikesEachSide", "Strikes each side")}><option value="5">5</option><option value="10">10</option><option value="15">15</option></select></label>
      <span className="expiry-map-scale" aria-label={scaleLabel}>{metric === "oi" ? <><i data-sign="zero" />{translate("expiryMap.lower", "Lower")}<i data-sign="positive" />{translate("expiryMap.higher", "Higher")}</> : <><i data-sign="negative" />{translate("expiryMap.negative", "Negative")}<i data-sign="zero" />0<i data-sign="positive" />{translate("expiryMap.positive", "Positive")}</>}</span>
    </div>
    <div className="expiry-map-summary">{summary.map(([label, value]) => <div key={label}><span>{label}</span><b>{value}</b></div>)}</div>
    {rows.length && expirations.length ? <>
      <div className="expiry-map-scroll">
        <div className="expiry-map-grid" role="grid" aria-label={translate("expiryMap.aria", "Options exposure by strike and expiry")} style={{ "--expiry-columns": expirations.length }}>
          <div className="expiry-map-grid-header" role="row"><span role="columnheader">{translate("chart.strike", "Strike")}</span>{expirations.map((expiry) => <span role="columnheader" key={expiry}>{expiry}</span>)}</div>
          <div className="expiry-map-total-row" role="row"><span role="rowheader">{totalLabel}</span>{(map.expiry_totals || []).map((value, index) => <span role="gridcell" key={`${expirations[index]}-total`} className={valueTone(value)}>{metric === "oi" ? formatCompact(value) : signedCompact(value)}</span>)}</div>
          {rows.map((row) => <div className={`expiry-map-row ${row.is_atm ? "is-atm" : ""}`} role="row" key={row.strike}>
            <span role="rowheader" className="expiry-map-strike">{formatPrice(row.strike)}{row.is_atm && <small>{translate("expiryMap.atSpot", "AT SPOT")}</small>}</span>
            {(row.values || []).map((value, index) => <span key={`${row.strike}-${expirations[index]}`} role="gridcell" tabIndex="0" title={`${metricLabel}: ${metric === "oi" ? formatCompact(value) : formatMoney(value)}`} aria-label={`${formatPrice(row.strike)}, ${expirations[index]}, ${metricLabel}: ${metric === "oi" ? formatCompact(value) : formatMoney(value)}`} className={`expiry-map-cell ${valueTone(value)}`} style={{ "--exposure-intensity": intensity(value, max) }}>{metric === "oi" ? formatCompact(value) : signedCompact(value)}</span>)}
          </div>)}
        </div>
      </div>
      <div className="expiry-map-accessible"><Table2 size={13} aria-hidden="true" />{translate("expiryMap.accessible", "Every matrix value is signed, keyboard reachable and available in the table below.")}</div>
      <details className="table-disclosure expiry-map-table"><summary>{translate("expiryMap.openTable", "Open numeric matrix")}</summary><div className="table-scroll"><table className="accessible-table"><caption>{translate("expiryMap.title", "GEX / OI by strike and expiry")}</caption><thead><tr><th>{translate("chart.strike", "Strike")}</th>{expirations.map((expiry) => <th key={expiry}>{expiry}</th>)}</tr></thead><tbody>{rows.map((row) => <tr key={`table-${row.strike}`}><td>{formatPrice(row.strike)}</td>{(row.values || []).map((value, index) => <td key={`${row.strike}-${expirations[index]}`}>{metric === "oi" ? formatCompact(value) : formatMoney(value)}</td>)}</tr>)}</tbody></table></div></details>
    </> : <div className="empty-state">{translate("expiryMap.empty", "No real expiry exposure rows are available for this symbol and session.")}</div>}
  </section>;
}
