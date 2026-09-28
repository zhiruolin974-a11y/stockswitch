from __future__ import annotations

import json
import math
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.market.calendar import SHANGHAI
from src.market.tencent import validate_symbol


class InvalidHistoricalData(ValueError):
    pass


@dataclass(frozen=True)
class MarketBar:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float
    adjustment: str = "none"

    def __post_init__(self):
        if self.timestamp.tzinfo is None or self.adjustment not in ("none", "qfq", "hfq"):
            raise InvalidHistoricalData(f"{self.symbol} {self.timestamp}: invalid timezone or adjustment")
        values = (self.open, self.high, self.low, self.close, self.volume, self.turnover)
        if (not all(math.isfinite(v) for v in values) or min(self.open, self.high, self.low, self.close) <= 0
                or self.volume < 0 or self.turnover < 0 or not self.low <= self.open <= self.high
                or not self.low <= self.close <= self.high):
            raise InvalidHistoricalData(f"{self.symbol} {self.timestamp.date()}: invalid OHLCV {values}")

    @property
    def day(self) -> date:
        return self.timestamp.astimezone(SHANGHAI).date()


def validate_bars(bars: list[MarketBar], symbol: str, adjustment: str) -> None:
    previous = None
    for index, bar in enumerate(bars):
        if bar.symbol != symbol or bar.adjustment != adjustment:
            raise InvalidHistoricalData(f"{symbol} row {index}: symbol/adjustment mismatch")
        if previous is not None and bar.timestamp <= previous:
            raise InvalidHistoricalData(f"{symbol} row {index}: duplicate or unordered timestamp {bar.timestamp}")
        previous = bar.timestamp


class HistoricalMarketDataProvider(ABC):
    name: str

    @abstractmethod
    def get_bars(self, symbol: str, start: date, end: date, adjustment: str = "none") -> list[MarketBar]: ...


def _parse_tencent_history(payload: bytes, symbol: str, adjustment: str, start: date, end: date) -> list[MarketBar]:
    try:
        text = payload.decode("utf-8")
        body = json.loads(text[text.index("={") + 1:])
        if body.get("code") != 0:
            raise InvalidHistoricalData(f"{symbol}: provider error {body.get('msg')}")
        data = body["data"][symbol]
        rows = data.get({"none": "day", "qfq": "qfqday", "hfq": "hfqday"}[adjustment])
        if rows is None:
            raise InvalidHistoricalData(f"{symbol}: missing {adjustment} daily bars")
        bars = []
        for i, row in enumerate(rows):
            day = date.fromisoformat(row[0])
            if start <= day <= end:
                volume = float(row[5]) * (1 if symbol.startswith(("sh688", "sz399", "sh000", "sz000")) else 100)
                bars.append(MarketBar(symbol, datetime.combine(day, time(15), SHANGHAI),
                                      float(row[1]), float(row[3]), float(row[4]), float(row[2]),
                                      volume, float(row[8]) * 10000, adjustment))
        validate_bars(bars, symbol, adjustment)
        return bars
    except (UnicodeError, ValueError, KeyError, IndexError, TypeError) as exc:
        if isinstance(exc, InvalidHistoricalData):
            raise
        raise InvalidHistoricalData(f"{symbol}: invalid provider payload near row {locals().get('i', '?')}: {exc}") from exc


class TencentHistoricalMarketDataProvider(HistoricalMarketDataProvider):
    name = "Tencent Finance historical daily"
    endpoint = "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"

    def __init__(self, timeout: float = 15):
        self.timeout = timeout

    def get_bars(self, symbol: str, start: date, end: date, adjustment: str = "none") -> list[MarketBar]:
        symbol = validate_symbol(symbol, allow_index=True)
        if adjustment not in ("none", "qfq", "hfq") or end < start:
            raise ValueError("Invalid adjustment or date range")
        bars: list[MarketBar] = []
        remote_adjustment = "" if adjustment == "none" else adjustment
        for year in range(start.year, end.year + 1):
            parameters = {
                "_var": f"kline_day{remote_adjustment}{year}",
                "param": f"{symbol},day,{year}-01-01,{year + 1}-12-31,640,{remote_adjustment}",
            }
            request = Request(self.endpoint + "?" + urlencode(parameters),
                              headers={"User-Agent": "StockSwitch/0.2 (personal research)"})
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    if response.status != 200:
                        raise InvalidHistoricalData(f"{symbol}: HTTP {response.status}")
                    payload = response.read(1_500_001)
            except OSError as exc:
                raise InvalidHistoricalData(f"{symbol}: history download failed: {exc}") from exc
            if len(payload) > 1_500_000:
                raise InvalidHistoricalData(f"{symbol}: oversized history payload")
            bars.extend(_parse_tencent_history(payload, symbol, adjustment, start, end))
        # The remote endpoint can return overlapping 640-bar windows. Repeated identical
        # dates across requests are a fetch artifact; conflicting values are an error.
        by_day: dict[date, MarketBar] = {}
        for bar in bars:
            if bar.day in by_day and by_day[bar.day] != bar:
                raise InvalidHistoricalData(f"{symbol} {bar.day}: conflicting overlapping bars")
            by_day[bar.day] = bar
        result = [by_day[day] for day in sorted(by_day)]
        validate_bars(result, symbol, adjustment)
        return result


