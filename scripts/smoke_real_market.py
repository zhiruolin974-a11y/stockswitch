"""Read-only public market smoke; never creates an order or broker."""

from datetime import datetime
from time import monotonic

from src.market.calendar import ChinaAMarketRules, SHANGHAI
from src.market.provider import INDEX_SYMBOLS
from src.market.tencent import TencentMarketDataProvider


def main() -> int:
    symbols = (*INDEX_SYMBOLS, "sh600519", "sz000001")
    provider = TencentMarketDataProvider()
    provider.connect()
    started = monotonic()
    try:
        quotes = provider.get_quotes(symbols)
    finally:
        provider.disconnect()
    duration = monotonic() - started
    print("Market state:", ChinaAMarketRules().state(datetime.now(SHANGHAI)))
    print(f"Read-only batch transport duration: {duration:.3f}s (not exchange quote latency)")
    for quote in quotes.values():
        print(f"{quote.symbol} {quote.name}: {quote.last_price:.2f}; source={quote.source}; "
              f"remote={quote.timestamp.isoformat()}; received_at={quote.received_at.isoformat()}; "
              f"is_delayed={quote.is_delayed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
