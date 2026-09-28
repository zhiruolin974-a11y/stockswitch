from __future__ import annotations

from datetime import datetime, time
from typing import Protocol
from zoneinfo import ZoneInfo


SHANGHAI = ZoneInfo("Asia/Shanghai")


class HolidayCalendar(Protocol):
    def is_holiday(self, day) -> bool: ...


class ChinaAMarketRules:
    def __init__(self, holiday_calendar: HolidayCalendar | None = None):
        self.holiday_calendar = holiday_calendar

    def state(self, at: datetime) -> str:
        local = at.astimezone(SHANGHAI)
        if local.weekday() >= 5 or (self.holiday_calendar and self.holiday_calendar.is_holiday(local.date())):
            return "Market Closed"
        clock = local.time()
        if time(9, 30) <= clock < time(11, 30) or time(13) <= clock < time(15):
            return "Market Open"
        if time(11, 30) <= clock < time(13):
            return "Lunch Break"
        return "Market Closed"

    def can_trade(self, at: datetime) -> bool:
        return self.state(at) == "Market Open"
