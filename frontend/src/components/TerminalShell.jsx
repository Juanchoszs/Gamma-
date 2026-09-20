import { useEffect } from "react";
import { ChevronDown, Menu, PanelLeft, RefreshCw, Search, Settings2 } from "lucide-react";
import { EXPIRATION_OPTIONS, NAV_GROUPS } from "../app/constants";
import { translateLabel, formatDateTime } from "../lib/format";

export function Sidebar({ page, collapsed, mobileOpen, onToggle, onNavigate, t }) {
  return (
    <aside className={`terminal-sidebar ${collapsed ? "is-collapsed" : ""} ${mobileOpen ? "is-mobile-open" : ""}`}>
      <div className="brand-row">
        <span className="brand-mark">G</span>
        {!collapsed && <span className="brand-copy"><strong>GAMMA</strong><small>MARKET INTELLIGENCE</small></span>}
        <button className="icon-button sidebar-toggle" onClick={onToggle} aria-label={collapsed ? "Expand navigation" : "Collapse navigation"} title={collapsed ? "Expand navigation" : "Collapse navigation"}>{collapsed ? <Menu size={16} /> : <PanelLeft size={16} />}</button>
      </div>
      <nav className="sidebar-nav" aria-label="Terminal navigation">
        {NAV_GROUPS.map((group) => <div className="nav-group" key={group.label}>
          {!collapsed && <span className="nav-group-label">{t(`nav.${group.label.toLowerCase()}`, group.label)}</span>}
          {group.items.map(([id, label, Icon]) => <button key={id} className={`nav-item ${page === id ? "is-active" : ""}`} onClick={() => onNavigate(id)} aria-current={page === id ? "page" : undefined} title={collapsed ? t(`nav.${id === "flow" ? "flowPage" : id}`, label) : undefined}><Icon size={16} strokeWidth={1.7} /><span>{!collapsed && t(`nav.${id === "flow" ? "flowPage" : id}`, label)}</span></button>)}
        </div>)}
      </nav>
      {!collapsed && <div className="sidebar-footer"><span className="status-dot status-dot--live" />{t("shell.engineConnected")}</div>}
    </aside>
  );
}

export function Topbar({ symbol, symbols, bucket, language, onLanguageChange, t, onSymbolChange, onBucketChange, status, isFetching, onRefresh, onSettings, onMenu }) {
  return <header className="terminal-topbar">
    <div className="topbar-leading"><button className="icon-button mobile-menu" onClick={onMenu} aria-label={t("shell.openNavigation", "Open navigation")}><Menu size={17} /></button><span className="topbar-kicker">{t("shell.workspace")}</span><span className="topbar-divider" /><label className="symbol-picker"><Search size={14} /><span className="sr-only">{t("common.symbol", "Symbol")}</span><select value={symbol} onChange={(event) => onSymbolChange(event.target.value)} aria-label={t("common.symbol", "Symbol")}>{(symbols.length ? symbols : [symbol]).map((item) => <option key={item}>{item}</option>)}</select><ChevronDown size={13} /></label></div>
    <div className="expiration-control" role="group" aria-label="Expiration bucket">{EXPIRATION_OPTIONS.map((item) => <button key={item} className={bucket === item ? "is-active" : ""} onClick={() => onBucketChange(item)} aria-pressed={bucket === item}>{item}</button>)}</div>
    <div className="topbar-actions"><div className="language-switch" role="group" aria-label={t("common.language", "Language")}><button className={language === "en" ? "is-active" : ""} onClick={() => onLanguageChange("en")} aria-pressed={language === "en"}>EN</button><button className={language === "es" ? "is-active" : ""} onClick={() => onLanguageChange("es")} aria-pressed={language === "es"}>ES</button></div><span className={`connection-status connection-status--${status === "error" ? "error" : status === "pending" ? "loading" : "live"}`}><span className="status-dot" />{status === "error" ? t("shell.offline") : isFetching ? t("shell.syncing") : t("shell.live")}</span><button className="icon-button" onClick={onRefresh} aria-label={t("shell.refresh")} title={t("shell.refresh")}><RefreshCw size={15} className={isFetching ? "spin" : ""} /></button><button className="icon-button" onClick={onSettings} aria-label={t("shell.settings")} title={t("shell.settings")}><Settings2 size={15} /></button></div>
  </header>;
}

export function WorkspaceHeader({ data, symbol, onControls, t }) {
  const state = data.state || {};
  return <div className="workspace-header-pro"><div><span className="eyebrow"><span className="status-dot status-dot--live" /> {t("shell.marketMonitor")} <i>/</i> {data.overlay?.as_of ? formatDateTime(data.overlay.as_of) : t("shell.liveSession", "LIVE SESSION")}</span><h1>{symbol} {t("shell.decisionWorkspace")}</h1><p>{t("shell.workspaceSummary")}</p></div><div className="workspace-header-actions"><span className="regime-badge">{translateLabel(state.session || "CONNECTING", t)}</span><button className="button-secondary" onClick={onControls}>{t("shell.controls")}</button></div></div>;
}

export function StatusBar({ data, symbol, t }) {
  const status = data.status === "error" ? t("shell.offline") : data.status === "pending" ? t("shell.loading") : t("shell.ready");
  return <footer className="terminal-statusbar"><span><span className={`status-dot ${data.status === "error" ? "status-dot--error" : "status-dot--live"}`} /> {t("shell.engineStatus")} {status}</span><span>{symbol}</span><span className="statusbar-right">{data.overlay?.source || "Python domain services"} · {data.overlay?.as_of ? formatDateTime(data.overlay.as_of) : "waiting"}</span></footer>;
}

export function TerminalShell({ page, collapsed, mobileOpen, language, t, onToggle, onNavigate, children }) {
  useEffect(() => {
    const handleKey = (event) => {
      if (event.key === "Escape") onToggle(false);
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onToggle]);
  return <div className={`terminal-frame ${collapsed ? "is-collapsed" : ""}`}><div className={`mobile-backdrop ${mobileOpen ? "is-open" : ""}`} onClick={() => onToggle(false)} aria-hidden="true" /><Sidebar page={page} collapsed={collapsed} mobileOpen={mobileOpen} onToggle={() => onToggle()} onNavigate={onNavigate} t={t} /><div className="terminal-body">{children}</div></div>;
}
