# CSS Audit — GEX Dashboard

**Date:** 2026-09-12
**Source File:** `gex/assets/style.css` (1684 lines)
**Modular Files Present:** 00-reset.css, 01-tokens.css, 02-base.css, 03-layout.css, 04-navigation.css, 05-controls.css
**Modular Files Missing:** 06-components.css, 07-data-display.css, 08-analytics.css, 09-heatmap.css, 10-positioning.css, 11-modals.css, 12-states.css, 13-responsive.css, 99-utilities.css

---

## 1. Structural Issues

### Duplicate `:root` Blocks (2 found)
- **Line 7-29:** First `:root` — Neon system (cyan/magenta glows, glassmorphism)
- **Line 35-53:** Second `:root` — "Design system 2.0" — attempts to override first

### Redefinitions of Same Selectors
| Selector | Occurrences | Lines |
|----------|-------------|-------|
| `.topbar` | 2 | 55-59, 187-195 |
| `.workspace-hero` | 2 | 74-77, 238-268 |
| `.toolbar` | 2 | 64, 272-278 |
| `.tabbar` | 2 | 81, 582-589 |
| `.tab-item` | 3 | 82-84, 594-620 |
| `.stat` | 2 | 91-96, 382-429 |
| `.row` | 2 | 97-98, 635-636 |
| `.daybar` | 2 | 99, 673-678 |
| `.hint` | 2 | 100, 626-633 |
| `.cards` | 2 | 90, 380 |
| `.brand` | 2 | 63, 205-213 |
| `.brand-mark` | 2 | 62, 215-226 |

### Override Pile Pattern
Multiple rules for same selector accumulating instead of consolidating.

---

## 2. Neon / Decorative Aesthetic (To Eliminate)

### Hardcoded Neon Colors
- `#00f0ff` (cyan neon) — 47 occurrences
- `#ff2e74` (magenta neon) — 23 occurrences
- `#fbbf24` (gold/amber) — 12 occurrences
- `#10b981` (emerald) — 8 occurrences

### Glow Effects
- `--glow-cyan: 0 0 14px rgba(0, 240, 255, 0.35)` — line 23
- `--glow-magenta: 0 0 14px rgba(255, 46, 116, 0.35)` — line 24
- `--glow-gold: 0 0 14px rgba(251, 191, 36, 0.35)` — line 25
- `text-shadow: 0 0 10px var(--ok)` — line 252 (live-pulse)
- `box-shadow: 0 0 10px rgba(0, 240, 255, 0.25)` — line 339 (seg checked)
- `box-shadow: inset 0 0 0 2px var(--surface), 0 0 8px rgba(0, 240, 255, 0.5)` — line 375 (check checked)
- `box-shadow: 0 0 8px rgba(0, 240, 255, 0.5)` — line 453-454 (pc-gauge)
- Multiple `box-shadow` with neon colors throughout

### Decorative Gradients
- `linear-gradient(120deg, #162235 0%, #121a27 64%, #142232 100%)` — line 76
- `radial-gradient(circle at 85% 15%, rgba(0,240,255,.12), transparent 32%)` — line 244
- `linear-gradient(135deg, var(--pos), #0284c7)` — line 219
- `linear-gradient(135deg, #00c6ff, #0072ff)` — line 1238 (tt-btn-primary)
- Heatmap colorscales using neon cyan/magenta — lines 759-768, 1036-1042

### Glassmorphism / Blur
- `backdrop-filter: blur(18px)` — line 58
- `backdrop-filter: blur(16px)` — line 192
- `backdrop-filter: blur(4px)` — line 148
- `backdrop-filter: blur(6px)` — line 914
- `backdrop-filter: blur(8px)` — line 1062
- `backdrop-filter: blur(12px)` — line 1578

---

## 3. Component Systems (Need Unification)

### Segmented Controls (5 variants)
1. `.seg` — lines 297-340
2. `.check` — lines 343-376
3. `.symbol-seg` — lines 1476-1506
4. `.pos-seg` — lines 1543-1564
5. `.heat-seg` — lines 1585-1618
6. `.analytics-seg` — line 1308

### Table Patterns (3 variants)
1. `.tape-table` — lines 786-813
2. `.whale-table` — lines 1325-1399
3. `.levels-table` — lines 1402-1446

### Modal Families (3 independent)
1. `.cfd-modal-backdrop` / `.cfd-modal-card` — lines 909-1029
2. `.tt-modal-backdrop` / `.tt-modal-card` — lines 1057-1287
3. `.native-overlay` / `.native-overlay-card` — lines 143-183

