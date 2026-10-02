"""Opt-in read-only public feed smoke for the frozen Windows distribution."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import date, timedelta

from src.backtest.engine import BacktestEngine
from src.backtest.models import BacktestConfig
from src.backtest.reporting import BacktestRunStore
from src.market.historical import HistoricalCache, TencentHistoricalMarketDataProvider
from src.market.provider import INDEX_SYMBOLS
from src.market.tencent import TencentMarketDataProvider

LOG = logging.getLogger(__name__)


def run_network_smoke(config, paths) -> None:
    """No brokerage adapter, credentials, account access or live orders."""
    quote_provider = TencentMarketDataProvider()
    quote_provider.connect()
    try:
        requested = tuple(dict.fromkeys((*INDEX_SYMBOLS, *config.watchlist[:2])))
        quotes = quote_provider.get_quotes(requested)
        if set(quotes) != set(requested):
            raise AssertionError("Public quote batch incomplete")
        for symbol, quote in quotes.items():
            LOG.info("Public read-only quote %s: source=%s timestamp=%s delayed=%s",
                     symbol, quote.source, quote.timestamp.isoformat(), quote.is_delayed)
    finally:
        quote_provider.disconnect()

    start, end = date(2026, 9, 1), date(2026, 9, 25)
    symbol = config.watchlist[0]
    historical = HistoricalCache(paths.history_database_path,
                                 TencentHistoricalMarketDataProvider())
    try:
        smoke_config = replace(config, short_window=2, long_window=3, breakout_window=2)
        result = BacktestEngine(historical, smoke_config).run(
            BacktestConfig((symbol,), start, end, frequency="daily", adjustment="none",
                           benchmark="sh000300", security_profiles={symbol: "main_normal"}))
        if not result.equity_curve:
            raise AssertionError("Real historical backtest has no equity curve")
        LOG.info("Read-only historical backtest: run_id=%s sessions=%s data_hash=%s",
                 result.run_id, len(result.equity_curve), result.data_hash)
        coverage = historical.coverage(symbol, "none")
        if not coverage:
            raise AssertionError("Historical cache coverage missing")
    finally:
        historical.close()

    # Reopen the SQLite cache and load the already covered range without a download.
    reopened = HistoricalCache(paths.history_database_path,
                               TencentHistoricalMarketDataProvider())
    try:
        loaded = reopened.get_bars(symbol, start - timedelta(days=24), end)
        if not loaded:
            raise AssertionError("Historical cache did not survive reopen")
        LOG.info("Historical cache reopened: %s bars", len(loaded))
    finally:
        reopened.close()
    store = BacktestRunStore(paths.backtests_path, paths=paths)
    try:
        store.save(result)
        LOG.info("Backtest result persisted: %s total run records", store.count())
    finally:
        store.close()
