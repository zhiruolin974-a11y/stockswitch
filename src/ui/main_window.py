from __future__ import annotations

import logging
import queue
import threading
import time
from datetime import datetime

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget

from src.app.paths import AppPaths
from src.app.version import VERSION
from src.market.calendar import SHANGHAI
from src.trading.engine import TradingEngine
from src.ui.backtest_tab import BacktestTab
from src.ui.dashboard_tab import DashboardTab
from src.ui.i18n import install_qt_chinese, tr, user_error
from src.ui.paper_tab import PaperTab
from src.ui.records_tab import RecordsTab
from src.ui.settings_tab import SettingsTab


LOG = logging.getLogger(__name__)


class MarketWorker(QThread):
    """Owns live data and simulated orders; Qt widgets only receive snapshots."""

    updated = Signal(object)
    failed = Signal(str)
    order_completed = Signal(object)

    def __init__(self, engine: TradingEngine):
        super().__init__()
        self.engine = engine
        self.stop_requested = threading.Event()
        self.commands: queue.Queue[tuple] = queue.Queue()

    def run(self) -> None:
        try:
            self.engine.connect()
            self.updated.emit(self.snapshot())
            next_poll = 0.0
            while not self.stop_requested.is_set():
                now = datetime.now(SHANGHAI)
                if time.monotonic() >= next_poll:
                    try:
                        self.engine.poll(now)
                    except Exception as exc:
                        self.failed.emit(str(exc))
                    self.updated.emit(self.snapshot())
                    interval = (self.engine.config.market_refresh_seconds if self.engine.rules.can_trade(now)
                                else self.engine.config.closed_refresh_seconds)
                    next_poll = time.monotonic() + interval
                try:
                    command = self.commands.get(timeout=0.2)
                except queue.Empty:
                    continue
                try:
                    action = command[0]
                    if action == "paper":
                        order, decision = self.engine.manual_paper_order(
                            command[1], command[2], command[3], datetime.now(SHANGHAI))
                        fill = next((item for item in reversed(self.engine.broker.fills)
                                     if item.order_id == order.id), None)
                        trade = next((item for item in reversed(self.engine.broker.trades)
                                      if item.order_id == order.id), None)
                        quote = self.engine.latest_quotes.get(order.symbol)
                        self.order_completed.emit({
                            "order": order, "decision": decision, "fill": fill, "trade": trade,
                            "cash": self.engine.portfolio.available_cash,
                            "name": quote.name if quote else order.symbol,
                        })
                    elif action == "add":
                        self.engine.add_symbol(command[1])
                        next_poll = 0.0
                    elif action == "remove":
                        from src.market.tencent import validate_symbol
                        self.engine.remove_symbol(validate_symbol(command[1]))
                        next_poll = 0.0
                    elif action == "strategy":
                        self.engine.set_strategy_enabled(command[1])
                    self.updated.emit(self.snapshot())
                except Exception as exc:
                    self.failed.emit(str(exc))
        except Exception as exc:
            LOG.exception("Market worker could not start")
            self.failed.emit(str(exc))
        finally:
            self.stop_requested.set()
            try:
                self.engine.disconnect()
            except Exception:
                LOG.exception("Market provider disconnect failed")
            self.updated.emit(self.snapshot())

    def snapshot(self) -> dict:
        portfolio = self.engine.portfolio
        quotes = list(self.engine.latest_quotes.values())
        indexes = list(self.engine.latest_indexes.values())
        source = (quotes[0].source if quotes else indexes[0].source if indexes
                  else self.engine.provider.__class__.__name__)
        positions = []
        for position in portfolio.positions.values():
            quote = self.engine.latest_quotes.get(position.symbol)
            positions.append({
                "symbol": position.symbol,
                "name": quote.name if quote else position.symbol,
                "quantity": position.quantity,
                "available_quantity": position.available_quantity,
                "average_cost": position.average_cost,
                "market_price": position.market_price,
                "market_value": position.market_value,
                "unrealized_pnl": position.unrealized_pnl,
            })
        return {
            "connected": self.engine.connected,
            "stale": self.engine.stale,
            "last_update": self.engine.last_update,
            "market_state": self.engine.rules.state(datetime.now(SHANGHAI)),
            "source": source,
            "delayed": any(quote.is_delayed for quote in (*indexes, *quotes)),
            "monitoring": not self.stop_requested.is_set(),
            "watchlist": list(self.engine.watchlist),
            "indexes": indexes,
            "quotes": quotes,
            "positions": positions,
            "initial_cash": portfolio.initial_cash,
            "day_start_equity": portfolio.day_start_equity,
            "cash": portfolio.available_cash,
            "market_value": portfolio.market_value,
            "equity": portfolio.total_equity,
            "realized": portfolio.realized_pnl,
            "unrealized": portfolio.unrealized_pnl,
            "daily": portfolio.daily_pnl,
            "events": list(self.engine.events[-30:]),
            "event_records": list(self.engine.event_records[-30:]),
            "trade_records": self.engine.journal.list_recent_trades(limit=200),
            "strategy": self.engine.strategy_enabled,
        }


