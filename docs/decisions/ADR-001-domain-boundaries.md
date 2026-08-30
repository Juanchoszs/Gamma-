# ADR-001: Domain Boundaries

Status: Accepted

## Context

The dashboard combines market-data ingestion, persistence, scheduling, API
responses, and UI rendering. Domain models must remain usable without pulling
those infrastructure concerns into the domain layer.

## Decision

The domain layer owns market-data states, quality values, and normalized
snapshot/summary models. It does not import Dash, Flask, APScheduler, HTTP
clients, scheduler modules, or storage implementations.

The configuration package remains a separate lightweight dependency. Application
modules may depend on domain and configuration; domain modules do not depend on
application modules.

The current implementation has no infrastructure imports in `gex/domain/`.
`gex/domain/models.py` does use pandas for the normalized option-chain field,
so the boundary is infrastructure-free rather than dependency-free.

## Consequences

Domain behavior can be tested independently of the dashboard and network
providers. Ingestion and UI code must translate their data into domain models
instead of making domain objects depend on those systems. Pandas remains a
runtime dependency of the domain models.
