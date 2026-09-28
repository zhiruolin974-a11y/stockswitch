from dataclasses import replace
from datetime import datetime, timedelta

from src.app.config import load_config
from src.market.calendar import SHANGHAI
from src.market.models import MarketQuote
from src.market.provider import INDEX_SYMBOLS


OPEN = datetime(2026, 9, 28, 10, 0, tzinfo=SHANGHAI)


def config(**changes):
    return replace(load_config(), **changes)


def quote(symbol="sz000001", price=10.0, at=OPEN, volume=1000.0):
    return MarketQuote(symbol, symbol, at, at, price, price, price, price, 9.5,
                       volume, volume * price, price - 9.5, (price / 9.5 - 1) * 100,
                       "FakeMarketDataProvider", False)


def frame(price=10.0, at=OPEN, volume=1000.0):
    return {symbol: quote(symbol, price, at, volume) for symbol in ("sz000001", *INDEX_SYMBOLS)}
