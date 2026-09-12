# GEX CSS Modular Refactor + Visual Upgrade — Task Tracker

## Phase 1: Architecture & Modularization (RESTRUCTURING)

### CSS Modules Creation
- [x] 00-reset.css — Minimal reset (DONE)
- [x] 01-tokens.css — Single :root with all tokens + backward-compatible aliases (DONE)
- [x] 02-base.css — Base element styles (DONE)
- [x] 03-layout.css — App shell, page structure, grid (DONE)
- [x] 04-navigation.css — Topbar, brand, toolbar, tabs (DONE)
- [x] 05-controls.css — Buttons, dropdowns, segmented controls, checkboxes (DONE)
- [ ] 06-components.css — Panels, stats, badges, chips, section headers, dividers, actions, status, empty states
- [ ] 07-data-display.css — Price, GEX, DEX, volume, OI, IV, delta, timestamps, status, metadata
- [ ] 08-analytics.css — Analytics, whale tracker, levels, volume, expiry unified
- [ ] 09-heatmap.css — Heatmap controls, cards, chart containers
- [ ] 10-positioning.css — Positioning selector, metric cards, controls, chart, panes
- [ ] 11-modals.css — Unified modal primitive (backdrop, container, header, body, status, fields, actions)
- [ ] 12-states.css — Interactive states (hover, active, focus, selected, disabled, loading, error), real-time/data quality states
- [ ] 13-responsive.css — Consolidated breakpoints (1440, 1280, 1024, 768, 480)
- [ ] 99-utilities.css — Focus-visible, reduced-motion, helpers

