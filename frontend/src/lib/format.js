const number = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });

export function formatMoney(value) {
  const amount = value === null || value === undefined || value === "" ? NaN : Number(value);
  if (!Number.isFinite(amount)) return "--";
  const abs = Math.abs(amount);
  const sign = amount < 0 ? "-" : "";
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(1)}K`;
  return `${sign}$${abs.toFixed(0)}`;
}

export function formatPrice(value) {
  const amount = value === null || value === undefined || value === "" ? NaN : Number(value);
  return Number.isFinite(amount) ? number.format(amount) : "--";
}

export function formatPercent(value) {
  const amount = value === null || value === undefined || value === "" ? NaN : Number(value);
  return Number.isFinite(amount) ? `${amount >= 0 ? "+" : ""}${amount.toFixed(2)}%` : "--";
}

export function formatDateTime(value) {
  if (!value) return "--";
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? "--" : parsed.toLocaleString([], { dateStyle: "short", timeStyle: "medium" });
}

export function formatCompact(value) {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "--";
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(amount);
}

export function displayLabel(value) {
  return String(value || "--").replaceAll("_", " ");
}

const VALUE_LABEL_KEYS = {
  "LIVE": "value.live",
  "DATA LIVE": "value.dataLive",
  "DATA STALE": "value.dataStale",
  "STALE": "value.stale",
  "DELAYED": "value.delayed",
  "NEGATIVE GAMMA": "value.negativeGamma",
  "POSITIVE GAMMA": "value.positiveGamma",
  "NEUTRAL GAMMA": "value.neutralGamma",
  "GAMMA NEGATIVA": "value.negativeGamma",
  "GAMMA POSITIVA": "value.positiveGamma",
  "GAMMA NEUTRAL": "value.neutralGamma",
  "ABOVE MAJOR GAMMA": "value.aboveMajorGamma",
  "BELOW MAJOR GAMMA": "value.belowMajorGamma",
  "PUT HEAVY": "value.putHeavy",
  "CALL HEAVY": "value.callHeavy",
  "BALANCED": "value.balanced",
  "CALL WALL": "value.callWall",
  "PUT WALL": "value.putWall",
  "GAMMA FLIP": "value.gammaFlip",
  "LOW GAMMA": "value.lowGamma",
  "HIGH GAMMA": "value.highGamma",
  "VOLUME NODE": "value.volumeNode",
  "ABOVE LEVEL": "value.aboveLevel",
  "BELOW LEVEL": "value.belowLevel",
  "APPROACHING": "value.approaching",
  "TESTING": "value.testing",
  "ACTIVE": "value.active",
  "CLOSED": "value.closed",
  "OPEN": "value.open",
  "REGULAR": "value.regular",
  "OVERNIGHT": "value.overnight",
  "WAITING": "value.waiting",
  "CONDITIONAL": "value.conditional",
  "GEX ENGINE": "value.gexEngine",
  "SESSION PROFILE": "value.sessionProfile",
  "UNKNOWN": "value.unknown",
  "CONNECTING": "value.connecting",
};

export function translateLabel(value, t) {
  const label = displayLabel(value);
  const key = VALUE_LABEL_KEYS[label.toUpperCase()];
  return key && t ? t(key, label) : label;
}
