# ADR-002: GEX Sign Convention

Status: Accepted

## Context

Gamma exposure is displayed by strike and used for regime and level
calculations. A stable sign convention is required so calls, puts, and net
values retain the same interpretation across the dashboard.

## Decision

The current primary calculation in `metrics.enrich` assigns:

- Calls: positive GEX.
- Puts: negative GEX.
- Magnitude: `gamma * open_interest * contract_multiplier * spot^2 * 0.01`.

The same call-positive/put-negative sign is used by `flow_delta` for traded
gamma flow and by the historical backfill when it builds reconstructed chains.
Positive net GEX is interpreted by `regime_read` as stabilizing gamma; negative
net GEX is interpreted as amplifying gamma.

This records the convention implemented by the repository. It does not claim
that the sign is a universal market convention or an executable trading signal.

## Consequences

Per-strike charts can show call and put contributions with opposite signs.
Aggregations, zero-gamma searches, levels, and regime text must preserve this
sign rather than applying another call/put flip. Changes to the formula require
updates to the sign-focused tests and this ADR.
