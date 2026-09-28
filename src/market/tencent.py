from __future__ import annotations

import logging
import re
from datetime import datetime
from urllib.error import URLError
from urllib.request import Request, urlopen

from src.market.calendar import SHANGHAI
from src.market.models import MarketDataError, MarketQuote
from src.market.provider import MarketDataProvider


LOG = logging.getLogger(__name__)
STOCK_CODE = re.compile(r"(?:sh(?:600|601|603|605|688)\d{3}|sz(?:000|001|002|003|300|301)\d{3})\Z")
INDEX_CODE = re.compile(r"(?:sh000001|sz399001|sz399006|sh000300)\Z")
BARE_CODE = re.compile(r"\d{6}\Z")
LINE = re.compile(r'v_(sh\d{6}|sz\d{6})="([^"]*)";')


def validate_symbol(symbol: str, *, allow_index: bool = False) -> str:
    value = symbol.strip().lower()
    if allow_index and value == "000300":
        return "sh000300"
    if BARE_CODE.fullmatch(value):
        value = ("sh" if value.startswith(("600", "601", "603", "605", "688")) else "sz") + value
    if STOCK_CODE.fullmatch(value) or (allow_index and INDEX_CODE.fullmatch(value)):
        return value
    raise ValueError(f"Unsupported A-share symbol: {symbol}")


def parse_tencent_batch(raw: bytes, symbols: tuple[str, ...], received_at: datetime) -> dict[str, MarketQuote]:
    try:
        decoded = raw.decode("gb18030")
    except UnicodeDecodeError as exc:
        raise MarketDataError("Invalid market response encoding") from exc
    result: dict[str, MarketQuote] = {}
    for match in LINE.finditer(decoded):
        symbol = match.group(1)
        if symbol not in symbols:
            continue
        fields = match.group(2).split("~")
        if len(fields) < 38:
            raise MarketDataError(f"Incomplete quote for {symbol}")
        try:
            timestamp = datetime.strptime(fields[30], "%Y%m%d%H%M%S").replace(tzinfo=SHANGHAI)
            last = float(fields[3])
            previous = float(fields[4])
            quote = MarketQuote(
                symbol=symbol, name=fields[1], timestamp=timestamp, received_at=received_at,
                last_price=last, open=float(fields[5]), high=float(fields[33]), low=float(fields[34]),
                previous_close=previous, volume=float(fields[6]) * 100,
                turnover=float(fields[37]) * 10000, change=last - previous,
                change_percent=(last / previous - 1) * 100,
                source="Tencent Finance public quote", is_delayed=True,
            )
        except (ValueError, IndexError) as exc:
            raise MarketDataError(f"Invalid quote for {symbol}: {exc}") from exc
        result[symbol] = quote
    missing = set(symbols) - set(result)
    if missing:
        raise MarketDataError(f"Missing quotes: {', '.join(sorted(missing))}")
    return result


class TencentMarketDataProvider(MarketDataProvider):
    """Public, unauthenticated batch snapshots. Timeliness is unguaranteed."""

    def __init__(self, timeout: float = 8.0):
        self.timeout = timeout
        self._connected = False
        self._last_timestamps: dict[str, datetime] = {}

    def connect(self) -> None:
        self._connected = True
        LOG.info("Market provider connected: Tencent Finance public quote")

    def disconnect(self) -> None:
        self._connected = False
        LOG.info("Market provider disconnected")

    def health(self) -> bool:
        return self._connected

    def get_quote(self, symbol: str) -> MarketQuote:
        return self.get_quotes([symbol])[symbol]

    def get_quotes(self, symbols: list[str] | tuple[str, ...]) -> dict[str, MarketQuote]:
        if not self._connected:
            raise MarketDataError("Market provider is disconnected")
        requested = tuple(dict.fromkeys(validate_symbol(item, allow_index=True) for item in symbols))
        if not requested or len(requested) > 16:
            raise ValueError("Request 1 to 16 symbols per batch")
        url = "https://qt.gtimg.cn/q=" + ",".join(requested)
        try:
            request = Request(url, headers={"User-Agent": "StockSwitch/0.1 (personal research)"})
            with urlopen(request, timeout=self.timeout) as response:
                if response.status != 200:
                    raise MarketDataError(f"HTTP {response.status}")
                raw = response.read(100_001)
            if len(raw) > 100_000:
                raise MarketDataError("Oversized quote response")
            quotes = parse_tencent_batch(raw, requested, datetime.now(SHANGHAI))
            for symbol, quote in quotes.items():
                previous = self._last_timestamps.get(symbol)
                if previous and quote.timestamp < previous:
                    raise MarketDataError(f"Timestamp regressed for {symbol}")
            self._last_timestamps.update({symbol: quote.timestamp for symbol, quote in quotes.items()})
            return quotes
        except (OSError, URLError) as exc:
            LOG.warning("Market request failed: %s", exc)
            raise MarketDataError(f"Market request failed: {exc}") from exc
