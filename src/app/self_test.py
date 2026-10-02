"""Opt-in, offline end-to-end smoke executed by the packaged EXE itself."""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QDate, QTimer

from src.app.paths import is_frozen, resource_path
from src.market.calendar import SHANGHAI
from src.market.fake import FakeMarketDataProvider
from src.market.models import MarketQuote
from src.market.provider import INDEX_SYMBOLS
from src.trading.models import OrderSide, OrderStatus

LOG = logging.getLogger(__name__)
AT = datetime(2026, 9, 28, 10, 0, tzinfo=SHANGHAI)


def fake_provider() -> FakeMarketDataProvider:
    def frame(price: float, at: datetime) -> dict[str, MarketQuote]:
        def quote(symbol: str) -> MarketQuote:
            return MarketQuote(symbol, symbol, at, at, price, price, price, price, 9.5,
                               1000, price * 1000, price - 9.5,
                               (price / 9.5 - 1) * 100, "FakeMarketDataProvider", False)
        return {symbol: quote(symbol) for symbol in ("sz000001", *INDEX_SYMBOLS)}
    return FakeMarketDataProvider([frame(10, AT), frame(12, AT + timedelta(days=1))])


def run_self_test(app, window, engine, paths, outcome: dict[str, bool]) -> None:
    """Exercise GUI, fake paper risk/journal, backtest chart and export; then exit."""
    tab = window.backtest_tab

    def fail(reason: str) -> None:
        LOG.error("Packaged EXE self-test failed: %s", reason)
        outcome["ok"] = False
        window.close()
        app.quit()

    def completed(result) -> None:
        try:
            if len(tab.chart.points) < 100 or tab.trades.rowCount() < 1:
                raise AssertionError("Backtest chart or trade history missing")
            tab.export_button.click()
            if not tab.message.text().startswith("Exported to "):
                raise AssertionError("Backtest export action failed")
            target = paths.exports_dir / "backtests" / result.run_id
            if not all((target / name).exists() for name in ("summary.json", "trades.csv", "equity_curve.csv")):
                raise AssertionError("Backtest export missing")
            LOG.info("Packaged EXE self-test passed: fake paper buy/sell, journal, backtest, chart, export")
            outcome["ok"] = True
            window.close()
            app.quit()
        except Exception as exc:
            LOG.exception("Packaged EXE self-test exception")
            fail(str(exc))

    def begin() -> None:
        try:
            if not is_frozen():
                raise AssertionError("Self-test requires frozen runtime")
            if paths.app_data_dir == Path(sys.executable).parent or not paths.config_path.exists():
                raise AssertionError("AppPaths/config initialization failed")
            if not paths.database_path.exists() or not resource_path("assets/StockSwitch.ico").exists():
                raise AssertionError("SQLite/resource initialization failed")
            if not window.isVisible() or window.centralWidget().count() != 2:
                raise AssertionError("MainWindow or Phase 1/2 tabs missing")
            prior_trades = engine.journal.count("trades")
            engine.connect()
            engine.poll(AT)
            buy, decision = engine.manual_paper_order("sz000001", OrderSide.BUY, 100, AT)
            if not decision.accepted or buy.status != OrderStatus.FILLED:
                raise AssertionError("Fake paper buy failed")
            engine.provider.advance()
            next_day = AT + timedelta(days=1)
            engine.poll(next_day)
            sell, decision = engine.manual_paper_order("sz000001", OrderSide.SELL, 100, next_day)
            if not decision.accepted or sell.status != OrderStatus.FILLED:
                raise AssertionError("Fake paper sell failed")
            if engine.journal.count("trades") != prior_trades + 2:
                raise AssertionError("SQLite journal missing trades")
            tab.source.setCurrentText("Fake (offline smoke)")
            tab.security_profile.setCurrentText("main_normal")
            tab.start_date.setDate(QDate(2025, 1, 2))
            tab.end_date.setDate(QDate(2025, 9, 1))
            tab.run_button.click()
            if tab.worker is None:
                raise AssertionError("Backtest worker did not start")
            tab.worker.completed.connect(completed)
            tab.worker.failed.connect(fail)
            tab.worker.cancelled.connect(lambda: fail("Backtest cancelled"))
        except Exception as exc:
            LOG.exception("Packaged EXE self-test exception")
            fail(str(exc))

    QTimer.singleShot(0, begin)
    QTimer.singleShot(20000, lambda: fail("Self-test timeout") if not outcome.get("ok") else None)
