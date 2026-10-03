"""Read-only paper and current-session backtest trade history."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from src.backtest.models import BacktestResult
from src.storage.journal import JournalTradeRecord
from src.trading.models import OrderSide
from src.ui.formatting import gain_color, money
from src.ui.i18n import side_label, strategy_label


class RecordsTab(QWidget):
    """Paper fills are persisted; backtest fills exist only for this GUI session."""

    HEADERS = ("成交时间", "股票代码", "方向", "数量（股）", "成交价格",
               "手续费", "已实现盈亏", "策略")

    def __init__(self):
        super().__init__()
        self.paper_records: list[JournalTradeRecord] = []
        self.backtest_result: BacktestResult | None = None
        layout = QVBoxLayout(self)
        filters = QHBoxLayout()
        filters.addWidget(QLabel("记录来源"))
        self.source_filter = QComboBox()
        self.source_filter.addItem("模拟交易", "paper")
        self.source_filter.addItem("本次回测", "backtest")
        self.source_filter.setToolTip("模拟交易记录来自本地日志；回测成交仅显示本次程序运行期间的结果。")
        filters.addWidget(self.source_filter)
        filters.addWidget(QLabel("买卖方向"))
        self.side_filter = QComboBox()
        self.side_filter.addItem("全部", "all")
        self.side_filter.addItem("买入", OrderSide.BUY.value)
        self.side_filter.addItem("卖出", OrderSide.SELL.value)
        filters.addWidget(self.side_filter)
        filters.addStretch()
        layout.addLayout(filters)

        self.source_note = QLabel("显示本机最近 200 笔模拟成交，仅包含虚拟资金交易。")
        self.source_note.setWordWrap(True)
        layout.addWidget(self.source_note)
        self.count_label = QLabel("共 0 笔成交")
        layout.addWidget(self.count_label)
        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        self.empty_label = QLabel("暂无模拟交易成交记录。")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_label)

        self.source_filter.currentIndexChanged.connect(self.refresh)
        self.side_filter.currentIndexChanged.connect(self.refresh)

    def set_paper_records(self, rows: list[JournalTradeRecord]) -> None:
        """Replace the latest persisted paper fill snapshot from the market worker."""
        self.paper_records = list(rows)
        self.refresh()

    def set_backtest_result(self, result: BacktestResult | None) -> None:
        """Show the current session's full BacktestResult, never old summary rows."""
        self.backtest_result = result
        self.refresh()

    @staticmethod
    def _time(value: datetime) -> str:
        return value.strftime("%Y-%m-%d %H:%M:%S")

    def refresh(self) -> None:
        source = self.source_filter.currentData()
        side = self.side_filter.currentData()
        if source == "paper":
            records = [(record.timestamp, record.symbol, record.side, record.quantity,
                        record.price, record.fees, record.realized_pnl,
                        record.strategy, record.order_id) for record in self.paper_records]
            self.source_note.setText("显示本机最近 200 笔模拟成交，仅包含虚拟资金交易。")
            empty = "暂无模拟交易成交记录。"
        else:
            result = self.backtest_result
            strategies = {order.id: order.strategy for order in result.orders} if result else {}
            records = [(trade.timestamp, trade.symbol, trade.side, trade.quantity,
                        trade.price, trade.fees, trade.realized_pnl,
                        strategies.get(trade.order_id, result.strategy), trade.order_id)
                       for trade in result.trades] if result else []
            records.sort(key=lambda row: row[0], reverse=True)
            if result:
                self.source_note.setText(
                    f"仅显示本次程序运行期间的回测成交（运行编号：{result.run_id}）。"
                    "历史回测数据库只保存摘要，不保存逐笔成交。")
            else:
                self.source_note.setText(
                    "仅显示本次程序运行期间的回测成交；历史回测数据库不保存逐笔成交。")
            empty = "本次会话尚无回测成交记录。" if result is None else "本次回测没有成交记录。"
        if side != "all":
            records = [record for record in records if record[2].value == side]
        self.table.setRowCount(len(records))
        for row_number, record in enumerate(records):
            timestamp, symbol, trade_side, quantity, price, fees, pnl, strategy, order_id = record
            values = (self._time(timestamp), symbol, side_label(trade_side),
                      f"{quantity:,}", money(price), money(fees), money(pnl, signed=True),
                      strategy_label(strategy))
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(f"{value}\n模拟订单编号：{order_id}")
                if column == 6:
                    item.setForeground(QColor(gain_color(pnl)))
                self.table.setItem(row_number, column, item)
        self.table.resizeColumnsToContents()
        self.count_label.setText(f"共 {len(records)} 笔成交")
        self.empty_label.setText(empty)
        self.empty_label.setVisible(not records)
