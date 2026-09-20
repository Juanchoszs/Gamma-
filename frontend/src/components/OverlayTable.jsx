import { formatDateTime, formatMoney, formatPrice, formatCompact } from "../lib/format";

export default function OverlayTable({ overlay, t }) {
  const translate = t || ((key, fallback) => fallback);
  if (!overlay.bubbles.length) return <div className="empty-state">{translate("table.noFlow", "No flow matches the current filters.")}</div>;
  return (
    <div className="accessible-table-wrap">
      <table className="accessible-table">
        <caption>{translate("table.caption", "Options flow events plotted on the price chart")}</caption>
        <thead><tr><th>{translate("table.type", "Type")}</th><th>{translate("table.strike", "Strike")}</th><th>{translate("table.time", "Time")}</th><th>{translate("table.premium", "Premium")}</th><th>{translate("table.volume", "Volume")}</th><th>{translate("table.side", "Side")}</th></tr></thead>
        <tbody>{overlay.bubbles.map((bubble) => <tr key={bubble.id}><td className={bubble.option_type === "CALL" ? "text-call" : "text-put"}>{bubble.option_type}</td><td>{formatPrice(bubble.strike)}</td><td>{formatDateTime(bubble.timestamp)}</td><td>{formatMoney(bubble.premium)}</td><td>{formatCompact(bubble.volume)}</td><td>{bubble.side === "UNKNOWN" ? translate("common.unknown", "Unknown") : bubble.side}</td></tr>)}</tbody>
      </table>
    </div>
  );
}
