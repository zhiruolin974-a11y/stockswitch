from __future__ import annotations

import logging
import threading
from datetime import date, datetime, time, timedelta
from pathlib import Path

from PySide6.QtCore import QDate, QThread, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QDateEdit, QDoubleSpinBox, QFormLayout, QHBoxLayout,
    QGridLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget)

from src.app.config import AppConfig
from src.app.paths import AppPaths
from src.backtest.engine import BacktestCancelled, BacktestEngine
from src.backtest.models import BacktestConfig, BacktestResult, EquityPoint
from src.backtest.reporting import BacktestRunStore, export_result
from src.market.calendar import SHANGHAI
from src.market.historical import (FakeHistoricalMarketDataProvider, HistoricalCache, MarketBar,
                                   TencentHistoricalMarketDataProvider)
from src.market.tencent import validate_symbol
from src.ui.formatting import gain_color, money, percent_ratio
from src.ui.i18n import data_source_label, side_label, strategy_label, tr

LOG = logging.getLogger(__name__)


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
        self.setMinimumHeight(280)
        self.setToolTip("蓝线为模拟资产，橙线为基准资产；下方绿线显示相对历史高点的回撤。")

    def set_points(self, points: list[EquityPoint]) -> None:
        self.points = points
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#ffffff"))
        painter.setPen(QColor("#344054"))
        painter.drawText(12, 22, "资金曲线 · 基准对比")
        painter.drawText(max(260, self.width() - 260), 22, "模拟资产（蓝）  基准资产（橙）")
        if len(self.points) < 2:
            painter.drawText(20, 85, tr("backtest.empty"))
            painter.end()
            return
        left, right = 88, max(89, self.width() - 20)
        top, bottom = 45, max(100, self.height() - 110)
        values = [v for p in self.points for v in (p.total_equity, p.benchmark_equity)]
        low, high = min(values), max(values)
        if high == low:
            high += 1
        def x(i): return left + (right - left) * i / (len(self.points) - 1)
        def y(value): return bottom - (bottom - top) * (value - low) / (high - low)
        painter.setPen(QColor("#e4e7ec"))
        for value in (low, (low + high) / 2, high):
            painter.drawLine(left, int(y(value)), right, int(y(value)))
            painter.setPen(QColor("#667085"))
            painter.drawText(4, int(y(value)) + 4, f"{value:,.0f}")
            painter.setPen(QColor("#e4e7ec"))
        painter.setPen(QColor("#667085"))
        painter.drawText(4, 35, "资产（元）")
        for attr, color in (("total_equity", "#2166ac"), ("benchmark_equity", "#e08214")):
            painter.setPen(QPen(QColor(color), 2))
            for i in range(1, len(self.points)):
                painter.drawLine(int(x(i - 1)), int(y(getattr(self.points[i - 1], attr))),
                                 int(x(i)), int(y(getattr(self.points[i], attr))))
        painter.setPen(QColor("#667085"))
        painter.drawText(left, bottom + 20, self.points[0].timestamp.strftime("%Y-%m-%d"))
        painter.drawText(max(left, right - 90), bottom + 20, self.points[-1].timestamp.strftime("%Y-%m-%d"))
        drawdown_top, drawdown_bottom = bottom + 45, self.height() - 12
        worst = min(p.drawdown for p in self.points)
        painter.drawText(4, drawdown_top + 5, "历史回撤")
        painter.drawText(4, drawdown_bottom, percent_ratio(worst))
        painter.setPen(QPen(QColor("#2e7d32"), 2))
        def dy(point):
            return drawdown_top if worst == 0 else drawdown_top + (drawdown_bottom - drawdown_top) * point.drawdown / worst
        for i in range(1, len(self.points)):
            painter.drawLine(int(x(i - 1)), int(dy(self.points[i - 1])),
                             int(x(i)), int(dy(self.points[i])))
        painter.end()


