from __future__ import annotations

import logging
import queue
import threading
import time
from datetime import datetime

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QTabWidget)

from src.market.calendar import SHANGHAI
from src.app.paths import AppPaths
from src.app.version import VERSION
from src.trading.engine import TradingEngine
from src.trading.models import OrderSide
from src.ui.backtest_tab import BacktestTab


LOG = logging.getLogger(__name__)


class MarketWorker(QThread):
    updated = Signal(object)
    failed = Signal(str)

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
                        self.engine.manual_paper_order(command[1], command[2], command[3], datetime.now(SHANGHAI))
                    elif action == "add":
                        self.engine.add_symbol(command[1])
                        next_poll = 0
                    elif action == "remove":
                        self.engine.remove_symbol(command[1])
                    self.updated.emit(self.snapshot())
                except Exception as exc:
                    self.failed.emit(str(exc))
        finally:
            self.engine.disconnect()
            self.updated.emit(self.snapshot())

    def snapshot(self) -> dict:
        portfolio = self.engine.portfolio
        return {
            "connected": self.engine.connected,
            "stale": self.engine.stale,
            "last_update": self.engine.last_update,
            "market_state": self.engine.rules.state(datetime.now(SHANGHAI)),
            "source": "Tencent Finance public quote" if self.engine.provider.__class__.__name__ != "FakeMarketDataProvider" else "FakeMarketDataProvider",
            "watchlist": list(self.engine.watchlist),
            "indexes": list(self.engine.latest_indexes.values()),
            "quotes": list(self.engine.latest_quotes.values()),
            "positions": [(p.symbol, p.quantity, p.available_quantity, p.average_cost, p.market_price, p.market_value, p.unrealized_pnl)
                          for p in portfolio.positions.values()],
            "cash": portfolio.available_cash,
            "market_value": portfolio.market_value,
            "equity": portfolio.total_equity,
            "realized": portfolio.realized_pnl,
            "unrealized": portfolio.unrealized_pnl,
            "daily": portfolio.daily_pnl,
            "events": list(self.engine.events[-30:]),
            "strategy": self.engine.config.strategy_enabled,
        }


