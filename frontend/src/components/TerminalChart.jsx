import { useEffect, useMemo, useRef, useState } from "react";
import { CandlestickSeries, LineSeries, createChart } from "lightweight-charts";
import { formatCompact, formatDateTime, formatMoney, formatPrice, translateLabel } from "../lib/format";
import { CHART_COLORS, LAYER_LABELS } from "../app/constants";

function chartTime(value) {
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? Math.floor(timestamp / 1000) : null;
}

export function cleanPrices(rows = []) {
  const byTime = new Map();
  rows.forEach((row) => {
      const time = chartTime(row.timestamp);
      const close = Number(row.close);
      if (time === null || !Number.isFinite(close)) return;
      const open = Number(row.open);
      const high = Number(row.high);
      const low = Number(row.low);
      byTime.set(time, {
        time,
        open: Number.isFinite(open) ? open : close,
        high: Number.isFinite(high) ? high : close,
        low: Number.isFinite(low) ? low : close,
        close,
      });
    });
  return [...byTime.values()].sort((a, b) => a.time - b.time);
}

function levelColor(level) {
  if (level.color_key === "call_wall" || level.side === "C") return "var(--call)";
  if (level.color_key === "put_wall" || level.side === "P") return "var(--put)";
  return "var(--flip)";
}

