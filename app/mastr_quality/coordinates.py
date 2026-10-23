"""Coordinate parser for MaStR latitude/longitude values.

Why a separate parser: coordinates are never written with thousands
separators. A value like "48.123" or "48,123" can therefore only mean
48.123 degrees. A generic number parser that treats a dot or comma as a
thousands separator would turn it into 48123, which is impossible.
Capacity values (kW, kWh) are parsed elsewhere and are not affected.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

# optional sign, digits, optionally ONE decimal mark (dot or comma) + digits
_PATTERN = re.compile(r"^[+-]?\d+(?:[.,]\d+)?$")

_LIMITS = {"lat": 90.0, "lon": 180.0}


@dataclass(frozen=True)
class CoordinateResult:
    """Outcome of parsing: either a value, or a reason it was rejected."""

    value: float | None
    reason: str | None  # None, "missing", "not_numeric" or "out_of_range"


def parse_coordinate(raw, kind: str) -> CoordinateResult:
    if kind not in _LIMITS:
        raise ValueError("kind must be 'lat' or 'lon'")

    # 1. Nothing there -> "missing" (never turned into 0)
    if raw is None:
        return CoordinateResult(None, "missing")

    # 2. Turn the input into a float, or reject it
    if isinstance(raw, bool):
        return CoordinateResult(None, "not_numeric")

    if isinstance(raw, (int, float)):
        number = float(raw)
    else:
        text = str(raw).strip().replace("\u2212", "-")  # unicode minus sign
        if text == "":
            return CoordinateResult(None, "missing")
        if not _PATTERN.match(text):
            return CoordinateResult(None, "not_numeric")
        number = float(text.replace(",", "."))

    if math.isnan(number) or math.isinf(number):
        return CoordinateResult(None, "not_numeric")

    # 3. Must be a possible coordinate on Earth
    if abs(number) > _LIMITS[kind]:
        return CoordinateResult(None, "out_of_range")

    return CoordinateResult(number, None)