class FakeHistoricalMarketDataProvider(HistoricalMarketDataProvider):
    name = "FakeHistoricalMarketDataProvider"

    def __init__(self, bars: dict[str, list[MarketBar]]):
        self.bars = bars
        self.requests: list[tuple[str, date, date, str]] = []

    def get_bars(self, symbol: str, start: date, end: date, adjustment: str = "none") -> list[MarketBar]:
        self.requests.append((symbol, start, end, adjustment))
        result = [bar for bar in self.bars.get(symbol, []) if start <= bar.day <= end]
        validate_bars(result, symbol, adjustment)
        return result


class HistoricalCache(HistoricalMarketDataProvider):
    """Coverage intervals distinguish market holidays from missing downloads."""

    def __init__(self, path: Path, upstream: HistoricalMarketDataProvider):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS bars (
              symbol TEXT, frequency TEXT, adjustment TEXT, day TEXT, payload TEXT,
              PRIMARY KEY(symbol,frequency,adjustment,day));
            CREATE TABLE IF NOT EXISTS coverage (
              symbol TEXT, frequency TEXT, adjustment TEXT, start TEXT, end TEXT,
              provider TEXT, last_updated TEXT,
              PRIMARY KEY(symbol,frequency,adjustment,start,end,provider));
        """)
        self.upstream = upstream
        self.name = f"Cached {upstream.name}"
        providers = {row[0] for row in self.connection.execute("SELECT DISTINCT provider FROM coverage")}
        if providers and providers != {upstream.name}:
            self.connection.close()
            raise ValueError("History cache belongs to another provider; use a separate cache file")

    def coverage(self, symbol: str, adjustment: str) -> list[tuple[date, date]]:
        rows = self.connection.execute(
            "SELECT start,end FROM coverage WHERE symbol=? AND frequency='daily' AND adjustment=? AND provider=? ORDER BY start",
            (symbol, adjustment, self.upstream.name)).fetchall()
        return [(date.fromisoformat(a), date.fromisoformat(b)) for a, b in rows]

    def get_bars(self, symbol: str, start: date, end: date, adjustment: str = "none") -> list[MarketBar]:
        if end < start:
            raise ValueError("End date precedes start date")
        symbol = validate_symbol(symbol, allow_index=True)
        gaps = [(start, end)]
        for covered_start, covered_end in self.coverage(symbol, adjustment):
            updated = []
            for gap_start, gap_end in gaps:
                if covered_end < gap_start or covered_start > gap_end:
                    updated.append((gap_start, gap_end))
                else:
                    if gap_start < covered_start:
                        updated.append((gap_start, covered_start - timedelta(days=1)))
                    if covered_end < gap_end:
                        updated.append((covered_end + timedelta(days=1), gap_end))
            gaps = updated
        for gap_start, gap_end in gaps:
            bars = self.upstream.get_bars(symbol, gap_start, gap_end, adjustment)
            validate_bars(bars, symbol, adjustment)
            with self.connection:
                for bar in bars:
                    self.connection.execute("INSERT OR REPLACE INTO bars VALUES(?,?,?,?,?)",
                        (symbol, "daily", adjustment, bar.day.isoformat(), json.dumps({
                            "symbol": bar.symbol, "timestamp": bar.timestamp.isoformat(), "open": bar.open,
                            "high": bar.high, "low": bar.low, "close": bar.close, "volume": bar.volume,
                            "turnover": bar.turnover, "adjustment": bar.adjustment})))
                self.connection.execute("INSERT OR REPLACE INTO coverage VALUES(?,?,?,?,?,?,?)",
                    (symbol, "daily", adjustment, gap_start.isoformat(), gap_end.isoformat(),
                     self.upstream.name, datetime.now(SHANGHAI).isoformat()))
        rows = self.connection.execute("SELECT payload FROM bars WHERE symbol=? AND frequency='daily' AND adjustment=? AND day BETWEEN ? AND ? ORDER BY day",
            (symbol, adjustment, start.isoformat(), end.isoformat())).fetchall()
        result = [MarketBar(**{**(data := json.loads(row[0])), "timestamp": datetime.fromisoformat(data["timestamp"])}) for row in rows]
        validate_bars(result, symbol, adjustment)
        return result

    def close(self) -> None:
        self.connection.close()
