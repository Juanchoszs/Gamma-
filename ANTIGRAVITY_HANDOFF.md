# GEX Dashboard — Architecture Refactor Handoff

## 1. Project Overview

This repository is a Python-based GEX (Gamma Exposure) dashboard for analyzing options market positioning.

The application processes options chains and calculates market metrics such as:

- Gamma Exposure (GEX)
- Delta Exposure (DEX)
- Zero Gamma
- Gamma walls
- Call/Put positioning
- Dealer positioning
- Market state
- Data quality
- Historical snapshots
- Futures options data
- Real-time quotes
- Flow data

The main package is:

```text
gex/
```

The project includes a Dash web application, API functionality, schedulers, data ingestion, persistence, historical backfills, and multiple market data providers.

---

# 2. IMPORTANT: CURRENT REFACTORING GOAL

The repository is currently undergoing an incremental architecture refactor.

The objective is NOT to rewrite the project.

The objective is to:

1. Preserve existing behavior.
2. Preserve backward compatibility.
3. Reduce architectural coupling.
4. Separate domain concepts from infrastructure.
5. Extract pure calculation logic from large modules.
6. Improve testability.
7. Keep the application working after every step.

This is an incremental refactor.

DO NOT perform a massive rewrite.

Every phase must be validated with the existing test suite.

---

# 3. CURRENT PROJECT STRUCTURE

Current relevant structure:

```text
gex/
├── domain/
│   ├── __init__.py
│   ├── models.py
│   ├── quality.py
│   └── market_state.py
│
├── config/
│   ├── __init__.py
│   ├── constants.py
│   ├── market.py
│   ├── providers.py
│   └── settings.py
│
├── assets/
│
├── api.py
├── app.py
├── backfill.py
├── backtest.py
├── backup.py
├── config migration completed
├── digest.py
├── export.py
├── flowtape.py
├── futopt.py
├── greeks.py
├── idxopt.py
├── ingest.py
├── metrics.py
├── pinning.py
├── pricehist.py
├── rates.py
├── roll.py
├── rtquote.py
├── scheduler.py
├── store.py
├── tickcapture.py
├── tickstats.py
├── tt_auth.py
└── tt_web.py
```

---

# 4. PHASE A — COMPLETED

Phase A focused on Data Integrity and Truthfulness.

## A1 — Timezone consistency

Fixed timezone handling in:

```text
gex/store.py
```

Changed naive:

```python
datetime.now()
```

to Eastern Time-aware usage:

```python
datetime.now(ET)
```

A regression test was added.

---

## A2 — Domain models

Domain concepts were moved out of the old configuration layer.

Current domain package:

```text
gex/domain/
```

Includes:

### quality.py

Contains centralized data quality concepts.

Examples include:

* VALID
* WARNING
* STALE
* EXPIRED
* INVALID
* MISSING

### market_state.py

Contains explicit market state concepts.

Examples include:

* LIVE
* DELAYED
* MARKET_CLOSED
* HISTORICAL
* NO_DATA

### models.py

Contains shared domain models such as metrics/snapshot models.

The purpose is to avoid putting domain concepts inside configuration modules.

---

## A3 — Centralized Data Quality

Data quality evaluation was centralized.

Provider-aware quality thresholds were introduced.

The architecture should now use domain quality logic rather than scattering ad-hoc quality decisions throughout the application.

---

## A4 — Missing vs Zero

The project now distinguishes:

```text
Missing data != numeric zero
```

For example:

* `None`
* `NaN`
* Missing measurement

must not automatically be interpreted as:

```text
0
```

This is particularly important for DEX and historical data.

---

## A5 — Explicit Market State

Market state handling was centralized.

The domain model now separates:

```text
DataQuality
```

from:

```text
MarketDataState
```

These concepts must remain distinct.

Example:

```text
STALE
```

is a data quality condition.

It can map to:

```text
DELAYED
```

as a market/UI state.

Do not reintroduce invalid states such as:

```python
MarketDataState.STALE
```

unless explicitly redesigning the domain model.

---

## A6 — Snapshot Metadata

Snapshot persistence was improved so snapshots can carry metadata needed to understand their origin and quality.

---

# 5. PHASE B — ARCHITECTURAL FOUNDATION

## B1/B2 — Configuration decomposition completed

Previously the project had:

```text
gex/config.py
```

This was decomposed into:

```text
gex/config/
├── __init__.py
├── constants.py
├── market.py
├── providers.py
└── settings.py
```

### constants.py

Technical and financial constants.

Examples:

```python
RISK_FREE_RATE
CONTRACT_MULTIPLIER
YEAR_SECONDS
```

### market.py

Market structure definitions.

Contains:

```python
Underlying
UNDERLYINGS
targets()
constituents()
```

### settings.py

Runtime application settings.

Contains:

```python
Settings
SETTINGS
DATA_DIR
```

### providers.py

Provider metadata and provider abstractions.

Includes provider concepts for sources such as:

* CBOE
* dxFeed
* Databento

and aliases used by existing code.

IMPORTANT:

Provider metadata was centralized.

Authentication, HTTP clients, and ingestion logic were intentionally NOT moved during this phase.