class MainWindow(QMainWindow):
    def __init__(self, engine: TradingEngine, *, paths: AppPaths | None = None):
        super().__init__()
        install_qt_chinese(QApplication.instance())
        self.engine = engine
        # Desktop automatic simulation requires the user's explicit startup
        # confirmation. The engine's strategy and risk calculations are intact.
        self.engine.set_strategy_enabled(False)
        self.paths = paths or AppPaths.for_runtime()
        self.worker: MarketWorker | None = None
        self.setWindowTitle(f"StockSwitch - A股模拟交易与量化研究  {VERSION}")
        self.resize(1180, 820)
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.dashboard_tab = DashboardTab(engine.config)
        self.paper_tab = PaperTab(engine.config, paths=self.paths)
        self.backtest_tab = BacktestTab(engine.config, paths=self.paths)
        self.records_tab = RecordsTab()
        self.settings_tab = SettingsTab(engine.config, paths=self.paths)
        for widget, title in (
            (self.dashboard_tab, tr("nav.overview")),
            (self.paper_tab, tr("nav.paper")),
            (self.backtest_tab, tr("nav.backtest")),
            (self.records_tab, tr("nav.records")),
            (self.settings_tab, tr("nav.settings")),
        ):
            self.tabs.addTab(widget, title)

        self.index_table = self.dashboard_tab.index_table
        self.quote_table = self.dashboard_tab.quote_table
        self.status_label = self.dashboard_tab.status_label
        self.start_button = self.dashboard_tab.start_button
        self.stop_button = self.dashboard_tab.stop_button
        self.dashboard_tab.start_requested.connect(self.start_monitoring)
        self.dashboard_tab.stop_requested.connect(self.stop_monitoring)
        self.dashboard_tab.add_symbol_requested.connect(lambda symbol: self.queue_command("add", symbol))
        self.dashboard_tab.remove_symbol_requested.connect(lambda symbol: self.queue_command("remove", symbol))
        self.paper_tab.order_requested.connect(
            lambda symbol, side, quantity: self.queue_command("paper", symbol, side, quantity))
        self.paper_tab.auto_toggle_requested.connect(
            lambda enabled: self.queue_command("strategy", enabled))
        self.paper_tab.quote_requested.connect(lambda symbol: self.queue_command("add", symbol))
        self.backtest_tab.result_ready.connect(self.records_tab.set_backtest_result)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.statusBar().showMessage("仅模拟交易 · 不连接券商或真实账户")
        self.setStyleSheet("""
            QMainWindow, QTabWidget::pane { background: #f5f7fa; color: #1d2939; }
            QTabBar::tab { padding: 10px 20px; color: #475467; background: #e9edf2; }
            QTabBar::tab:selected { color: #17365d; background: #ffffff; border-top: 2px solid #376c9f; }
            QTableWidget { background: #ffffff; alternate-background-color: #f8fafc;
                           border: 1px solid #dce3ea; gridline-color: #edf1f5; }
            QPushButton { padding: 6px 12px; }
            QGroupBox { font-weight: 600; border: 1px solid #dce3ea;
                        border-radius: 4px; margin-top: 10px; padding-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
        """)

    def _on_tab_changed(self, index: int) -> None:
        if index == 1:
            self.paper_tab.show_first_use_notice()

    def start_monitoring(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        self.worker = MarketWorker(self.engine)
        self.worker.updated.connect(self.render_snapshot)
        self.worker.failed.connect(self.show_error)
        self.worker.order_completed.connect(self.paper_tab.show_order_result)
        self.worker.start()
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.statusBar().showMessage("正在连接行情…")

    def stop_monitoring(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.stop_requested.set()
            if not self.worker.wait(10000):
                LOG.warning("Market worker did not stop within 10 seconds")
                self.statusBar().showMessage("行情线程尚未停止，请稍后再试")
                return
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.statusBar().showMessage("行情监控已停止；模拟交易不可用")

    def queue_command(self, *command) -> None:
        if not self.worker or not self.worker.isRunning():
            self.show_error("Start Monitoring first")
            return
        self.worker.commands.put(command)

    def show_error(self, message: str) -> None:
        LOG.warning("GUI market/command error: %s", message)
        self.statusBar().showMessage(user_error(message), 10000)
        self.paper_tab.show_command_error(user_error(message))

    def render_snapshot(self, state: dict) -> None:
        self.dashboard_tab.render_snapshot(state)
        self.paper_tab.render_snapshot(state)
        self.records_tab.set_paper_records(state["trade_records"])
        self.statusBar().showMessage(self.status_label.text())

    def closeEvent(self, event) -> None:
        self.backtest_tab.stop()
        self.stop_monitoring()
        if ((self.worker and self.worker.isRunning()) or
                (self.backtest_tab.worker and self.backtest_tab.worker.isRunning())):
            self.statusBar().showMessage("后台任务正在停止，请稍后关闭窗口。")
            event.ignore()
            return
        self.engine.journal.close()
        LOG.info("Application closed")
        super().closeEvent(event)
