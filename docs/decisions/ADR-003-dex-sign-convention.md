# ADR-003: DEX Sign Convention

Status: Accepted

## Context

DEX describes delta exposure and is interpreted independently from GEX. The
repository contains explicit tests because applying the GEX sign rule to DEX
would reverse the per-contract result.

## Decision

For live/enriched chains, `metrics.enrich` stores:

`DEX = -delta_bs * open_interest * contract_multiplier * spot`

Therefore, with the current dealer-position assumption, a call has negative
DEX and a put has positive DEX. `regime_read` interprets negative net DEX as
dealer short delta with latent buying pressure, and positive net DEX as dealer
long delta with latent selling pressure.

The signed dxFeed order-flow path uses the same dealer-view delta sign for
aggressor trades. The tests verify that a call buyer produces negative dealer
delta and a put buyer produces positive dealer delta.

The historical `backfill.build_day` path uses the same leading minus, so live
and reconstructed historical DEX values use the same formula.

## Consequences

DEX and GEX must not share a generic sign multiplier. Net DEX interpretation is
comparable between live and reconstructed historical values when provenance and
the underlying data source are otherwise comparable.
