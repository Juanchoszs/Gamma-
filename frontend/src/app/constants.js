import {
  Activity,
  BarChart3,
  BookOpen,
  Gauge,
  Layers3,
  LayoutDashboard,
  LineChart,
  Map,
  Radio,
  Settings2,
  ShieldAlert,
  Sparkles,
  Target,
  Waves,
  Flame,
} from "lucide-react";

export const NAV_GROUPS = [
  {
    label: "Market",
    items: [
      ["overview", "Overview", LayoutDashboard],
      ["map", "Market Map", Map],
      ["heat", "Heatmaps", Flame],
      ["profile", "GEX & Gamma", BarChart3],
      ["chain", "Options Chain", Layers3],
      ["levels", "Levels", Target],
    ],
  },
  {
    label: "Flow",
    items: [
      ["scenarios", "Scenarios", Sparkles],
      ["positioning", "Positioning", Gauge],
      ["flow", "Options Flow", Waves],
      ["volatility", "Vanna & Charm", Activity],
    ],
  },
  {
    label: "Research",
    items: [
      ["report", "Market Report", BookOpen],
      ["history", "Level History", LineChart],
      ["session", "Session Profile", Radio],
    ],
  },
  {
    label: "System",
    items: [
      ["settings", "Settings", Settings2],
      ["diagnostics", "Diagnostics", ShieldAlert],
    ],
  },
];

export const LEVEL_COLORS = {
  CALL_WALL: "var(--call)",
  PUT_WALL: "var(--put)",
  GAMMA_FLIP: "var(--flip)",
  HIGH_GAMMA: "var(--positive)",
  LOW_GAMMA: "var(--violet)",
  GEX_WALL: "var(--info)",
  OI_NODE: "var(--info)",
  VOLUME_NODE: "var(--violet)",
};

export const EXPIRATION_OPTIONS = ["0DTE", "WEEKLY", "MONTHLY", "ALL"];

export const DEFAULT_LAYERS = {
  price: true,
  currentPrice: true,
  callWall: true,
  putWall: true,
  gammaFlip: true,
  flow: true,
};

export const CHART_COLORS = {
  background: "#0e151a",
  grid: "#1c2a33",
  border: "#30414c",
  text: "#d8e3e8",
  muted: "#8e9da7",
  bullish: "#8fbeb6",
  bearish: "#df8795",
  call: "#58b6c4",
  put: "#d98795",
  current: "#d8e3e8",
  flip: "#d8b65a",
};

export const LAYER_LABELS = {
  price: "Price",
  currentPrice: "Current price",
  callWall: "Call wall",
  putWall: "Put wall",
  gammaFlip: "Gamma flip",
  flow: "Flow",
};

export const CHARTS_BY_PAGE = {
  overview: ["overview-market-map", "gex-strike", "dex-strike", "flow", "gflow", "tape", "gex-history", "spot-zg", "smile"],
  map: ["market-map-chart", "unified-level-map"],
  heat: ["heatmap-intraday", "heatmap-bubbles", "heatmap-term", "heatmap-hist", "heatmap-overlay"],
  profile: ["profile", "profile-exp", "vex", "cex"],
  positioning: ["pos-dist-graph", "oi-change", "pos-hist-graph"],
  flow: ["flow", "gflow", "tape"],
  volatility: ["vol-surface", "iv-term-structure", "gex-by-expiry", "oi-by-expiry"],
  history: ["level-history-chart", "gex-history"],
  levels: ["unified-level-map"],
};

export const PROFILE_EXPIRATIONS = [
  ["ALL", "All"],
  ["0DTE", "0DTE"],
  ["WEEKLY", "Weekly"],
  ["MONTHLY", "Monthly"],
];

export const FLOW_SERIES = [
  ["calls", "Calls"],
  ["puts", "Puts"],
  ["net", "Net"],
];