---

## Compatibility facade

`gex/config/__init__.py` acts as the public compatibility layer.

Existing imports such as:

```python
from gex.config import SETTINGS
```

must continue working.

Do not unnecessarily change all imports across the repository.

The goal is architectural migration without breaking the public internal API.

---

# 6. B3 — ADRs COMPLETED

Architecture Decision Records were created in:

```text
docs/decisions/
```

They document important architectural decisions.

Current ADRs:

```text
ADR-001-domain-boundaries.md
ADR-002-gex-sign-convention.md
ADR-003-dex-sign-convention.md
ADR-004-data-quality.md
ADR-005-snapshot-strategy.md
ADR-006-provider-abstraction.md
```

These are important.

Before changing the relevant architecture, inspect the ADR.

---

# 7. B4 — CONSISTENCY FIXES COMPLETED

Several inconsistencies discovered during Phase B were fixed.

## Market State consistency

Invalid references were removed.

The separation is:

```text
DataQuality:
    VALID
    WARNING
    STALE
    EXPIRED
    INVALID
    MISSING

MarketDataState:
    LIVE
    DELAYED
    MARKET_CLOSED
    HISTORICAL
    NO_DATA
```

A stale/expired quality condition can map to a UI state such as `DELAYED`.

Do not mix these two enums.

---

## Provider quality configuration

A typed provider configuration mechanism was added.

The quality system should select configuration for the requested provider instead of returning an entire configuration dictionary.

Relevant concepts include:

```python
ProviderQualityConfig
get_quality_config(provider)
```

---

## DEX consistency

DEX historical backfill was aligned with the live calculation convention.

The current intended convention is:

```text
DEX = -delta * open_interest * contract_multiplier * spot
```

Historical and live calculations should not silently use different sign conventions.

`net_dex` was added to historical output.

Before changing DEX formulas, inspect:

```text
docs/decisions/ADR-003-dex-sign-convention.md
```

---

# 8. TEST BASELINE

The project currently has:

```text
384 passing tests
```

The original baseline was:

```text
374 tests
```

Additional regression tests were added during the architecture work.

The test suite must remain green.

Always run:

```powershell
python -m pytest tests/ --tb=short
```

Do not consider a refactoring task complete if the full suite fails.

---

# 9. CURRENT PHASE: PHASE C

Phase C is focused on modularizing large calculation and infrastructure modules.

The most important target is:

```text
gex/metrics.py
```

The goal is to extract pure calculations into focused modules while preserving:

```python
gex.metrics
```

as a compatibility facade.

---

# 10. CURRENT BLOCKING ISSUE

An attempt was started for:

```text
C1 — Metrics extraction
```

A background agent attempted to extract calculation logic from:

```text
gex/metrics.py
```

into more focused modules.

However, its validation reported approximately:

```text
23 test failures
```

Most failures appeared related to persistence/import/re-export behavior.

IMPORTANT:

Do not blindly continue from the extraction.

First inspect:

```powershell
git status
git diff
```

Then identify:

1. What files the C1 extraction created.
2. What imports changed.
3. What functions were removed from `metrics.py`.
4. Whether compatibility exports were broken.
5. Whether failures are genuinely caused by the extraction.

Do not accept a refactor simply because the new architecture looks cleaner.

Behavioral compatibility comes first.

---

# 11. IMMEDIATE NEXT TASK

The next task is:

# C1 — Extract pure metrics calculations safely

Target:

```text
gex/metrics.py
```

Desired architecture conceptually:

```text
gex/
├── calculations/
│   ├── gamma.py
│   ├── delta.py
│   ├── zero_gamma.py
│   └── ...
│
└── metrics.py
```

However:

DO NOT create modules just for cosmetic reasons.

Only extract cohesive pure logic.

---

## C1 Rules

### Rule 1 — Preserve public API

Existing imports must continue working.

For example, if existing code does:

```python
from gex.metrics import calculate_x
```

that should continue working.

Use re-exports if necessary.

Example:

```python
from .calculations.gamma import calculate_x
```

inside `metrics.py`.

---

### Rule 2 — Extract pure logic first

Good extraction candidates:

* mathematical calculations;
* GEX calculations;
* DEX calculations;
* zero gamma search;
* strike aggregation;
* transformations without filesystem access;
* transformations without HTTP;
* deterministic functions.

Do NOT mix extraction with:

* persistence;
* scheduler logic;
* Dash UI;
* HTTP providers;
* application startup.

---

### Rule 3 — Avoid circular imports

Preferred dependency direction:

```text
config
   ↓

domain
   ↓

calculations
   ↓

application/services
   ↓

infrastructure
   ↓

UI/API
```

Exact structure may vary, but avoid reverse dependencies.

Specifically:

```text
domain
```

should not depend on:

```text
app
scheduler
store
Dash
```

Pure calculations should not depend on UI.

---

### Rule 4 — Small commits

Work incrementally.

Recommended sequence:

1. Inspect one cohesive group of functions.
2. Extract it.
3. Add compatibility imports.
4. Run targeted tests.
5. Run full suite.
6. Only then continue.

Do not extract the entire `metrics.py` in one large operation.