### Media Queries (Duplicated)
- `@media (max-width: 760px)` — line 104
- `@media (max-width: 720px)` — lines 263, 773
- `@media (max-width: 900px)` — line 1675

---

## 4. Hardcoded Colors (Sample)

| Color | Type | Locations |
|-------|------|-----------|
| `#0f1422` | Surface | 1, 52, 386 |
| `#070a11` | Page/BG | 11, 53, 119, 910 |
| `#161e32` | Surface-2 | 9, 382 |
| `#1a2234` | Line | 15, 193, 585 |
| `#26334d` | Line-hover | 16, 72 |
| `#161f30` | Grid | 17, 916 |
| `#090d16` | Dark surface | 257, 299, 344, 818 |
| `#141b2c` | Active surface | 335, 1502, 1560, 1613 |
| `#1d2b3e` | Hover surface | 101, 102 |
| `#293b53` | Hover surface | 102 |
| `#0d121f` | Chip BG | 503 |
| `#080c16` | Input BG | 1180, 1217 |

---

## 5. Emojis Found (36+ total)

### i18n.py — 30 emojis across 3 languages (es, fr, en)
- Heatmap sub-tabs: 🔥 🫧 🗓️ 🏛️ 📊 (5 × 3 = 15)
- Positioning sub-tabs: 📊 📈 🏛️ (3 × 3 = 9)
- Buttons: 🔄 💾 🗑 ⚡ (4 × 3 = 12, but some shared)
- Analytics: 🐋 📊 📅 📋 (4 in EN only)

### main.py (dashboard) — 10 emojis
- Line 3343: 🔑
- Heatmap tabs: 🔥 🫧 🗓️ 🏛️ 📊 (5)
- Positioning tabs: 📊 📈 🏛️ (3)
- Analytics tabs: 📊 🐋 📅 📋 (4)

### faq.html — 3 emojis
- 🔰 (3 occurrences, one per language)

### digest.py — 7 emojis
- Lines 56-60: 😴 🟢 🟡 🟠 🔴 🚨
- Line 413: 🌙

---

## 6. Animations (Decorative — To Remove/Reduce)

| Animation | Purpose | Lines |
|-----------|---------|-------|
| `page-enter` | Page transition | 85-86, 389 |
| `pulse` (live-pulse) | Live indicator glow | 252, 262 |
| `cfdFadeIn` | Modal entry | 935-938 |
| `ttModalIn` | Modal entry | 1084-1087 |
| `whale-fade-in` | Row entry | 1390-1399 |
| `analytics-pane-in` | Pane transition | 1462-1471 |

---

## 7. `!important` Usage (Needs Audit)

- `.tab-item` — 7 `!important` declarations (lines 100-106, 112-123) — Required for Dash dcc.Tab inline style override
- `.seg label:has(input:checked)` — 1 (line 334)
- `.check label:has(input:checked)` — 1 (line 371)

---

## 8. Python/Dash Contracts (Must Preserve)

### Component Classes (referenced in Python)
From `gex/presentation/dashboard/main.py`:
- `app-shell`, `topbar`, `topbar-row`, `topbar-actions`, `brand`, `brand-mark`, `brand-sub`
- `workspace-hero`, `workspace-head`, `workspace-copy`, `workspace-status`, `workspace-summary`
- `symbol-picker`, `toolbar`, `ctl`, `ctl-label`, `seg`, `check`, `tabbar`, `tab-item`
- `page`, `page-pane`, `section-head`, `section-kicker`, `section-note`
- `cards`, `stat`, `stat-label`, `stat-value`, `stat-sub`
- `row`, `primary-overlay-chart`, `graph-card`, `daybar`, `hint`, `footer`
- `btn`, `linkbtn`, `cfd-btn`, `cfd-control-group`, `cfd-input`
- `native-banner`, `native-overlay`, `native-overlay-card`
- `regime-banner`, `regime-label`, `regime-text`, `regime-disclaimer`
- `chips`, `chip`, `chips-prefix`, `levels-row`, `tv-copy`
- `rt-badge`, `rt-dot`, `rt-connected`, `rt-degraded`, `rt-disconnected`
- `dash-tabs-container`, `tape-table`, `tape-td`, `tape-mono`, `tape-num`
- `cfd-modal-backdrop`, `cfd-modal-card`, `cfd-modal-header`, `cfd-modal-desc`
- `cfd-calc-row`, `cfd-calc-label`, `cfd-calc-static-val`, `cfd-calc-field`, `cfd-calc-result`, `cfd-calc-result-val`, `cfd-modal-actions`
- `btn-tt-api`, `tt-modal-backdrop`, `tt-modal-card`, `tt-modal-header`, `tt-modal-title`, `tt-modal-desc`, `tt-status-banner`, `tt-status-dot`, `tt-input-group`, `tt-label`, `tt-input`, `tt-guide-box`, `tt-guide-title`, `tt-guide-code`, `tt-modal-actions`, `tt-btn-primary`, `tt-btn-secondary`, `tt-btn-danger`, `tt-msg-alert`
- `analytics-bar`, `analytics-seg`, `analytics-empty`, `whale-table`, `whale-th`, `whale-td`, `whale-mono`, `whale-num`, `whale-row`, `whale-large`, `whale-mega`, `levels-table`, `lvl-th`, `lvl-td`, `lvl-mono`, `lvl-num`, `lvl-row`, `heat-bar`, `heat-seg`, `heat-cards`, `heat-control-group`, `pos-cards`, `pos-bar`, `pos-seg`
- `scale-note`

