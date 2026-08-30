"""Transform price levels between index, ETF, and futures scales."""
from __future__ import annotations

from dataclasses import dataclass

from .config import UNDERLYINGS, targets


@dataclass(frozen=True)
class Scale:
    key: str
    label: str
    family: str
    source: str
    is_future: bool = False

    def cross_family(self, src_underlying: str) -> bool:
        """Return whether the source and target belong to different families."""
        src = UNDERLYINGS.get(src_underlying)
        return src is not None and src.family != self.family


def available_scales() -> list[Scale]:
    """Return each target underlying and its associated future scale."""
    out: list[Scale] = []
    for u in targets():
        out.append(Scale(u.key, u.key, u.family, u.key))
        if u.future:
            out.append(Scale(u.future, u.future, u.family, u.key, is_future=True))
    return out


def scale_by_key(key: str) -> Scale | None:
    return next((s for s in available_scales() if s.key == key), None)


def reference_price(scale: Scale, spots: dict[str, float],
                    bases: dict[str, float | None]) -> float | None:
    """Return the scale spot, adding the basis for futures."""
    spot = spots.get(scale.source)
    if spot is None:
        return None
    if scale.is_future:
        basis = bases.get(scale.source)
        if basis is None:
            return None
        return spot + basis
    return spot


def transform(src_underlying: str, target: Scale | None,
              spots: dict[str, float], bases: dict[str, float | None]):
    """Return a price conversion function, ratio, and conversion mode."""
    identity = (lambda x: x), 1.0, "native"
    if target is None or target.key == src_underlying:
        return identity

    src_spot = spots.get(src_underlying)
    if not src_spot:
        return identity

    # Exact conversion from an index to its associated future.
    if target.is_future and target.source == src_underlying:
        basis = bases.get(src_underlying)
        if basis is None:
            return identity
        return (lambda x: x + basis), 1.0, "basis"

    tgt = reference_price(target, spots, bases)
    if not tgt:
        return identity
    ratio = tgt / src_spot
    return (lambda x: x * ratio), ratio, "ratio"
