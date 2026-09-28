from __future__ import annotations

import threading
from datetime import date, datetime, time, timedelta
from pathlib import Path

from PySide6.QtCore import QDate, QThread, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QDateEdit, QDoubleSpinBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget)

from src.app.config import AppConfig, ROOT
from src.backtest.engine import BacktestCancelled, BacktestEngine
from src.backtest.models import BacktestConfig, BacktestResult, EquityPoint
from src.backtest.reporting import BacktestRunStore, export_result
from src.market.calendar import SHANGHAI
from src.market.historical import (FakeHistoricalMarketDataProvider, HistoricalCache, MarketBar,
                                   TencentHistoricalMarketDataProvider)
from src.market.tencent import validate_symbol


def fake_daily_provider(symbols: tuple[str, ...], start: date, end: date,
                        adjustment: str = "none") -> FakeHistoricalMarketDataProvider:
    data: dict[str, list[MarketBar]] = {}
    day = start
    for offset, symbol in enumerate(symbols):
        bars = []
        session = 0
        previous = 10.0 + offset * 2
        while day <= end:
            if day.weekday() < 5:
                slope = 0.08 if (session // 70) % 2 == 0 else -0.07
                close = max(1, round(previous + slope, 3))
                opened = previous
                bars.append(MarketBar(symbol, datetime.combine(day, time(15), SHANGHAI),
                                      opened, max(opened, close) + 0.03,
                                      min(opened, close) - 0.03, close,
                                      1_000_000 + session * 1000, close * 1_000_000, adjustment))
                previous = close
                session += 1
            day += timedelta(days=1)
        data[symbol] = bars
        day = start
    return FakeHistoricalMarketDataProvider(data)


class EquityChart(QWidget):
    def __init__(self):
        super().__init__()
        self.points: list[EquityPoint] = []
        self.setMinimumHeight(220)

    def set_points(self, points: list[EquityPoint]) -> None:
        self.points = points
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#ffffff"))
        painter.setPen(QColor("#333333"))
        painter.drawText(10, 16, "Equity (blue) / Benchmark (orange) / Drawdown (red)")
        if len(self.points) < 2:
            painter.drawText(10, 65, "Run a backtest to see the curve")
            painter.end()
            return
        left, right = 30, max(31, self.width() - 15)
        top, bottom = 27, max(60, self.height() - 77)
        values = [v for p in self.points for v in (p.total_equity, p.benchmark_equity)]
        low, high = min(values), max(values)
        if high == low:
            high += 1
        def x(i): return left + (right - left) * i / (len(self.points) - 1)
        def y(value): return bottom - (bottom - top) * (value - low) / (high - low)
        for attr, color in (("total_equity", "#2166ac"), ("benchmark_equity", "#e08214")):
            painter.setPen(QPen(QColor(color), 2))
            for i in range(1, len(self.points)):
                painter.drawLine(int(x(i - 1)), int(y(getattr(self.points[i - 1], attr))),
                                 int(x(i)), int(y(getattr(self.points[i], attr))))
        painter.setPen(QPen(QColor("#b2182b"), 2))
        drawdown_top, drawdown_bottom = bottom + 18, self.height() - 8
        worst = min(p.drawdown for p in self.points)
        for i in range(1, len(self.points)):
            def dy(point):
                return drawdown_top if worst == 0 else drawdown_top + (drawdown_bottom - drawdown_top) * point.drawdown / worst
            painter.drawLine(int(x(i - 1)), int(dy(self.points[i - 1])),
                             int(x(i)), int(dy(self.points[i])))
        painter.end()


class BacktestWorker(QThread):
    progress_changed = Signal(int, str)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, app_config: AppConfig, config: BacktestConfig, source: str):
        super().__init__()
        self.app_config = app_config
        self.config = config
        self.source = source
        self.cancel_requested = threading.Event()

    def run(self) -> None:
        cache = None
        try:
            if self.source == "Fake (offline smoke)":
                warm_start = self.config.start_date - timedelta(days=220)
                provider = fake_daily_provider(tuple(dict.fromkeys((*self.config.symbols, self.config.benchmark))),
                                               warm_start, self.config.end_date, self.config.adjustment)
            else:
                cache = HistoricalCache(ROOT / "data" / "history" / "daily.sqlite",
                                        TencentHistoricalMarketDataProvider())
                provider = cache
            result = BacktestEngine(provider, self.app_config).run(
                self.config, self.cancel_requested, lambda n, stage: self.progress_changed.emit(n, stage))
            if self.cancel_requested.is_set():
                raise BacktestCancelled()
            store = BacktestRunStore(ROOT / "data" / "backtests.db")
            try:
                store.save(result)
            finally:
                store.close()
            self.completed.emit(result)
        except BacktestCancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            if cache:
                cache.close()