---

# 12. IMPORTANT: DO NOT REWRITE STORE/SCHEDULER/APP

For C1, do not modify these unless strictly necessary to repair a broken import:

```text
gex/store.py
gex/scheduler.py
gex/app.py
```

Phase C should focus first on calculation boundaries.

Do not turn C1 into a repository-wide rewrite.

---

# 13. DATA DIRECTORY CLEANUP

The repository root currently contains generated/runtime directories such as:

```text
.pytest_cache/
build/
gex_dashboard.egg-info/
logs/
data/
```

Not all of these should necessarily be committed.

Before changing anything, inspect:

```text
.gitignore
```

Likely categories:

## Generated build artifacts

Usually safe to ignore:

```text
build/
dist/
*.egg-info/
.pytest_cache/
```

## Runtime logs

Usually safe to ignore:

```text
logs/
*.log
server.out.log
server.err.log
```

unless logs are intentionally versioned.

## Virtual environment

Should normally be ignored:

```text
.venv/
```

## Data

Be careful.

The project uses:

```text
data/
```

for market history and snapshots.

Do NOT blindly delete or ignore all data.

Determine whether:

1. data is intentionally versioned;
2. data is runtime-generated;
3. some sample data is required for tests.

A likely future architecture improvement is:

```text
data/
├── history/
├── snapshots/
├── cache/
└── runtime/
```

but do not perform this migration until the current metrics extraction is stable.

---

# 14. CODE STYLE REQUIREMENTS

The user wants the codebase cleaner and less over-documented.

Do NOT add excessive comments.

Avoid comments that simply restate the code.

Bad:

```python
# Set the interval to 60 seconds
interval = 60
```

Good:

```python
# CBOE publishes delayed data, so polling faster does not improve freshness.
interval = 60
```

Use comments only when they explain:

* business rules;
* market conventions;
* non-obvious decisions;
* numerical assumptions;
* external provider behavior;
* architectural constraints.

---

# 15. LANGUAGE REQUIREMENTS

The existing project historically contains a lot of French comments.

New code should preferably use English.

Do not perform a massive translation-only refactor.

When modifying a file:

* remove clearly unnecessary French comments in the modified area;
* simplify overly verbose comments;
* keep important business context;
* avoid touching unrelated code just for language cleanup.

The objective is cleaner code, not a giant formatting diff.

---

# 16. GENERAL REFACTORING PRINCIPLES

Follow these rules throughout the project:

### Preserve behavior

Architecture improvements must not silently change calculations.

### Tests first

If behavior is unclear:

1. inspect tests;
2. add a regression test;
3. then refactor.

### Backward compatibility

Existing internal imports should continue working when possible.

### No speculative abstractions

Do not create:

* factories;
* interfaces;
* base classes;
* dependency injection systems;

unless the existing code genuinely requires them.

### No giant commits

Keep each phase logically focused.

### No cosmetic rewrites

Avoid massive formatting or renaming changes.

### Verify packaging

The project now uses subpackages such as:

```text
gex.config
gex.domain
```

Packaging configuration must continue including them.

---

# 17. RECOMMENDED WORKFLOW FOR EVERY TASK

Before editing:

```powershell
git status
git diff
```

Inspect relevant code.

Then:

1. Identify the smallest safe change.
2. Implement it.
3. Run targeted tests.
4. Run the full suite.
5. Run:

```powershell
git diff --check
```

6. Inspect:

```powershell
git diff
```

7. Only then report completion.

Do not report a task as complete while tests are failing.

---

# 18. CURRENT PRIORITY ORDER

Current recommended sequence:

## Phase C

### C1

Safely extract pure calculation logic from `gex/metrics.py`.

### C2

Separate application/services orchestration from calculations where justified.

### C3

Review persistence boundaries.

### C4

Review scheduler responsibilities.

---

## Future Phase D

Potential infrastructure cleanup:

* provider adapters;
* storage abstractions;
* clearer service boundaries;
* runtime/generated data organization.

These are not immediate tasks.

---

# 19. DEFINITION OF SUCCESS

The refactor is successful if:

1. The application still works.
2. All tests pass.
3. Public/internal compatibility is preserved.
4. `metrics.py` becomes smaller and more focused.
5. Pure calculations become independently testable.
6. Domain concepts remain independent from UI/infrastructure.
7. Configuration remains centralized without becoming a dependency dumping ground.
8. Comments are concise and useful.
9. No large unnecessary rewrite is introduced.

---

# 20. STARTING INSTRUCTION FOR THE NEXT AGENT

Start by inspecting the current unfinished C1 work.

Run:

```powershell
git status
git diff --stat
git diff
```

Then inspect the current test failures.

Do NOT continue extracting code until you understand why the previous C1 attempt produced approximately 23 failures.

Determine whether the failures come from:

* broken imports;
* missing re-exports;
* changed module initialization;
* persistence behavior accidentally affected;
* incorrect extraction boundaries.

Restore compatibility first.

Then continue C1 incrementally.

The immediate objective is not "make the architecture look perfect".

The immediate objective is:

```text
Safely complete the metrics extraction with all tests passing.
```
