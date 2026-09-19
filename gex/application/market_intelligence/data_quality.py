"""Data-quality inspection for normalized option-chain inputs."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class OptionDataQuality:
    """Counts that expose malformed source records without repairing them."""

    record_count: int
    valid_record_count: int
    invalid_record_count: int
    missing_greeks: int
    missing_open_interest: int
    missing_volume: int
    missing_expiration: int
    invalid_timestamps: int
    duplicate_contracts: int

    def to_dict(self) -> dict[str, int]:
        return {
            "record_count": self.record_count,
            "valid_record_count": self.valid_record_count,
            "invalid_record_count": self.invalid_record_count,
            "missing_greeks": self.missing_greeks,
            "missing_open_interest": self.missing_open_interest,
            "missing_volume": self.missing_volume,
            "missing_expiration": self.missing_expiration,
            "invalid_timestamps": self.invalid_timestamps,
            "duplicate_contracts": self.duplicate_contracts,
        }


def inspect_option_data_quality(chain: pd.DataFrame | None) -> OptionDataQuality:
    """Inspect an existing chain and report quality concerns without mutation.

    A duplicate is only a duplicate contract when strike, option side and
    expiration repeat together. Repeated strikes across expirations or sides
    are valid and must remain visible to the analytics engine.
    """
    frame = chain if chain is not None else pd.DataFrame()
    count = int(len(frame))
    if frame.empty:
        return OptionDataQuality(0, 0, 0, 0, 0, 0, 0, 0, 0)

    expiry_raw = frame.get("expiry", pd.Series(index=frame.index, dtype=object))
    expiry = pd.to_datetime(expiry_raw, errors="coerce")
    invalid_contract = ~structurally_valid_option_records(frame)

    missing_expiration = int(pd.isna(expiry_raw).sum()) if "expiry" in frame else count
    invalid_timestamps = int((expiry_raw.notna() & expiry.isna()).sum()) if "expiry" in frame else count
    duplicate_contracts = _duplicate_contract_count(frame)
    return OptionDataQuality(
        record_count=count,
        valid_record_count=max(count - int(invalid_contract.sum()), 0),
        invalid_record_count=int(invalid_contract.sum()),
        missing_greeks=_missing_any(frame, ("gamma", "delta", "iv")),
        missing_open_interest=_missing(frame, "open_interest"),
        missing_volume=_missing(frame, "volume"),
        missing_expiration=missing_expiration,
        invalid_timestamps=invalid_timestamps,
        duplicate_contracts=duplicate_contracts,
    )


def valid_option_records(chain: pd.DataFrame | None) -> pd.DataFrame:
    """Return a copy containing only structurally valid option contracts.

    This deliberately does not impute missing Greeks, OI or volume. Those
    fields remain visible to quality diagnostics and downstream engines can
    decide whether an available metric is usable.
    """
    frame = chain if chain is not None else pd.DataFrame()
    if frame.empty:
        return frame.copy()
    return frame.loc[structurally_valid_option_records(frame)].copy()


def structurally_valid_option_records(frame: pd.DataFrame) -> pd.Series:
    """Boolean contract-validity mask shared by diagnostics and analytics."""
    strike = pd.to_numeric(frame.get("strike", pd.Series(index=frame.index, dtype=float)), errors="coerce")
    expiry = pd.to_datetime(frame.get("expiry", pd.Series(index=frame.index, dtype=object)), errors="coerce")
    option_type = frame.get("type", pd.Series(index=frame.index, dtype=object)).astype(str).str.upper()
    return strike.notna() & (strike > 0) & expiry.notna() & option_type.isin(("C", "P"))


def _missing(frame: pd.DataFrame, column: str) -> int:
    return int(frame[column].isna().sum()) if column in frame else int(len(frame))


def _missing_any(frame: pd.DataFrame, columns: tuple[str, ...]) -> int:
    if not columns:
        return 0
    missing = pd.Series(False, index=frame.index)
    for column in columns:
        missing |= frame[column].isna() if column in frame else True
    return int(missing.sum())


def _duplicate_contract_count(frame: pd.DataFrame) -> int:
    keys = ("strike", "type", "expiry")
    if not set(keys).issubset(frame.columns):
        return 0
    return int(frame.duplicated(list(keys), keep=False).sum())
