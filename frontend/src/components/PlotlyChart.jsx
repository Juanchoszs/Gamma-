import createPlotlyComponent from "react-plotly.js/factory";
import Plotly from "plotly.js-cartesian-dist-min";
import { localizePlotlyFigure } from "../lib/plotlyI18n";

const Plot = createPlotlyComponent(Plotly);

const CHART_COLORS = new Map([
  ["#2dd4bf", "#58b6c4"],
  ["#34d399", "#6b93e5"],
  ["#22d3ee", "#58b6c4"],
  ["#00f0ff", "#58b6c4"],
  ["#f05c7c", "#d98795"],
  ["#ff2e74", "#d98795"],
  ["#f6c85f", "#d8b65a"],
]);

function recolor(value) {
  if (typeof value !== "string") return value;
  return CHART_COLORS.get(value.toLowerCase()) || value;
}

function recolorTrace(trace) {
  const next = { ...trace };
  if (next.line) next.line = { ...next.line, color: recolor(next.line.color) };
  if (next.marker) {
    next.marker = {
      ...next.marker,
      color: Array.isArray(next.marker.color) ? next.marker.color.map(recolor) : recolor(next.marker.color),
      line: next.marker.line ? { ...next.marker.line, color: recolor(next.marker.line.color) } : next.marker.line,
    };
  }
  if (next.fillcolor) next.fillcolor = recolor(next.fillcolor);
  if (Array.isArray(next.colorscale)) next.colorscale = next.colorscale.map(([stop, color]) => [stop, recolor(color)]);
  return next;
}

function axisTheme(axis = {}) {
  const title = typeof axis.title === "string" ? { text: axis.title } : axis.title;
  return {
    ...axis,
    gridcolor: "#1c2a33",
    zerolinecolor: "#30414c",
    linecolor: "#30414c",
    tickfont: { ...(axis.tickfont || {}), color: "#8e9da7", size: 10 },
    title: title ? { ...title, font: { ...(title.font || {}), color: "#8e9da7", size: 10 } } : title,
  };
}

function accessibleRows(figure) {
  const rows = [];
  (figure.data || []).slice(0, 6).forEach((trace, traceIndex) => {
    const x = Array.isArray(trace.x) ? trace.x : [];
    const y = Array.isArray(trace.y) ? trace.y : [];
    const count = Math.min(Math.max(x.length, y.length), 20);
    for (let index = 0; index < count && rows.length < 48; index += 1) {
      rows.push({
        series: trace.name || `Series ${traceIndex + 1}`,
        x: x[index] ?? "--",
        y: y[index] ?? "--",
      });
    }
  });
  return rows;
}

export default function PlotlyChart({ figure, label, loading = false, language = "en", t }) {
  const translate = t || ((key, fallback) => fallback);
  if (loading && !figure) {
    return <div className="plotly-empty plotly-empty--loading" role="status"><span className="loading-bar" />{translate("plotly.loading", "Loading")} {label}...</div>;
  }
  if (!figure) {
    return <div className="plotly-empty" role="status">{label} {translate("plotly.unavailable", "is not available for this snapshot.")}</div>;
  }
  const localizedFigure = localizePlotlyFigure(figure, language);
  const figureTitle = typeof localizedFigure.layout?.title === "string"
    ? { text: localizedFigure.layout.title }
    : localizedFigure.layout?.title;
  const layout = {
    ...localizedFigure.layout,
    autosize: true,
    height: 620,
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    font: { ...(localizedFigure.layout?.font || {}), color: "#b5c0c7", family: "Inter, system-ui, sans-serif" },
    title: figureTitle ? { ...figureTitle, font: { ...(figureTitle.font || {}), color: "#d8e3e8", size: 13 } } : undefined,
    margin: { l: 58, r: 24, t: 48, b: 42, ...(localizedFigure.layout?.margin || {}) },
    xaxis: axisTheme(localizedFigure.layout?.xaxis),
    yaxis: axisTheme(localizedFigure.layout?.yaxis),
    legend: localizedFigure.layout?.legend ? { ...localizedFigure.layout.legend, font: { ...(localizedFigure.layout.legend.font || {}), color: "#9aaab4", size: 10 } } : undefined,
    shapes: localizedFigure.layout?.shapes?.map((shape) => ({ ...shape, line: shape.line ? { ...shape.line, color: recolor(shape.line.color) } : shape.line, fillcolor: recolor(shape.fillcolor) })),
    annotations: localizedFigure.layout?.annotations?.map((annotation) => ({ ...annotation, font: annotation.font ? { ...annotation.font, color: recolor(annotation.font.color) } : annotation.font })),
  };
  const rows = accessibleRows(localizedFigure);
  return <div className="plotly-chart" aria-label={label}>
    <div className="plotly-canvas"><Plot
      data={(localizedFigure.data || []).map(recolorTrace)}
      layout={layout}
      config={{ responsive: true, displaylogo: false, scrollZoom: true, doubleClick: "reset", modeBarButtonsToRemove: ["lasso2d", "select2d"] }}
      useResizeHandler
      style={{ width: "100%", height: "100%" }}
    /></div>
    {rows.length > 0 && <details className="plotly-data-details">
      <summary>{translate("plotly.openTable", "Open data table")}</summary>
      <div className="plotly-data-scroll"><table><caption>{label} {translate("plotly.values", "values")}</caption><thead><tr><th>{translate("plotly.series", "Series")}</th><th>X</th><th>Y</th></tr></thead><tbody>{rows.map((row, index) => <tr key={`${row.series}-${index}`}><td>{row.series}</td><td>{String(row.x)}</td><td>{String(row.y)}</td></tr>)}</tbody></table></div>
    </details>}
  </div>;
}
