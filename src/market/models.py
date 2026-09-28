from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone


class MarketDataError(RuntimeError):
    pass


class MarketDataStale(MarketDataError):
    pass


@dataclass(frozen=True)
class MarketQuote:
    symbol: str
    name: str
    timestamp: datetime
    received_at: datetime
    last_price: float
    open: float
    high: float
    low: float
    previous_close: float
    volume: float
    turnover: float
    change: float
    change_percent: float
    source: str
    is_delayed: bool

    def __post_init__(self) -> None:
        if not self.symbol or not self.name or not self.source:
            raise ValueError("Quote identity is required")
        if self.timestamp.tzinfo is None or self.received_at.tzinfo is None:
            raise ValueError("Quote timestamps must include a timezone")
        for value in (self.last_price, self.open, self.high, self.low, self.previous_close, self.volume, self.turnover, self.change, self.change_percent):
            if not math.isfinite(value):
                raise ValueError("Quote values must be finite")
        if any(price <= 0 for price in (self.last_price, self.open, self.high, self.low, self.previous_close)) or self.volume < 0:
            raise ValueError("Invalid quote price or volume")

    def age_seconds(self, now: datetime) -> float:
        return (now.astimezone(timezone.utc) - self.timestamp.astimezone(timezone.utc)).total_seconds()

    def require_fresh(self, now: datetime, max_age_seconds: int) -> None:
        age = self.age_seconds(now)
        if age > max_age_seconds or age < -5:
            raise MarketDataStale(f"{self.symbol} quote age {age:.1f}s exceeds allowed range")