class BacktestWorker(QThread):
    progress_changed = Signal(int, str)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, app_config: AppConfig, config: BacktestConfig, source: str,
                 paths: AppPaths | None = None):
        super().__init__()
        self.app_config = app_config
        self.config = config
        self.source = source
        self.paths = paths or AppPaths.for_runtime()
        self.cancel_requested = threading.Event()

    def run(self) -> None:
        cache = None
        try:
            if self.source == "fake":
                warm_start = self.config.start_date - timedelta(days=220)
                provider = fake_daily_provider(tuple(dict.fromkeys((*self.config.symbols, self.config.benchmark))),
                                               warm_start, self.config.end_date, self.config.adjustment)
            else:
                cache = HistoricalCache(self.paths.history_database_path,
                                        TencentHistoricalMarketDataProvider())
                provider = cache
            result = BacktestEngine(provider, self.app_config).run(
                self.config, self.cancel_requested, lambda n, stage: self.progress_changed.emit(n, stage))
            if self.cancel_requested.is_set():
                raise BacktestCancelled()
            store = BacktestRunStore(self.paths.backtests_path, paths=self.paths)
            try:
                store.save(result)
            finally:
                store.close()
            self.completed.emit(result)
        except BacktestCancelled:
            self.cancelled.emit()
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception("Backtest failed")
            self.failed.emit(str(exc))
        finally:
            if cache:
                cache.close()