### Legacy Cleanup
- [ ] Remove duplicate :root from style.css (keep only in 01-tokens.css)
- [ ] Remove all neon colors (#00f0ff, #ff2e74) from style.css
- [ ] Remove all text-shadow, glow, decorative gradients from style.css
- [ ] Remove glassmorphism (backdrop-filter blur as decoration)
- [ ] Remove all !important where specificity can be fixed properly
- [ ] Migrate remaining rules from style.css to appropriate modules
- [ ] Verify style.css is only an entrypoint (@import chain)

## Phase 2: Emoji Purge (ZERO TOLERANCE)

### i18n.py — Remove all emojis from 3 language packs (es, fr, en)
- [ ] heat_sub_intraday (🔥)
- [ ] heat_sub_bubbles (🫧)
- [ ] heat_sub_term (🗓️)
- [ ] heat_sub_hist (🏛️)
- [ ] heat_sub_overlay (📊)
- [ ] pos_sub_dist (📊)
- [ ] pos_sub_delta (📈)
- [ ] pos_sub_hist (🏛️)
- [ ] cfd_calc_yahoo (🔄)
- [ ] tt_btn_save (💾)
- [ ] tt_btn_disconnect (🗑)
- [ ] tt_configure_cta (⚡)
- [ ] tt_modal_btn (⚡)
- [ ] tt_step_1 (⚡)
- [ ] tt_btn_save_connect (⚡)

### main.py — Remove hardcoded emojis
- [ ] Line 3343: 🔑 in tt-modal-open-btn
- [ ] Lines 3523-3527: Heatmap sub-tab labels (5 emojis)
- [ ] Lines 3615-3617: Pos sub-tab labels (3 emojis)
- [ ] Lines 3656-3659: Analytics sub-tab labels (4 emojis)
- [ ] Line 3718: 🔄 in cfd-modal-yahoo-btn
- [ ] Line 3751: ⚡ in tt-modal-title
- [ ] Line 3826: 🗑 in tt-modal-disconnect-btn
- [ ] Line 3830: 💾 in tt-modal-save-btn

### digest.py — Remove emojis
- [ ] Lines 56-61: VIX regime emojis (😴, 🟢, 🟡, 🟠, 🔴, 🚨)
- [ ] Line 413-415: 🌙

## Phase 3: Visual Upgrade (INSTITUTIONAL TERMINAL)

### Neon Purge (Complete)
- [ ] Replace #00f0ff with --color-info / --market-call
- [ ] Replace #ff2e74 with --color-negative / --market-put
- [ ] Replace all glow variables with `none`
- [ ] Remove all text-shadow decorativo
- [ ] Remove all box-shadow luminoso
- [ ] Remove decorative gradients (keep only functional color stops)
- [ ] Remove backdrop-filter blur used only as decoration

### Spacing Normalization
- [ ] Ensure only --space-1 through --space-9 used
- [ ] Remove arbitrary px values (11px, 13px, 17px, etc.)

### Typography Normalization
- [ ] --font-ui for UI, --font-data for data (tabular-nums)
- [ ] Consistent scale: --text-xs through --text-3xl

### Radii Normalization
- [ ] Only --radius-sm, --radius-md, --radius-lg

### Shadows Normalization
- [ ] Only --shadow-sm, --shadow-md, --shadow-lg (depth, not illumination)

### Controls Unification
- [ ] Single segmented control base (.seg, .seg-btn)
- [ ] Single checkbox base (.check, .check-label)
- [ ] Single button base (.btn variants)
- [ ] Single dropdown/select base

### Tables Unification
- [ ] .data-table, .data-table__header, .data-table__row, .data-table__cell, .data-table__numeric, .data-table__muted
- [ ] Apply to Tape, Whale Tracker, GEX Levels

### Modals Unification
- [ ] Single .modal primitive with variants
- [ ] Migrate CFD modal, Tastytrade modal, native overlay

### States Unification
- [ ] LIVE/RECENT/STALE/MISSING/INVALID/DEGRADED/DISCONNECTED
- [ ] Each with text + indicator + semantic color

### Empty States
- [ ] Professional messages (no "No data")
- [ ] No emojis

## Phase 4: Validation & Regression

### Functional Safety (MUST NOT CHANGE)
- [ ] Callbacks intact
- [ ] Callback IDs intact
- [ ] Component IDs intact
- [ ] Calculations intact
- [ ] Providers intact
- [ ] CBOE ingestion intact
- [ ] Storage intact
- [ ] Scheduler intact
- [ ] Plotly chart internals intact

### Regression Checklist
- [ ] Dashboard tab
- [ ] Analytics tab
- [ ] Heatmap tab (all 5 sub-panes)
- [ ] Positioning tab
- [ ] Tape tab
- [ ] Whale Tracker
- [ ] GEX Levels
- [ ] Modals (CFD, Tastytrade, native)
- [ ] Dropdowns
- [ ] Segmented controls
- [ ] Checkboxes
- [ ] Buttons
- [ ] Symbol selector
- [ ] Empty states
- [ ] Status states
- [ ] Charts
- [ ] Responsive (1440, 1280, 1024, 768, 480)
- [ ] All supported instruments (SPX, NDX, SPY, QQQ, ES, NQ, BTC, GC)

### Automated CSS Audit
- [ ] Duplicate selectors
- [ ] Duplicate :root
- [ ] Hardcoded colors
- [ ] Obsolete selectors
- [ ] Emoji check (0 in UI)
- [ ] Excessive !important
- [ ] Duplicate media queries
- [ ] Unused animations
- [ ] Conflicting declarations

## Definition of Done
- [ ] All 15 CSS modules created and loading
- [ ] Single :root in 01-tokens.css
- [ ] Zero neon (#00f0ff, #ff2e74) in chrome CSS
- [ ] Zero glow, text-shadow, decorative gradients, glassmorphism
- [ ] Zero emojis in UI (i18n.py + main.py + digest.py)
- [ ] Backward-compatible aliases working
- [ ] All tabs functional
- [ ] All modals functional
- [ ] All controls functional
- [ ] Responsive works
- [ ] Application loads without errors
- [ ] Final CSS audit passes