class BacktestTab(QWidget):
    def __init__(self, app_config: AppConfig):
        super().__init__()
        self.app_config = app_config
        self.worker: BacktestWorker | None = None
        self.result: BacktestResult | None = None
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.symbols_input = QLineEdit("sz000001")
        self.start_date = QDateEdit(QDate.currentDate().addMonths(-9))
        self.end_date = QDateEdit(QDate.currentDate().addDays(-1))
        for widget in (self.start_date, self.end_date):
            widget.setCalendarPopup(True)
            widget.setDisplayFormat("yyyy-MM-dd")
        self.frequency = QComboBox()
        self.frequency.addItem("daily")
        self.initial_cash = QDoubleSpinBox()
        self.initial_cash.setRange(1000, 1_000_000_000)
        self.initial_cash.setValue(app_config.initial_cash)
        self.strategy_name = QLabel("TrendBreakoutStrategy")
        self.benchmark = QLineEdit(app_config.backtest_benchmark)
        self.source = QComboBox()
        self.source.addItems(["Tencent historical (cached)", "Fake (offline smoke)"])
        self.security_profile = QComboBox()
        self.security_profile.addItems(["unknown", "main_normal", "main_st", "chinext", "star"])
        self.security_profile.setCurrentText(app_config.backtest_security_profile)
        self.profile_overrides = QLineEdit()
        self.profile_overrides.setPlaceholderText("Optional: sz000001=main_normal,sz300750=chinext")
        self.output_path = QLineEdit(str(ROOT / "exports" / "backtests"))
        for label, widget in (("Symbols (comma separated)", self.symbols_input), ("Start Date", self.start_date),
                              ("End Date", self.end_date), ("Frequency", self.frequency),
                              ("Initial Cash", self.initial_cash), ("Strategy", self.strategy_name),
                              ("Benchmark", self.benchmark), ("History Provider", self.source),
                              ("Verified Security Profile", self.security_profile),
                              ("Per-Symbol Profiles", self.profile_overrides), ("Export Folder", self.output_path)):
            form.addRow(label, widget)
        layout.addLayout(form)
        controls = QHBoxLayout()
        self.run_button = QPushButton("Run Backtest")
        self.cancel_button = QPushButton("Cancel Backtest")
        self.cancel_button.setEnabled(False)
        self.export_button = QPushButton("Export CSV / JSON")
        self.export_button.setEnabled(False)
        self.run_button.clicked.connect(self.start_run)
        self.cancel_button.clicked.connect(self.cancel_run)
        self.export_button.clicked.connect(self.export)
        for button in (self.run_button, self.cancel_button, self.export_button):
            controls.addWidget(button)
        layout.addLayout(controls)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.message = QLabel("Research backtest only. Unknown security profile blocks fills.")
        layout.addWidget(self.message)
        self.summary = QLabel("No backtest result")
        layout.addWidget(self.summary)
        self.chart = EquityChart()
        layout.addWidget(self.chart)
        layout.addWidget(QLabel("SIMULATED Trade History"))
        self.trades = QTableWidget(0, 6)
        self.trades.setHorizontalHeaderLabels(["Symbol", "Side", "Time", "Price", "Quantity", "Fees / PnL"])
        layout.addWidget(self.trades)

    def start_run(self) -> None:
        try:
            symbols = tuple(dict.fromkeys(validate_symbol(part.strip()) for part in self.symbols_input.text().split(",") if part.strip()))
            start = date.fromisoformat(self.start_date.date().toString("yyyy-MM-dd"))
            end = date.fromisoformat(self.end_date.date().toString("yyyy-MM-dd"))
            profile = self.security_profile.currentText()
            profiles = {symbol: profile for symbol in symbols}
            if self.profile_overrides.text().strip():
                for item in self.profile_overrides.text().split(","):
                    symbol_text, selected = item.strip().split("=", 1)
                    symbol = validate_symbol(symbol_text)
                    if symbol not in symbols or selected not in ("unknown", "main_normal", "main_st", "chinext", "star"):
                        raise ValueError(f"Invalid security profile override: {item}")
                    profiles[symbol] = selected
            config = BacktestConfig(symbols, start, end, self.initial_cash.value(), self.frequency.currentText(),
                                    "none", validate_symbol(self.benchmark.text(), allow_index=True),
                                    self.app_config.backtest_risk_free_rate,
                                    self.app_config.backtest_annualization_factor,
                                    profiles)
        except (ValueError, TypeError) as exc:
            self.message.setText(f"Invalid backtest input: {exc}")
            return
        self.worker = BacktestWorker(self.app_config, config, self.source.currentText())
        self.worker.progress_changed.connect(self.on_progress)
        self.worker.completed.connect(self.on_result)
        self.worker.failed.connect(self.on_failed)
        self.worker.cancelled.connect(self.on_cancelled)
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.export_button.setEnabled(False)
        self.progress.setValue(0)
        self.message.setText("Loading historical data...")
        self.worker.start()

    def cancel_run(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel_requested.set()
            self.message.setText("Cancellation requested...")

    def on_progress(self, value: int, stage: str) -> None:
        self.progress.setValue(value)
        self.message.setText(stage)

    def _finished(self) -> None:
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

    def on_failed(self, message: str) -> None:
        self._finished()
        self.message.setText(f"Backtest failed: {message}")

    def on_cancelled(self) -> None:
        self._finished()
        self.message.setText("Backtest cancelled; no official result saved")

    def on_result(self, result: BacktestResult) -> None:
        self._finished()
        self.result = result
        self.export_button.setEnabled(True)
        self.progress.setValue(100)
        self.message.setText(f"Completed {result.run_id}; {result.provider}; {result.config.adjustment} adjustment")
        p = result.performance
        def metric(value, percent=False):
            return "N/A" if value is None else f"{value:.2%}" if percent else f"{value:.2f}"
        self.summary.setText(
            f"Total Return {metric(p['total_return'], True)} | Annualized {metric(p['annualized_return'], True)} | "
            f"Max Drawdown {metric(p['max_drawdown'], True)} | Sharpe {metric(p['sharpe'])} | "
            f"Win Rate {metric(p['win_rate'], True)} | Trade Count {p['total_trades']} | "
            f"Final Equity {metric(p['final_equity'])} | Benchmark {metric(p['benchmark_return'], True)}")
        self.chart.set_points(result.equity_curve)
        self.trades.setRowCount(len(result.trades))
        for i, trade in enumerate(result.trades):
            values = [trade.symbol, trade.side.value, trade.timestamp.isoformat(), f"{trade.price:.4f}",
                      str(trade.quantity), f"{trade.fees:.2f} / {trade.realized_pnl:+.2f}"]
            for j, value in enumerate(values):
                self.trades.setItem(i, j, QTableWidgetItem(value))

    def export(self) -> None:
        if self.result is None:
            return
        try:
            target = export_result(self.result, Path(self.output_path.text()) / self.result.run_id)
            self.message.setText(f"Exported to {target}")
        except Exception as exc:
            self.message.setText(f"Export failed: {exc}")

    def stop(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel_requested.set()
            self.worker.wait(60000)
