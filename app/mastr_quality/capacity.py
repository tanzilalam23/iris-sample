"""Capacity parser (kW / kWh), independent from the coordinate parser.

Rules: a single dot or comma is a decimal mark (XML decimals use a dot).
If both appear, the LAST one is the decimal mark and the other is a
thousands separator. A repeated mark must form valid thousands groups
(1.234.567). Anything else is rejected rather than guessed.
Zero is a valid value; missing stays missing, never 0.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

_PATTERN = re.compile(r"^[+-]?\d[\d.,]*$")


@dataclass(frozen=True)
class CapacityResult:
    value: float | None
    reason: str | None  # None, "missing", "not_numeric" or "negative"


def parse_capacity(raw) -> CapacityResult:
    if raw is None:
        return CapacityResult(None, "missing")
    if isinstance(raw, bool):
        return CapacityResult(None, "not_numeric")

    if isinstance(raw, (int, float)):
        number = float(raw)
    else:
        text = str(raw).strip()
        if text == "":
            return CapacityResult(None, "missing")
        if not _PATTERN.match(text):
            return CapacityResult(None, "not_numeric")

        negative = text.startswith("-")
        text = text.lstrip("+-")
        has_dot, has_comma = "." in text, "," in text

        if has_dot and has_comma:
            decimal = "," if text.rfind(",") > text.rfind(".") else "."
            thousands = "." if decimal == "," else ","
            if text.count(decimal) != 1 or text.rfind(thousands) > text.rfind(decimal):
                return CapacityResult(None, "not_numeric")
            text = text.replace(thousands, "").replace(decimal, ".")
        elif has_dot or has_comma:
            mark = "," if has_comma else "."
            if text.count(mark) > 1:
                if not re.fullmatch(r"\d{1,3}(?:" + re.escape(mark) + r"\d{3})+", text):
                    return CapacityResult(None, "not_numeric")
                text = text.replace(mark, "")
            else:
                text = text.replace(",", ".")

        try:
            number = float(text)
        except ValueError:
            return CapacityResult(None, "not_numeric")
        if negative:
            number = -number

    if math.isnan(number) or math.isinf(number):
        return CapacityResult(None, "not_numeric")
    if number < 0:
        return CapacityResult(None, "negative")
    return CapacityResult(number, None)