### Callback IDs (referenced in Python)
- `symbol-selector`, `unit-selector`, `bucket-selector`, `majors-only`, `day-selector`
- `heat-subtabs`, `heat-metric`, `heat-levels`, `heat-window`, `heat-unit`, `heat-bubble-min`, `heat-bubble-limit`
- `analytics-subtabs`, `pos-subtabs`, `pos-window`
- `cfd-offset-input`, `cfd-calc-btn`, `cfd-auto-btn`, `cfd-reset-btn`, `cfd-modal-yahoo-btn`, `cfd-modal-apply-btn`, `cfd-modal-close-btn`
- `tt-modal-btn`, `tt-client-id`, `tt-client-secret`, `tt-refresh-token`, `tt-save-connect-btn`, `tt-save-btn`, `tt-disconnect-btn`, `tt-close-btn`
- `tape-size`, `tape-show-combos`

---

## 9. Plotly Chart Internals (Must NOT Touch)

All chart generation in `gex/presentation/dashboard/main.py`:
- `C` color palette (lines 51-71) — Plotly-internal, separate from CSS chrome
- `base_layout()`, `GRAPH_CONFIG`, `time_range_selector()`, `intraday_range_selector()`
- `exposure_fig()`, `heatmap_intraday_fig()`, `heatmap_term_fig()`, `heatmap_bubbles_fig()`, `heatmap_hist_fig()`, `heatmap_overlay_fig()`
- `whale_fig()`, `gex_expiry_fig()`, `oi_expiry_fig()`, `levels_table()`
- `vol_surface_fig()`, `vol_term_fig()`, `skew_fig()`, `vex_fig()`, `cex_fig()`
- `pos_dist_fig()`, `pos_delta_fig()`, `pos_hist_fig()`

---

## 10. Risk Assessment

### HIGH RISK (Do Not Modify)
- Plotly chart color palette `C` and all figure generation
- Callback IDs and component IDs
- Business logic, calculations, providers, CBOE ingestion, storage, scheduler

### MEDIUM RISK (Modify with Caution)
- Dash inline styles on `dcc.Tab` (requires `!important` in CSS)
- `.Select-control` and dropdown internals (React Select)
- Modal animations (if tied to UX expectations)

### LOW RISK (Safe to Refactor)
- All application chrome CSS (layout, navigation, controls, components, tables)
- Token definitions
- Spacing, typography, radii, shadows scales
- Emoji removal from text labels
- Decorative animation removal

---

## 11. Recommended Migration Order

1. **Create missing modular files** (06-13, 99) with new architecture
2. **Migrate tokens** — Already done in 01-tokens.css (verify aliases work)
3. **Migrate base/reset/layout/navigation/controls** — Already done in 00-05
4. **Create 06-components.css** — Consolidate .stat, .card, .chip, .badge, .section-head, .divider, .empty-state
5. **Create 07-data-display.css** — Data typography, numeric formatting, semantic colors
6. **Create 08-analytics.css** — Unify analytics, whale, levels, volume, expiry
7. **Create 09-heatmap.css** — Heatmap controls, remove decorative effects
8. **Create 10-positioning.css** — Reuse primitives from 05, 06
9. **Create 11-modals.css** — Unify 3 modal families
10. **Create 12-states.css** — Real-time/data quality states
11. **Create 13-responsive.css** — Consolidate all media queries
12. **Create 99-utilities.css** — focus-visible, reduced-motion, helpers
13. **Remove style.css** or make it a pure @import entrypoint
14. **Remove emojis** from Python/i18n
15. **Validate** at each step