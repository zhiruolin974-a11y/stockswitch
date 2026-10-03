"""Consistent display-only A-share formatting; values are never used for fills."""

from __future__ import annotations

import math


GAIN_RED = "#C62828"
LOSS_GREEN = "#2E7D32"
NEUTRAL_GRAY = "#616161"


def _finite(value: float | int | None) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _format(value: float | int | None, *, scale: float, suffix: str,
            prefix: str = "", signed: bool = False) -> str:
    number = _finite(value)
    if number is None:
        return "—"
    display = round(number * scale, 2)
    sign = "+" if signed and display > 0 else "-" if display < 0 else ""
    return f"{sign}{prefix}{abs(display):,.2f}{suffix}"


def money(value: float | int | None, signed: bool = False) -> str:
    """Format yuan, e.g. +¥1,234.50 (signed) or ¥1,234.50."""
    return _format(value, scale=1, prefix="¥", suffix="", signed=signed)


def percent_ratio(value: float | int | None, signed: bool = False) -> str:
    """Format a fractional ratio: 0.025 becomes 2.50%."""
    return _format(value, scale=100, suffix="%", signed=signed)


def percent_points(value: float | int | None, signed: bool = False) -> str:
    """Format pre-scaled quote percentage points: 2.5 becomes 2.50%."""
    return _format(value, scale=1, suffix="%", signed=signed)


def gain_color(value: float | int | None) -> str:
    """A-share convention: rising/gain red, falling/loss green."""
    number = _finite(value)
    return GAIN_RED if number is not None and number > 0 else LOSS_GREEN if number is not None and number < 0 else NEUTRAL_GRAY
