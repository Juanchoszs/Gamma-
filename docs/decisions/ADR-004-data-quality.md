# ADR-004: Data Quality and Market State

Status: Accepted

## Context

The dashboard receives delayed public data, live broker data, reconstructed
historical data, and sometimes incomplete chains. Numeric values alone cannot
explain whether a result is fresh, stale, invalid, or absent.

## Decision

`gex.domain.quality` defines the states `VALID`, `WARNING`, `STALE`, `EXPIRED`,
`INVALID`, and `MISSING`. Missing measurements are distinct from numeric zero.
The quality evaluator accepts age, provider, required-field completeness, and
expired-contract information.

`gex.domain.market_state` defines interface states including `LIVE`, `DELAYED`,
`MARKET_CLOSED`, `HISTORICAL`, and `NO_DATA`. `resolve_market_state` prioritizes
historical view and invalid/no-data conditions before considering market hours,
snapshot availability, and quality.

The current code declares provider-specific age thresholds for CBOE, dxFeed,
and native data. `get_quality_config` selects and returns the typed threshold
configuration for the requested provider identifier. Stale and expired quality
are represented as `DELAYED` market state when the market is open; they are not
separate `MarketDataState` enum members.

## Consequences

APIs and UI can expose data provenance and state instead of implying that every
number is live. Quality and market state remain separate dimensions while the
resolver provides a stable interface-level state.
