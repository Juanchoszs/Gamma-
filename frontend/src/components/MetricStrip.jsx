import { formatMoney, formatPercent, formatPrice, translateLabel } from "../lib/format";

export default function MetricStrip({ data, t }) {
  const translate = t || ((key, fallback) => fallback);
  const state = data.state || {};
  const summary = data.summary || {};
  const levels = data.map?.levels || data.overlay?.levels || [];
  const callWall = levels.find((level) => level.type === "CALL_WALL" || level.side === "C");
  const putWall = levels.find((level) => level.type === "PUT_WALL" || level.side === "P");
  const flip = levels.find((level) => level.type === "GAMMA_FLIP" || level.color_key === "flip") || data.overlay?.levels.find((level) => level.color_key === "flip");
  const cards = [
    [translate("metric.spot", "Spot"), formatPrice(data.overlay?.currentPrice || state.spot), "spot", state.price_change_percent !== undefined ? formatPercent(state.price_change_percent) : translate("common.live", "LIVE")],
    [translate("metric.netGex", "Net GEX"), formatMoney(state.net_gex ?? summary.net_gex), Number(state.net_gex) >= 0 ? "positive" : "negative", translateLabel(state.gamma_regime, translate)],
    [translate("metric.gammaFlip", "Gamma Flip"), formatPrice(flip?.price || state.zero_gamma), "flip", translate("metric.dealerPivot", "dealer pivot")],
    [translate("metric.callWall", "Call Wall"), formatPrice(callWall?.price), "call", translate("metric.resistance", "resistance")],
    [translate("metric.putWall", "Put Wall"), formatPrice(putWall?.price), "put", translate("metric.support", "support")],
    [translate("metric.vix", "VIX"), data.vix?.available ? formatPrice(data.vix.vix) : "--", "iv", data.vix?.grade?.label || data.vix?.grade || translate("metric.volatility", "volatility")],
  ];
  return <div className="metric-strip-pro">{cards.map(([label, value, tone, meta]) => <div className={`metric-card-pro metric-card-pro--${tone}`} key={label}><span>{label}</span><strong>{value}</strong><small>{meta}</small></div>)}</div>;
}