function BubbleTooltip({ bubble, position, t }) {
  if (!bubble || !position) return null;
  const translate = t || ((key, fallback) => fallback);
  const rows = [
    [translate("tooltip.type", "Type"), bubble.option_type],
    [translate("tooltip.strike", "Strike"), formatPrice(bubble.strike)],
    [translate("tooltip.time", "Time"), formatDateTime(bubble.timestamp)],
    [translate("tooltip.premium", "Premium"), formatMoney(bubble.premium)],
    [translate("tooltip.volume", "Volume"), formatCompact(bubble.volume)],
    [translate("tooltip.openInterest", "Open interest"), formatCompact(bubble.open_interest)],
    ["IV", Number.isFinite(Number(bubble.implied_volatility)) ? `${(Number(bubble.implied_volatility) * 100).toFixed(1)}%` : null],
    ["Delta", Number.isFinite(Number(bubble.delta)) ? Number(bubble.delta).toFixed(3) : null],
    ["Gamma", Number.isFinite(Number(bubble.gamma)) ? Number(bubble.gamma).toFixed(5) : null],
    [translate("tooltip.side", "Side"), bubble.side === "UNKNOWN" ? null : bubble.side],
  ].filter(([, value]) => value !== null && value !== "--");
  return (
    <div className="chart-tooltip" style={{ left: `${Math.min(position.x + 12, 66)}%`, top: `${Math.max(12, position.y - 12)}px` }} role="status">
      <strong>{bubble.option_type} FLOW</strong>
      <dl>{rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
    </div>
  );
}

export default function TerminalChart({ overlay, priceHistory, layers, onToggleLayer, t }) {
  const translate = t || ((key, fallback) => fallback);
  const chartRef = useRef(null);
  const hostRef = useRef(null);
  const [selectedBubble, setSelectedBubble] = useState(null);
  const [bubblePositions, setBubblePositions] = useState({});
  const [chartReady, setChartReady] = useState(false);
  const [, setOverlayTick] = useState(0);
  const prices = useMemo(() => cleanPrices(overlay.priceSeries), [overlay.priceSeries]);
  const levels = useMemo(() => overlay.levels.filter((level) => Number.isFinite(Number(level.price))), [overlay.levels]);
  const bubbles = useMemo(() => overlay.bubbles.filter((bubble) => Number.isFinite(Number(bubble.strike)) && chartTime(bubble.timestamp)), [overlay.bubbles]);

  useEffect(() => {
    if (!hostRef.current || !prices.length) return undefined;
    const host = hostRef.current;
    const chart = createChart(host, {
      width: host.clientWidth,
      height: 520,
      layout: { background: { color: "transparent" }, textColor: CHART_COLORS.muted, fontFamily: "JetBrains Mono, monospace", fontSize: 11 },
      grid: { vertLines: { color: CHART_COLORS.grid }, horzLines: { color: CHART_COLORS.grid } },
      rightPriceScale: { borderColor: CHART_COLORS.border, scaleMargins: { top: 0.08, bottom: 0.12 } },
      timeScale: { borderColor: CHART_COLORS.border, timeVisible: true, secondsVisible: false, rightOffset: 4 },
      crosshair: { mode: 1, vertLine: { color: "#607684", width: 1, style: 3 }, horzLine: { color: "#607684", width: 1, style: 3 } },
    });
    const useCandles = prices.some((row) => row.open !== row.close || row.high !== row.close || row.low !== row.close);
    const series = useCandles
      ? chart.addSeries(CandlestickSeries, { upColor: CHART_COLORS.bullish, downColor: CHART_COLORS.bearish, borderVisible: false, wickUpColor: CHART_COLORS.bullish, wickDownColor: CHART_COLORS.bearish })
      : chart.addSeries(LineSeries, { color: CHART_COLORS.text, lineWidth: 2, crosshairMarkerRadius: 4 });
    series.setData(useCandles ? prices : prices.map(({ time, close }) => ({ time, value: close })));
    const price = Number(overlay.currentPrice);
    const priceLine = Number.isFinite(price) ? series.createPriceLine({
      price,
      color: CHART_COLORS.text,
      lineWidth: 2,
      lineStyle: 2,
      lineVisible: layers.currentPrice,
      axisLabelVisible: true,
      title: translate("chart.currentPrice", "Current price"),
    }) : null;
    const allPrices = [...prices.map((row) => row.close), ...levels.map((level) => Number(level.price)), Number(overlay.currentPrice)].filter(Number.isFinite);
    if (allPrices.length > prices.length && prices.length > 1 && prices[0].time < prices[prices.length - 1].time) {
      const scaleSeries = chart.addSeries(LineSeries, { color: "rgba(0,0,0,0)", lineWidth: 1, lastValueVisible: false, priceLineVisible: false });
      const first = prices[0].time;
      const last = prices[prices.length - 1].time;
      scaleSeries.setData([{ time: first, value: Math.min(...allPrices) }, { time: last, value: Math.max(...allPrices) }]);
    }
    chart.timeScale().fitContent();
    chartRef.current = { chart, series, priceLine };
    setChartReady(true);
    const resize = () => chart.applyOptions({ width: host.clientWidth, height: Math.max(360, Math.min(560, host.clientHeight || 520)) });
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
      setChartReady(false);
    };
  }, [prices, levels, overlay.currentPrice]);

  useEffect(() => {
    chartRef.current?.series?.applyOptions({ visible: layers.price });
  }, [layers.price]);

  useEffect(() => {
    const state = chartRef.current;
    if (!state || !hostRef.current) return undefined;
    let frame = 0;
    const position = () => {
      const { chart, series } = state;
      const next = {};
      bubbles.forEach((bubble) => {
        const x = chart.timeScale().timeToCoordinate(chartTime(bubble.timestamp));
        const y = series.priceToCoordinate(Number(bubble.strike));
        if (x !== null && y !== null) next[bubble.id] = { x, y };
      });
      setBubblePositions(next);
      setOverlayTick((value) => value + 1);
    };
    const schedule = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(position);
    };
    schedule();
    window.addEventListener("resize", schedule);
    state.chart.timeScale().subscribeVisibleTimeRangeChange(schedule);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", schedule);
      state.chart.timeScale().unsubscribeVisibleTimeRangeChange(schedule);
    };
  }, [bubbles, levels, overlay.currentPrice]);

  useEffect(() => {
    chartRef.current?.priceLine?.applyOptions({
      lineVisible: layers.currentPrice,
      axisLabelVisible: false,
    });
  }, [layers.currentPrice]);

  const selectedPosition = selectedBubble ? bubblePositions[selectedBubble.id] : null;
  return (
    <div className="chart-module" data-chart-id="options-flow-overlay" aria-label={translate("chart.optionsFlow", "Options flow overlay")}>
      <div className="chart-toolbar chart-toolbar--pro">
        <div className="chart-legend"><span><i className="legend-line legend-line--price" />{translate("chart.price", "Price")}</span><span><i className="legend-dot legend-dot--call" />{translate("chart.callFlow", "Call flow")}</span><span><i className="legend-dot legend-dot--put" />{translate("chart.putFlow", "Put flow")}</span><span><i className="legend-line legend-line--flip" />{translate("chart.gammaFlip", "Gamma flip")}</span></div>
        <div className="chart-toolbar-actions">
          {Object.entries(layers).map(([key, enabled]) => <button key={key} className={`layer-toggle ${enabled ? "is-active" : ""}`} onClick={() => onToggleLayer(key)} aria-pressed={enabled}>{translate(`chart.${key}`, LAYER_LABELS[key] || key)}</button>)}
          <button className="chart-reset" onClick={() => chartRef.current?.chart.timeScale().fitContent()} aria-label={translate("chart.resetView", "Reset chart view")}>{translate("chart.reset", "Reset")}</button>
        </div>
      </div>
      <div className="chart-canvas" ref={hostRef}>
        {!prices.length && <div className="chart-placeholder"><span className="status-dot" /><strong>{translate("chart.waiting", "Waiting for price bars")}</strong><small>{translate("chart.noHistory", "Historical OHLC data is not available for this symbol yet.")}</small></div>}
        {chartReady && levels.map((level) => {
          const position = chartRef.current?.series?.priceToCoordinate(Number(level.price));
          const visible = (level.side === "C" && layers.callWall) || (level.side === "P" && layers.putWall) || (level.color_key === "flip" && layers.gammaFlip);
          if (!visible || position === null || position === undefined) return null;
          return <div key={level.id} className="chart-level-overlay" style={{ top: `${position}px`, "--level-color": levelColor(level) }}><span>{translateLabel(level.name, translate)}</span><b>{formatPrice(level.price)}</b></div>;
        })}
        {layers.flow && bubbles.map((bubble) => {
          const position = bubblePositions[bubble.id];
          if (!position) return null;
          const call = bubble.option_type === "CALL";
          return <button key={bubble.id} className={`flow-bubble flow-bubble--${call ? "call" : "put"}`} style={{ left: `${position.x}px`, top: `${position.y}px`, width: `${bubble.size}px`, height: `${bubble.size}px` }} onClick={() => setSelectedBubble((current) => current?.id === bubble.id ? null : bubble)} onFocus={() => setSelectedBubble(bubble)} title={`${bubble.option_type} ${formatPrice(bubble.strike)} ${formatMoney(bubble.premium)}`} aria-label={`${bubble.option_type} flow at strike ${formatPrice(bubble.strike)}, premium ${formatMoney(bubble.premium)}`} />;
        })}
        <BubbleTooltip bubble={selectedBubble} position={selectedPosition ? { ...selectedPosition, x: (selectedPosition.x / Math.max(hostRef.current?.clientWidth || 1, 1)) * 100 } : null} t={t} />
      </div>
      <div className="chart-footer"><span>{overlay.priceSeries.length} {translate("common.bars", "bars")}</span>{priceHistory && <span>{priceHistory.available_sessions ?? 0}/{priceHistory.requested_sessions ?? 0} {translate("chart.sessionsAvailable", "real sessions")}</span>}<span>{overlay.bubbles.length} {translate("chart.flowEvents", "aggregated flow events")}</span><span>{overlay.levels.length} {translate("common.levels", "GEX levels")}</span><span className="chart-footer-source">{priceHistory?.source || overlay.source || translate("chart.marketEngine", "market engine")} · {translateLabel(overlay.freshness || "UNKNOWN", translate)}</span></div>
    </div>
  );
}