class BacktestTab(QWidget):
    result_ready = Signal(object)

    def __init__(self, app_config: AppConfig, *, paths: AppPaths | None = None):
        super().__init__()
        self.app_config = app_config
        self.paths = paths or AppPaths.for_runtime()
        self.worker: BacktestWorker | None = None
        self.result: BacktestResult | None = None
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        scroll.setWidget(body)
        outer.addWidget(scroll)
        layout = QVBoxLayout(body)
        form = QFormLayout()
        self.symbols_input = QLineEdit("sz000001")
        self.start_date = QDateEdit(QDate.currentDate().addMonths(-9))
        self.end_date = QDateEdit(QDate.currentDate().addDays(-1))
        for widget in (self.start_date, self.end_date):
            widget.setCalendarPopup(True)
            widget.setDisplayFormat("yyyy-MM-dd")
        self.frequency = QComboBox()
        self.frequency.addItem("日线", "daily")
        self.initial_cash = QDoubleSpinBox()
        self.initial_cash.setRange(1000, 1_000_000_000)
        self.initial_cash.setValue(app_config.initial_cash)
        self.initial_cash.setPrefix("¥")
        self.initial_cash.setGroupSeparatorShown(True)
        self.strategy_name = QLabel(strategy_label("TrendBreakoutStrategy"))
        self.benchmark = QLineEdit(app_config.backtest_benchmark)
        self.source = QComboBox()
        self.source.addItem("腾讯历史行情（本地缓存）", "tencent")
        self.source.addItem("离线模拟数据", "fake")
        self.security_profile = QComboBox()
        for name, value in (("未核验（不允许成交）", "unknown"), ("主板普通股票", "main_normal"),
                            ("主板 ST 股票", "main_st"), ("创业板", "chinext"), ("科创板", "star")):
            self.security_profile.addItem(name, value)
        self.security_profile.setCurrentIndex(self.security_profile.findData(app_config.backtest_security_profile))
        self.security_profile.setToolTip("请核验所选股票在整个回测期间适用的板块和涨跌停规则；未知类别禁止成交。")
        self.profile_overrides = QLineEdit()
        self.profile_overrides.setPlaceholderText("可选，例如 sz000001=main_normal,sz300750=chinext")
        self.profile_overrides.setToolTip("高级类别覆盖：main_normal 主板普通；main_st 主板 ST；chinext 创业板；star 科创板。")
        self.output_path = QLineEdit(str(self.paths.exports_dir / "backtests"))
        for label, widget in (("股票代码（逗号分隔）", self.symbols_input), ("开始日期", self.start_date),
                              ("结束日期", self.end_date), ("周期", self.frequency),
                              ("初始资金", self.initial_cash), ("策略", self.strategy_name),
                              ("业绩基准", self.benchmark), ("历史行情来源", self.source),
                              ("证券类别（需核验）", self.security_profile),
                              ("按股票覆盖类别（高级）", self.profile_overrides), ("导出目录", self.output_path)):
            form.addRow(label, widget)
        layout.addLayout(form)
        controls = QHBoxLayout()
        self.run_button = QPushButton("开始回测")
        self.cancel_button = QPushButton("取消回测")
        self.cancel_button.setEnabled(False)
        self.export_button = QPushButton("导出 CSV / JSON")
        self.export_button.setEnabled(False)
        self.run_button.clicked.connect(self.start_run)
        self.cancel_button.clicked.connect(self.cancel_run)
        self.export_button.clicked.connect(self.export)
        for button in (self.run_button, self.cancel_button, self.export_button):
            controls.addWidget(button)
        layout.addLayout(controls)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.message = QLabel("仅用于历史研究；未核验的证券类别不允许成交。")
        layout.addWidget(self.message)
        self.summary = QLabel("请设置参数后运行历史回测。")
        layout.addWidget(self.summary)
        self.summary.setWordWrap(True)
        self.metric_values = {}
        grid = QGridLayout()
        metrics = (
            ("initial_equity", "初始资金", "本次回测使用的虚拟起始资金。"),
            ("final_equity", "最终资产", "回测结束时的资金和持仓市值。"),
            ("total_return", "总收益率", "最终资产相对于初始资金的变化比例。"),
            ("annualized_return", "年化收益率", "按现有交易日年化因子折算的收益率，不代表未来收益。"),
            ("max_drawdown", "最大回撤", "历史资金曲线从某个高点到之后最低点的最大跌幅。"),
            ("sharpe", "夏普比率", "超额收益与波动的比值；数据不足时不显示数值。"),
            ("win_rate", "胜率", "已完成交易中盈利交易所占比例。"),
            ("total_trades", "交易次数", "已有绩效分析器统计的交易次数。"),
            ("profit_factor", "盈亏比（利润因子）", "盈利交易净盈利之和除以亏损交易净亏损绝对值之和。"),
        )
        for i, (key, title, tip) in enumerate(metrics):
            card = QWidget()
            box = QVBoxLayout(card)
            heading = QLabel(title)
            heading.setToolTip(tip)
            value = QLabel("—")
            value.setToolTip(tip)
            value.setStyleSheet("font-size: 16px; font-weight: 600;")
            box.addWidget(heading)
            box.addWidget(value)
            grid.addWidget(card, i // 3, i % 3)
            self.metric_values[key] = value
        layout.addLayout(grid)
        self.chart = EquityChart()
        layout.addWidget(self.chart)
        layout.addWidget(QLabel("本次回测成交"))
        self.trades = QTableWidget(0, 6)
        self.trades.setHorizontalHeaderLabels(["股票代码", "方向", "成交时间", "成交价格", "数量（股）", "手续费 / 盈亏"])
        self.trades.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.trades.setMinimumHeight(160)
        self.trades.horizontalHeader().setStretchLastSection(True)
        self.trades_empty = QLabel("本次回测尚无成交记录。")
        layout.addWidget(self.trades_empty)
        layout.addWidget(self.trades)

    def start_run(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        try:
            symbols = tuple(dict.fromkeys(validate_symbol(part.strip()) for part in self.symbols_input.text().split(",") if part.strip()))
            start = date.fromisoformat(self.start_date.date().toString("yyyy-MM-dd"))
            end = date.fromisoformat(self.end_date.date().toString("yyyy-MM-dd"))
            profile = self.security_profile.currentData()
            profiles = {symbol: profile for symbol in symbols}
            if self.profile_overrides.text().strip():
                for item in self.profile_overrides.text().split(","):
                    symbol_text, selected = item.strip().split("=", 1)
                    symbol = validate_symbol(symbol_text)
                    if symbol not in symbols or selected not in ("unknown", "main_normal", "main_st", "chinext", "star"):
                        raise ValueError(f"Invalid security profile override: {item}")
                    profiles[symbol] = selected
            config = BacktestConfig(symbols, start, end, self.initial_cash.value(), self.frequency.currentData(),
                                    "none", validate_symbol(self.benchmark.text(), allow_index=True),
                                    self.app_config.backtest_risk_free_rate,
                                    self.app_config.backtest_annualization_factor,
                                    profiles)
        except (ValueError, TypeError) as exc:
            LOG.warning("Invalid backtest input: %s", exc)
            self.message.setText(tr("backtest.invalid"))
            return
        self.worker = BacktestWorker(self.app_config, config, self.source.currentData(), self.paths)
        self.worker.progress_changed.connect(self.on_progress)
        self.worker.completed.connect(self.on_result)
        self.worker.failed.connect(self.on_failed)
        self.worker.cancelled.connect(self.on_cancelled)
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.export_button.setEnabled(False)
        self.progress.setValue(0)
        self.run_button.setText(tr("backtest.running"))
        self.message.setText(tr("backtest.loading"))
        self.worker.start()

    def cancel_run(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel_requested.set()
            self.message.setText(tr("backtest.cancel_requested"))

    def on_progress(self, value: int, stage: str) -> None:
        self.progress.setValue(value)
        self.message.setText(tr("backtest.loading") if value < 30 else tr("backtest.calculating"))

    def _finished(self) -> None:
        self.run_button.setEnabled(True)
        self.run_button.setText(tr("backtest.run"))
        self.cancel_button.setEnabled(False)

    def on_failed(self, message: str) -> None:
        self._finished()
        LOG.warning("Backtest GUI failure: %s", message)
        self.message.setText(tr("backtest.failed"))

    def on_cancelled(self) -> None:
        self._finished()
        self.message.setText(tr("backtest.cancelled"))

    def on_result(self, result: BacktestResult) -> None:
        self._finished()
        self.result = result
        self.export_button.setEnabled(True)
        self.progress.setValue(100)
        self.message.setText(f"回测已完成 · {data_source_label(result.provider)} · 未复权")
        p = result.performance
        self.summary.setText(f"业绩基准收益：{percent_ratio(p.get('benchmark_return'), True)}")
        for key, label in self.metric_values.items():
            value = p.get(key)
            if key in ("initial_equity", "final_equity"):
                text = money(value)
            elif key in ("total_return", "annualized_return", "max_drawdown", "win_rate"):
                text = percent_ratio(value, key != "win_rate")
            elif key == "total_trades":
                text = str(value) if value is not None else "—"
            else:
                text = f"{value:.2f}" if value is not None else "—"
            label.setText(text)
            if key in ("total_return", "annualized_return", "max_drawdown"):
                label.setStyleSheet(f"font-size: 16px; font-weight: 600; color: {gain_color(value)};")
        self.chart.set_points(result.equity_curve)
        self.trades.setRowCount(len(result.trades))
        for i, trade in enumerate(result.trades):
            values = [trade.symbol, side_label(trade.side), trade.timestamp.strftime("%Y-%m-%d %H:%M:%S"), money(trade.price),
                      f"{trade.quantity:,}", f"{money(trade.fees)} / {money(trade.realized_pnl, True)}"]
            for j, value in enumerate(values):
                self.trades.setItem(i, j, QTableWidgetItem(value))
        self.trades.resizeColumnsToContents()
        self.trades_empty.setVisible(not result.trades)
        self.result_ready.emit(result)

    def export(self) -> None:
        if self.result is None:
            return
        try:
            target = export_result(self.result, Path(self.output_path.text()) / self.result.run_id,
                                   paths=self.paths)
            self.message.setText(tr("backtest.exported", path=target))
        except Exception as exc:
            LOG.exception("Backtest export failed")
            self.message.setText(tr("backtest.export_failed"))

    def stop(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel_requested.set()
            self.worker.wait(10000)
