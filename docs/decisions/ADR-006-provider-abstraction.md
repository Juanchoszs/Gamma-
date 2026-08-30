# ADR-006: Provider Abstraction

Status: Accepted

## Context

The repository consumes different kinds of data: delayed public option chains,
live broker feeds, and historical OPRA data. They have different capabilities,
licensing constraints, authentication, and symbol semantics.

## Decision

Provider identity is centralized as metadata in `gex.config.providers`.
`ProviderType` currently identifies CBOE, dxFeed, and Databento. Metadata records
expected delay, live/historical support, and whether data is shareable. Existing
source aliases such as `futopt`, `native`, `dxfeed_live`, and `cboe_delayed`
resolve to those provider records.

The current code does not introduce a common transport or ingestion interface.
`ingest.py` fetches and parses CBOE delayed JSON; `futopt.py` builds native
futures-option chains using Tastytrade instruments and dxFeed events; `rtquote.py`
handles quote credentials, tokens, WebSocket decoding, and public demo access;
`backfill.py` uses Databento for historical reconstruction; `tt_auth.py` performs
the one-time Tastytrade OAuth exchange.

## Consequences

Provider metadata can be used for classification and policy without moving
network or authentication logic. CBOE-backed data remains the shareable delayed
path, Databento remains historical/personal-use data, and dxFeed broker data
remains non-shareable. Adding a provider should first add metadata and tests;
transport abstractions are deferred until duplicated behavior demonstrates a
real need.
