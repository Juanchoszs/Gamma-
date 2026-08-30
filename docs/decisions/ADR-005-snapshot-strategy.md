# ADR-005: Snapshot Strategy

Status: Accepted

## Context

The application needs reproducible option-chain views, daily summaries, flow
history, and historical backtest inputs without writing every market event as a
separate record.

## Decision

Live CBOE pulls are enriched and, when their cadence is due, saved as Parquet
snapshots under `data/snapshots/{symbol}/{YYYY-MM-DD}/{HHMMSS}.parquet`.
Snapshot metadata columns record symbol, capture time, source, snapshot type,
quality, market state, schema version, age, and provider timestamp.

Summary rows are appended separately to
`data/history/metrics.parquet`. Delta-flow bars and other event aggregates are
written to daily Parquet files. The scheduler keeps in-memory state and uses
cadences: target snapshots default to ten minutes, flows to one minute, and
constituents use slower cadences.

Native NQ/ES and native index chains use the same snapshot persistence with
`source="dxfeed"` and separate storage keys where required. Historical
Databento reconstruction is timestamped at 16:00 for the represented session;
its chain is persisted only when `persist_chain`/`persist_chains` is enabled.

## Consequences

The system favors bounded writes and replayable daily files over per-event
persistence. Snapshots are suitable for recalculating levels and backtests,
while summary and flow files provide lighter-weight history. Atomic Parquet
writes and per-file locks protect concurrent scheduler updates.
