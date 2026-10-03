from __future__ import annotations

import logging

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QCheckBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QScrollArea, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from src.market.tencent import validate_symbol
from src.trading.models import OrderSide, OrderStatus
from src.ui.formatting import gain_color, money, percent_ratio
from src.ui.i18n import risk_reason, side_label, signal_reason, strategy_label, tr
from src.ui.widgets import MetricStrip, fill_table, table


LOG = logging.getLogger(__name__)


class PaperTab(QWidget):
    order_requested = Signal(str, object, int)
    auto_toggle_requested = Signal(bool)
    quote_requested = Signal(str)

    def __init__(self, config, *, paths):
        super().__init__()
        self.config, self.paths = config, paths
        self.state = {}
        self.pending = False
        self.first_use_notice_enabled = True
        self._notice_shown = False
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        scroll.setWidget(body)
        outer.addWidget(scroll)
        layout = QVBoxLayout(body)
        layout.addWidget(QLabel(tr("paper.account")))
        self.metrics = MetricStrip([(key, tr("account." + key)) for key in
                                    ("initial", "equity", "cash", "value", "daily")])
        layout.addWidget(self.metrics)
        self.modes = QTabWidget()
        layout.addWidget(self.modes)
        manual = QWidget()
        form = QFormLayout(manual)
        self.symbol_input = QLineEdit(config.watchlist[0] if config.watchlist else "")
        self.symbol_input.setPlaceholderText(tr("market.code_hint"))
        self.quantity = QSpinBox()
        self.quantity.setRange(1, 1_000_000)
        self.quantity.setSingleStep(config.lot_size)
        self.quantity.setValue(config.lot_size)
        self.quote_label = QLabel(tr("paper.no_quote"))
        self.estimate_label = QLabel(tr("paper.estimate", amount=money(None)))
        code_controls = QHBoxLayout()
        code_controls.addWidget(self.symbol_input)
        self.quote_button = QPushButton("查询 / 添加股票")
        self.quote_button.clicked.connect(self.request_quote)
        code_controls.addWidget(self.quote_button)
        form.addRow("股票代码", code_controls)
        form.addRow("交易数量（股）", self.quantity)
        form.addRow("股票与参考价格", self.quote_label)
        form.addRow("预计金额", self.estimate_label)
        buttons = QHBoxLayout()
        self.buy_button = QPushButton(tr("paper.buy"))
        self.sell_button = QPushButton(tr("paper.sell"))
        self.buy_button.clicked.connect(lambda: self.request_order(OrderSide.BUY))
        self.sell_button.clicked.connect(lambda: self.request_order(OrderSide.SELL))
        buttons.addWidget(self.buy_button)
        buttons.addWidget(self.sell_button)
        form.addRow(buttons)
        self.modes.addTab(manual, tr("paper.manual"))

        automatic = QWidget()
        auto_layout = QVBoxLayout(automatic)
        auto_layout.addWidget(QLabel(strategy_label("TrendBreakoutStrategy")))
        self.auto_status = QLabel(tr("paper.stopped"))
        auto_layout.addWidget(self.auto_status)
        limits = QLabel(f"单股最大仓位 {percent_ratio(config.max_single_position)}  ·  "
                        f"总仓位上限 {percent_ratio(config.max_total_position)}  ·  "
                        f"单日最大亏损 {percent_ratio(config.max_daily_loss)}")
        limits.setToolTip("每个策略订单都经过风险管理器；行情异常时会暂停模拟成交。")
        auto_layout.addWidget(limits)
        self.auto_button = QPushButton(tr("paper.start_auto"))
        self.auto_button.clicked.connect(self.toggle_auto)
        auto_layout.addWidget(self.auto_button)
        auto_layout.addWidget(QLabel("仅虚拟资金模拟；已有趋势突破策略不承诺收益。"))
        self.modes.addTab(automatic, tr("paper.auto"))
        self.feedback = QLabel(tr("app.paper_only"))
        self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)
        layout.addWidget(QLabel(tr("paper.holdings")))
        self.position_table = table(["股票代码", "股票名称", "持仓数量", "可卖数量", "平均成本",
                                     "当前价格", "持仓市值", "浮动盈亏", "盈亏比例"])
        self.position_table.setMinimumHeight(140)
        self.position_table.itemSelectionChanged.connect(self.prefill_sell)
        layout.addWidget(self.position_table)
        self.position_empty = QLabel(tr("paper.no_positions"))
        layout.addWidget(self.position_empty)
        layout.addWidget(QLabel(tr("paper.signals")))
        self.signal_table = table(["时间", "股票", "动作", "策略", "参考价格", "原因"])
        self.signal_table.setMinimumHeight(140)
        layout.addWidget(self.signal_table)
        self.signal_empty = QLabel(tr("paper.no_signals"))
        layout.addWidget(self.signal_empty)
        self.symbol_input.textChanged.connect(self.update_reference)
        self.quantity.valueChanged.connect(self.update_reference)
        self.update_reference()

    def selected_quote(self):
        try:
            symbol = validate_symbol(self.symbol_input.text().strip())
        except ValueError:
            return None
        return next((q for q in self.state.get("quotes", []) if q.symbol == symbol), None)

    def update_reference(self):
        quote = self.selected_quote()
        self.quote_label.setText(f"{quote.name} · {money(quote.last_price)}" if quote else tr("paper.no_quote"))
        self.estimate_label.setText(tr("paper.estimate", amount=money(quote.last_price * self.quantity.value() if quote else None)))
        available = bool(quote and self.state.get("monitoring") and self.state.get("connected")
                         and not self.state.get("stale") and not self.pending)
        self.buy_button.setEnabled(available)
        self.sell_button.setEnabled(available)
        self.quote_button.setEnabled(self.state.get("monitoring", False) and not self.pending)

    def request_quote(self):
        try:
            symbol = validate_symbol(self.symbol_input.text().strip())
        except ValueError:
            self.feedback.setText("股票代码无效，请输入有效的 A 股代码。")
            return
        self.quote_requested.emit(symbol)
        self.feedback.setText("正在查询行情；当前自选最多支持 8 只股票。")

    def request_order(self, side):
        quote = self.selected_quote()
        if quote is None or self.pending:
            return
        action = tr("paper.buy" if side == OrderSide.BUY else "paper.sell")
        dialog = QMessageBox(self)
        dialog.setWindowTitle(action)
        dialog.setText(tr("paper.reference", name=quote.name, symbol=quote.symbol,
                          quantity=f"{self.quantity.value():,}", price=money(quote.last_price),
                          amount=money(quote.last_price * self.quantity.value())))
        confirm = dialog.addButton(tr("paper.confirm", action=action), QMessageBox.ButtonRole.AcceptRole)
        dialog.addButton(tr("common.cancel"), QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        if dialog.clickedButton() is confirm:
            self.pending = True
            self.feedback.setText(tr("paper.pending"))
            self.update_reference()
            self.order_requested.emit(quote.symbol, side, self.quantity.value())

    def toggle_auto(self):
        enabled = not self.state.get("strategy", False)
        if enabled:
            dialog = QMessageBox(self)
            dialog.setWindowTitle(tr("paper.start_auto"))
            dialog.setText(tr("paper.auto_warning"))
            confirm = dialog.addButton(tr("common.confirm"), QMessageBox.ButtonRole.AcceptRole)
            dialog.addButton(tr("common.cancel"), QMessageBox.ButtonRole.RejectRole)
            dialog.exec()
            if dialog.clickedButton() is not confirm:
                return
        self.auto_button.setEnabled(False)
        self.auto_toggle_requested.emit(enabled)

    def show_order_result(self, payload):
        self.pending = False
        order, decision = payload["order"], payload["decision"]
        action = tr("paper.buy" if order.side == OrderSide.BUY else "paper.sell")
        trade = payload.get("trade")
        if order.status == OrderStatus.FILLED and trade:
            self.feedback.setText(tr("paper.success", action=action, price=money(trade.price),
                                     quantity=f"{trade.quantity:,}", fees=money(trade.fees), cash=money(payload["cash"])))
        else:
            self.feedback.setText(tr("paper.failure", action=action,
                                     reason=risk_reason(order.reject_reason or decision.reason)))
        self.update_reference()

    def show_command_error(self, message):
        self.pending = False
        self.feedback.setText(message)
        self.update_reference()

    def prefill_sell(self):
        row = self.position_table.currentRow()
        positions = self.state.get("positions", [])
        if 0 <= row < len(positions):
            position = positions[row]
            self.modes.setCurrentIndex(0)
            self.symbol_input.setText(position["symbol"])
            self.quantity.setValue(position["available_quantity"] or self.config.lot_size)
            if position["available_quantity"] == 0:
                self.feedback.setText("该持仓当前可卖 0 股；今日买入的 A 股受 T+1 限制。")

    def show_first_use_notice(self):
        marker = self.paths.config_dir / "paper_notice.dismissed"
        if not self.first_use_notice_enabled or self._notice_shown or marker.exists():
            return
        self._notice_shown = True
        dialog = QMessageBox(self)
        dialog.setWindowTitle(tr("paper.account"))
        dialog.setText(tr("paper.first_notice"))
        checkbox = QCheckBox(tr("app.do_not_show_again"))
        dialog.setCheckBox(checkbox)
        dialog.addButton(tr("common.close"), QMessageBox.ButtonRole.AcceptRole)
        dialog.exec()
        if checkbox.isChecked():
            try:
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_text("dismissed\n", encoding="utf-8")
            except OSError:
                LOG.exception("Could not persist first-use preference")
                self.feedback.setText("无法保存提示偏好，请检查数据目录权限。")

    def render_snapshot(self, state):
        self.state = state
        for key, value in (("initial", state["initial_cash"]), ("equity", state["equity"]),
                           ("cash", state["cash"]), ("value", state["market_value"])):
            self.metrics.set_value(key, money(value))
        ratio = state["daily"] / state["day_start_equity"] if state["day_start_equity"] > 0 else None
        self.metrics.set_value("daily", money(state["daily"], True) + "\n" + percent_ratio(ratio, True), gain_color(state["daily"]))
        running = state["strategy"] and state.get("monitoring", False)
        self.auto_status.setText(tr("paper.paused") if running and (state["stale"] or not state["connected"])
                                 else tr("paper.running") if running else tr("paper.stopped"))
        self.auto_button.setText(tr("paper.stop_auto" if state["strategy"] else "paper.start_auto"))
        self.auto_button.setEnabled(state.get("monitoring", False))
        self.position_table.blockSignals(True)
        rows, colors = [], {}
        for row, p in enumerate(state["positions"]):
            basis = p["average_cost"] * p["quantity"]
            rows.append([p["symbol"], p["name"], f"{p['quantity']:,}", f"{p['available_quantity']:,}",
                         money(p["average_cost"]), money(p["market_price"]), money(p["market_value"]),
                         money(p["unrealized_pnl"], True), percent_ratio(p["unrealized_pnl"] / basis if basis > 0 else None, True)])
            colors[row, 7] = colors[row, 8] = gain_color(p["unrealized_pnl"])
        fill_table(self.position_table, rows, colors)
        self.position_table.blockSignals(False)
        self.position_empty.setVisible(not rows)
        records = [r for r in reversed(state.get("event_records", [])) if r["side"] != OrderSide.HOLD]
        fill_table(self.signal_table, [[f"{r['timestamp']:%m-%d %H:%M:%S}", r["symbol"], side_label(r["side"]),
                   strategy_label(r["strategy"]), money(r["reference_price"]),
                   signal_reason(r.get("signal_reason", "")) + "；" + risk_reason(r["reason"])] for r in records])
        self.signal_empty.setVisible(not records)
        self.update_reference()
