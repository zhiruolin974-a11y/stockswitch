from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHeaderView, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from src.ui.formatting import gain_color, money, percent_points, percent_ratio
from src.ui.i18n import data_source_label, status_label, tr
from src.ui.widgets import MetricStrip, fill_table, table


INDEX_NAMES = {"sh000001": "上证指数", "sz399001": "深证成指",
               "sz399006": "创业板指", "sh000300": "沪深300"}


class DashboardTab(QWidget):
    start_requested = Signal()
    stop_requested = Signal()
    add_symbol_requested = Signal(str)
    remove_symbol_requested = Signal(str)

    def __init__(self, config):
        super().__init__()
        layout = QVBoxLayout(self)
        self.status_label = QLabel(tr("market.disconnected"))
        self.status_label.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(self.status_label)
        self.metrics = MetricStrip([(key, tr("account." + key)) for key in
                                    ("equity", "cash", "value", "daily", "cumulative")])
        layout.addWidget(self.metrics)
        self.detail_label = QLabel(tr("market.empty"))
        self.detail_label.setWordWrap(True)
        layout.addWidget(self.detail_label)
        controls = QHBoxLayout()
        self.start_button = QPushButton(tr("market.connect"))
        self.stop_button = QPushButton(tr("market.stop"))
        self.stop_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_requested.emit)
        self.stop_button.clicked.connect(self.stop_requested.emit)
        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)
        controls.addStretch()
        self.symbol_input = QLineEdit()
        self.symbol_input.setPlaceholderText(tr("market.code_hint"))
        self.symbol_input.setMaximumWidth(220)
        controls.addWidget(self.symbol_input)
        for key, signal in (("add", self.add_symbol_requested), ("remove", self.remove_symbol_requested)):
            button = QPushButton(tr("market." + key))
            button.clicked.connect(lambda checked=False, target=signal: target.emit(self.symbol_input.text().strip()))
            controls.addWidget(button)
        layout.addLayout(controls)
        layout.addWidget(QLabel(tr("market.indexes")))
        self.index_table = table(["指数名称", "当前点位", "涨跌额", "涨跌幅", "报价时间"])
        self.index_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.index_table.setMaximumHeight(185)
        layout.addWidget(self.index_table)
        layout.addWidget(QLabel(tr("market.watchlist")))
        self.quote_table = table(["股票代码", "股票名称", "当前价格", "涨跌幅", "报价时间", "行情状态"])
        self.quote_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.quote_table, 1)
        self.empty_label = QLabel(tr("market.empty"))
        layout.addWidget(self.empty_label)
        for key in ("equity", "cash"):
            self.metrics.set_value(key, money(config.initial_cash))
        self.metrics.set_value("value", money(0))

    @staticmethod
    def quote_detail(quote, stale=False):
        condition = tr("status.stale") if stale else tr("status.delayed") if quote.is_delayed else tr("status.normal")
        return f"{data_source_label(quote.source)} · {quote.timestamp:%Y-%m-%d %H:%M:%S} · {condition}"

    def render_snapshot(self, state):
        key = ("disconnected" if not state["connected"] else "stale" if state["stale"]
               else "delayed" if state.get("delayed") else "normal")
        self.status_label.setText(tr("market." + key) + "  ·  " + status_label(state["market_state"]))
        quotes = state["indexes"] + state["quotes"]
        timestamp = min((q.timestamp for q in quotes), default=None)
        detail = (f"{data_source_label(state['source'])} · 报价时间：{timestamp:%Y-%m-%d %H:%M:%S}"
                  if timestamp else tr("market.empty"))
        detail += " · 公开行情可能延迟；过期或异常行情会暂停交易"
        self.detail_label.setText(detail)
        self.status_label.setToolTip(detail)
        monitoring = state.get("monitoring", False)
        self.start_button.setEnabled(not monitoring)
        self.stop_button.setEnabled(monitoring)
        for key, value in (("equity", state["equity"]), ("cash", state["cash"]), ("value", state["market_value"])):
            self.metrics.set_value(key, money(value))
        for key, amount, denominator in (("daily", state["daily"], state["day_start_equity"]),
                                        ("cumulative", state["equity"] - state["initial_cash"], state["initial_cash"])):
            ratio = amount / denominator if denominator > 0 else None
            self.metrics.set_value(key, money(amount, True) + "\n" + percent_ratio(ratio, True),
                                   gain_color(amount), "今日比例以日初资产为基准；累计比例以起始资金为基准。")
        rows, colors, tips = [], {}, []
        for row, quote in enumerate(state["indexes"]):
            rows.append([INDEX_NAMES.get(quote.symbol, quote.name), f"{quote.last_price:,.2f}",
                         f"{quote.change:+,.2f}", percent_points(quote.change_percent, True), f"{quote.timestamp:%H:%M:%S}"])
            colors[row, 2] = colors[row, 3] = gain_color(quote.change)
            tips.append(self.quote_detail(quote, state["stale"]))
        fill_table(self.index_table, rows, colors, tips)
        rows, colors, tips = [], {}, []
        for row, quote in enumerate(state["quotes"]):
            rows.append([quote.symbol, quote.name, money(quote.last_price), percent_points(quote.change_percent, True),
                         f"{quote.timestamp:%Y-%m-%d %H:%M:%S}",
                         "已过期" if state["stale"] else "延迟行情" if quote.is_delayed else "行情正常"])
            colors[row, 3] = gain_color(quote.change_percent)
            tips.append(self.quote_detail(quote, state["stale"]))
        fill_table(self.quote_table, rows, colors, tips)
        self.empty_label.setVisible(not rows)
