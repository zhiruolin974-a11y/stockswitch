from __future__ import annotations

from bisect import bisect_left, bisect_right
from datetime import date


class UnknownTradingDay(ValueError):
    pass


class ChinaAMarketCalendar:
    """Observed exchange sessions, normally sourced from a benchmark index."""

    def __init__(self, sessions: list[date] | tuple[date, ...], covered_start: date, covered_end: date):
        self.sessions = tuple(sessions)
        if not self.sessions or list(self.sessions) != sorted(set(self.sessions)):
            raise ValueError("Trading sessions must be sorted and unique")
        if covered_start > self.sessions[0] or covered_end < self.sessions[-1]:
            raise ValueError("Coverage must contain all observed sessions")
        self.covered_start = covered_start
        self.covered_end = covered_end

    def _covered(self, day: date) -> None:
        if not self.covered_start <= day <= self.covered_end:
            raise UnknownTradingDay(f"No verified calendar coverage for {day}")

    def is_trading_day(self, day: date) -> bool:
        self._covered(day)
        i = bisect_left(self.sessions, day)
        return i < len(self.sessions) and self.sessions[i] == day

    def is_holiday(self, day: date) -> bool:
        return not self.is_trading_day(day)

    def previous_trading_day(self, day: date) -> date:
        self._covered(day)
        i = bisect_left(self.sessions, day) - 1
        if i < 0:
            raise UnknownTradingDay(f"No previous observed session before {day}")
        return self.sessions[i]

    def next_trading_day(self, day: date) -> date:
        self._covered(day)
        i = bisect_right(self.sessions, day)
        if i >= len(self.sessions):
            raise UnknownTradingDay(f"No next observed session after {day}")
        return self.sessions[i]

    def trading_days(self, start: date, end: date) -> list[date]:
        self._covered(start)
        self._covered(end)
        if end < start:
            raise ValueError("Invalid date range")
        return list(self.sessions[bisect_left(self.sessions, start):bisect_right(self.sessions, end)])