class MainWindow(QMainWindow):
    def __init__(self, engine: TradingEngine, *, paths: AppPaths | None = None):
        super().__init__()
        self.engine = engine
        self.worker: MarketWorker | None = None
        self.setWindowTitle(f"StockSwitch {VERSION} — PAPER TRADING")
        self.resize(1050, 780)
        root = QWidget()
        tabs = QTabWidget()
        self.setCentralWidget(tabs)
        tabs.addTab(root, "Live Paper Trading")
        self.backtest_tab = BacktestTab(engine.config, paths=paths)
        tabs.addTab(self.backtest_tab, "Backtest")
        layout = QVBoxLayout(root)
        layout.addWidget(QLabel("StockSwitch    PAPER TRADING    LIVE MARKET DATA + PAPER TRADING"))
        self.status_label = QLabel("Disconnected | Data Source: Tencent Finance | Approximate Real-Time / Delayed")
        layout.addWidget(self.status_label)

        controls = QHBoxLayout()
        self.start_button = QPushButton("Start Monitoring")
        self.stop_button = QPushButton("Stop Monitoring")
        self.stop_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_monitoring)
        self.stop_button.clicked.connect(self.stop_monitoring)
        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)
        self.symbol_input = QLineEdit()
        self.symbol_input.setPlaceholderText("A-share code, e.g. 000001 or sz000001")
        controls.addWidget(self.symbol_input)
        add_button = QPushButton("Add")
        remove_button = QPushButton("Remove")
        add_button.clicked.connect(lambda: self.queue_command("add", self.symbol_input.text()))
        remove_button.clicked.connect(lambda: self.queue_command("remove", self.symbol_input.text().strip().lower()))
        controls.addWidget(add_button)
        controls.addWidget(remove_button)
        layout.addLayout(controls)

        self.index_table = self._table(["Index", "Value", "Change", "Change %", "Updated"])
        self.quote_table = self._table(["Code", "Name", "Last", "Change %", "Volume (shares)", "Updated", "Data"])
        self.position_table = self._table(["Code", "Qty", "Available T+1", "Avg Cost", "Market Price", "Value", "Unrealized PnL"])
        self.signal_table = self._table(["Signal / Paper Order / Risk Result"])
        for title, table in (("Market Indices", self.index_table), ("Watchlist", self.quote_table),
                             ("SIMULATED / PAPER Positions", self.position_table), ("Signals and Risk Decisions", self.signal_table)):
            layout.addWidget(QLabel(title))
            layout.addWidget(table)

        paper_controls = QHBoxLayout()
        self.paper_symbol = QComboBox()
        self.paper_symbol.addItems(engine.watchlist)
        self.quantity = QSpinBox()
        self.quantity.setRange(100, 100000)
        self.quantity.setSingleStep(engine.config.lot_size)
        self.quantity.setValue(engine.config.lot_size)
        buy = QPushButton("SIMULATED / PAPER Buy")
        sell = QPushButton("SIMULATED / PAPER Sell")
        buy.clicked.connect(lambda: self.queue_command("paper", self.paper_symbol.currentText(), OrderSide.BUY, self.quantity.value()))
        sell.clicked.connect(lambda: self.queue_command("paper", self.paper_symbol.currentText(), OrderSide.SELL, self.quantity.value()))
        for widget in (self.paper_symbol, self.quantity, buy, sell):
            paper_controls.addWidget(widget)
        layout.addLayout(paper_controls)
        self.account_label = QLabel("Cash 100000 | Market Value 0 | Total Equity 100000 | Realized 0 | Unrealized 0 | Daily 0")
        layout.addWidget(self.account_label)
        self.statusBar().showMessage("Paper Trading | Strategy Enabled" if engine.config.strategy_enabled else "Paper Trading | Strategy Disabled")

    @staticmethod
    def _table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setStretchLastSection(True)
        return table

    def start_monitoring(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        self.worker = MarketWorker(self.engine)
        self.worker.updated.connect(self.render_snapshot)
        self.worker.failed.connect(self.show_error)
        self.worker.start()
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)

    def stop_monitoring(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.stop_requested.set()
            self.worker.wait(10000)
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def queue_command(self, *command) -> None:
        if not self.worker or not self.worker.isRunning():
            self.show_error("Start Monitoring first")
            return
        self.worker.commands.put(command)

    def show_error(self, message: str) -> None:
        self.statusBar().showMessage(f"Disconnected / Data Stale: {message}", 10000)
        LOG.warning("GUI market/command error: %s", message)

    @staticmethod
    def _fill_table(table: QTableWidget, rows: list[list[str]]) -> None:
        table.setRowCount(len(rows))
        for row_number, row in enumerate(rows):
            for column, value in enumerate(row):
                table.setItem(row_number, column, QTableWidgetItem(str(value)))

    def render_snapshot(self, state: dict) -> None:
        updated = state["last_update"].strftime("%Y-%m-%d %H:%M:%S") if state["last_update"] else "Never"
        condition = ("Connected / Data Stale" if state["connected"] and state["stale"] else
                     "Connected" if state["connected"] else "Disconnected / Data Stale")
        self.status_label.setText(f"{condition} | Data Source: {state['source']} | Last Update: {updated} | "
                                  f"{state['market_state']} | Approximate Real-Time / Delayed | PAPER TRADING | "
                                  f"Strategy {'Enabled' if state['strategy'] else 'Disabled'}")
        self.statusBar().showMessage(self.status_label.text())
        stale = "STALE" if state["stale"] else "Approximate / Delayed"
        self._fill_table(self.index_table, [[q.name, f"{q.last_price:.2f}", f"{q.change:+.2f}",
                         f"{q.change_percent:+.2f}%", q.timestamp.strftime("%H:%M:%S")]
                         for q in state["indexes"]])
        self._fill_table(self.quote_table, [[q.symbol, q.name, f"{q.last_price:.2f}", f"{q.change_percent:+.2f}%",
                         f"{q.volume:.0f}", q.timestamp.strftime("%H:%M:%S"), stale] for q in state["quotes"]])
        self._fill_table(self.position_table, [[symbol, qty, available, f"{cost:.2f}", f"{price:.2f}",
                         f"{value:.2f}", f"{pnl:+.2f}"] for symbol, qty, available, cost, price, value, pnl in state["positions"]])
        self._fill_table(self.signal_table, [[event] for event in reversed(state["events"])])
        self.paper_symbol.clear()
        self.paper_symbol.addItems(state["watchlist"])
        self.account_label.setText(f"Cash {state['cash']:.2f} | Market Value {state['market_value']:.2f} | "
                                   f"Total Equity {state['equity']:.2f} | Realized PnL {state['realized']:+.2f} | "
                                   f"Unrealized PnL {state['unrealized']:+.2f} | Daily PnL {state['daily']:+.2f}")

    def closeEvent(self, event) -> None:
        self.backtest_tab.stop()
        self.stop_monitoring()
        self.engine.journal.close()
        LOG.info("Application closed")
        super().closeEvent(event)
