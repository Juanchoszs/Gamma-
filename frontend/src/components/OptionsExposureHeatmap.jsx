import { Layers3, Table2 } from "lucide-react";
import { formatCompact, formatMoney, formatPrice } from "../lib/format";

const COLUMNS = [
  ["call_gex", "call", "Call GEX"],
  ["net_gex", "net", "Net GEX"],
  ["put_gex", "put", "Put GEX"],
];

function cleanRows(data) {
  return (data?.map?.rows || [])
    .map((row) => {
      const strike = Number(row.strike);
      if (!Number.isFinite(strike)) return null;
      const values = Object.fromEntries(COLUMNS.map(([key]) => {
        const value = Number(row[key]);
        return [key, Number.isFinite(value) ? value : null];
      }));
      if (Object.values(values).every((value) => value === null)) return null;
      return { strike, ...values };
    })
    .filter(Boolean)
    .sort((a, b) => a.strike - b.strike)
    .slice(-34);
}

function intensity(value, max) {
  if (!Number.isFinite(value) || !max) return 0;
  return Math.min(1, Math.abs(value) / max);
}

export default function OptionsExposureHeatmap({ data, t }) {
  const translate = t || ((key, fallback) => fallback);
  const rows = cleanRows(data);
  const values = rows.flatMap((row) => COLUMNS.map(([key]) => row[key]).filter(Number.isFinite));
  const max = Math.max(...values.map((value) => Math.abs(value)), 1);
  const spot = Number(data?.map?.spot);
  const nearestStrike = Number.isFinite(spot) && rows.length
    ? rows.reduce((nearest, row) => Math.abs(row.strike - spot) < Math.abs(nearest - spot) ? row.strike : nearest, rows[0].strike)
    : null;

  return <section className="surface-pro panel-pro exposure-heatmap" data-chart-id="options-exposure-heatmap">
    <div className="panel-heading-pro">
      <div><span className="eyebrow">{translate("chart.exposureEyebrow", "OPTIONS EXPOSURE")}</span><h3>{translate("chart.exposureTitle", "Strike exposure heatmap")}</h3></div>
      <Layers3 size={14} aria-hidden="true" />
    </div>
    <p className="exposure-heatmap-note">{translate("chart.exposureNote", "Real call, net and put GEX by strike from the Python market engine.")}</p>
    {rows.length ? <>
      <div className="exposure-heatmap-legend" aria-hidden="true">
        <span><i className="exposure-swatch exposure-swatch--call" />{translate("chart.calls", "Calls")}</span>
        <span><i className="exposure-swatch exposure-swatch--net" />{translate("chart.net", "Net")}</span>
        <span><i className="exposure-swatch exposure-swatch--put" />{translate("chart.puts", "Puts")}</span>
        <span className="exposure-heatmap-scale">{formatMoney(-max)} <b /> {formatMoney(max)}</span>
      </div>
      <div className="exposure-heatmap-grid" role="img" aria-label={translate("chart.exposureAria", "Options exposure heatmap by strike") }>
        <div className="exposure-heatmap-grid-header"><span>{translate("chart.strike", "Strike")}</span>{COLUMNS.map(([, tone, label]) => <span key={tone}>{translate(`chart.${tone}`, label)}</span>)}</div>
        {rows.map((row) => <div className={`exposure-heatmap-row ${row.strike === nearestStrike ? "is-spot" : ""}`} key={row.strike}>
          <span className="exposure-strike">{formatPrice(row.strike)}{row.strike === nearestStrike && <small>{translate("chart.spot", "SPOT")}</small>}</span>
          {COLUMNS.map(([key, tone, label]) => {
            const value = row[key];
            const amount = intensity(value, max);
            return <div className={`exposure-cell exposure-cell--${tone} ${value === null ? "is-empty" : value < 0 ? "is-negative" : ""}`} key={key} title={value === null ? `${label}: --` : `${label}: ${formatMoney(value)}`} style={{ "--exposure-intensity": amount }}>
              <span>{value === null ? "--" : formatCompact(value)}</span>
            </div>;
          })}
        </div>)}
      </div>
      <div className="exposure-heatmap-accessible"><Table2 size={13} aria-hidden="true" />{translate("chart.exposureAccessible", "Every heatmap cell has a signed numeric value and remains available to keyboard and screen-reader users in the table below.")}</div>
      <details className="table-disclosure exposure-heatmap-table"><summary>{translate("chart.openExposureTable", "Open numeric exposure table")}</summary><div className="table-scroll"><table className="accessible-table"><caption>{translate("chart.exposureTitle", "Strike exposure heatmap")}</caption><thead><tr><th>{translate("chart.strike", "Strike")}</th>{COLUMNS.map(([key, , label]) => <th key={key}>{translate(`chart.${key === "call_gex" ? "call" : key === "put_gex" ? "put" : "net"}`, label)}</th>)}</tr></thead><tbody>{rows.map((row) => <tr key={`table-${row.strike}`}><td>{formatPrice(row.strike)}</td>{COLUMNS.map(([key]) => <td key={key}>{row[key] === null ? "--" : formatMoney(row[key])}</td>)}</tr>)}</tbody></table></div></details>
    </> : <div className="empty-state">{translate("chart.noExposure", "No real exposure rows are available for this symbol and session.")}</div>}
  </section>;
}
