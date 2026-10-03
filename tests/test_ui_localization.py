import os
import tempfile
import unittest
from unittest.mock import patch
from datetime import timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox

from src.app.config import ROOT
from src.app.paths import AppPaths
from src.market.fake import FakeMarketDataProvider
from src.storage.journal import TradeJournal
from src.trading.engine import TradingEngine
from src.trading.models import OrderSide
from src.ui.formatting import gain_color, money, percent_points, percent_ratio
from src.ui.i18n import DEFAULT_LOCALE, risk_reason, side_label, tr, user_error
from src.ui.main_window import MainWindow, MarketWorker
from tests.helpers import OPEN, config, frame


class ChineseUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.paths = AppPaths(Path(self.temp.name))
        self.journal = TradeJournal(self.paths.database_path)
        self.engine = TradingEngine(FakeMarketDataProvider([frame()]), config(strategy_enabled=False, watchlist=("sz000001",)), self.journal)
        self.engine.connect()
        self.engine.poll(OPEN)
        self.window = MainWindow(self.engine, paths=self.paths)
        self.window.paper_tab.first_use_notice_enabled = False
        self.window.render_snapshot(MarketWorker(self.engine).snapshot())

    def tearDown(self):
        self.window.close()
        self.journal.close()
        self.temp.cleanup()

    def approve(self, text):
        def click():
            dialog = self.app.activeModalWidget()
            self.assertIsInstance(dialog, QMessageBox)
            next(button for button in dialog.buttons() if button.text() == text).click()
        QTimer.singleShot(0, click)

    def test_default_language_and_fallback(self):
        self.assertEqual(DEFAULT_LOCALE, "zh_CN")
        self.assertEqual(tr("nav.overview"), "总览")
        self.assertEqual(tr("nav.overview", "en_US"), "Overview")
        self.assertEqual(tr("nav.overview", "unsupported"), "总览")
        self.assertFalse(self.app._stockswitch_qt_translator.isEmpty())
        self.assertEqual(self.window.backtest_tab.start_date.locale().name(), "zh_CN")

    def test_chinese_main_navigation(self):
        self.assertEqual([self.window.tabs.tabText(i) for i in range(5)],
                         ["总览", "模拟交易", "历史回测", "交易记录", "设置"])
        self.assertIn("0.2.0", self.window.windowTitle())

    def test_overview_indices_and_account(self):
        dashboard = self.window.dashboard_tab
        self.assertEqual(dashboard.index_table.rowCount(), 4)
        self.assertEqual(dashboard.index_table.item(0, 0).text(), "上证指数")
        self.assertEqual(dashboard.metrics.values["equity"].text(), money(self.engine.portfolio.total_equity))
        self.assertIn("报价时间", dashboard.detail_label.text())

    def test_paper_page_labels_and_holdings_columns(self):
        page = self.window.paper_tab
        self.assertEqual(page.buy_button.text(), "模拟买入")
        self.assertEqual(page.sell_button.text(), "模拟卖出")
        self.assertEqual(page.position_table.columnCount(), 9)
        self.assertEqual(page.position_table.horizontalHeaderItem(3).text(), "可卖数量")
        self.assertFalse(self.engine.strategy_enabled)

    def test_backtest_display_values_do_not_select_logic(self):
        page = self.window.backtest_tab
        self.assertEqual(page.run_button.text(), "开始回测")
        page.source.setCurrentIndex(page.source.findData("fake"))
        self.assertEqual(page.source.currentText(), "离线模拟数据")
        self.assertEqual(page.source.currentData(), "fake")
        self.assertEqual(page.frequency.currentData(), "daily")
        self.assertEqual(len(page.metric_values), 9)

    def test_settings_units_paths_and_read_only(self):
        texts = [label.text() for label in self.window.settings_tab.findChildren(QLabel)]
        self.assertIn("界面语言", texts)
        self.assertIn("简体中文（zh_CN）", texts)
        self.assertIn("历史行情缓存目录", texts)
        self.assertIn(str(self.paths.history_dir), texts)
        self.assertTrue(any("基点" in text for text in texts))
        self.assertIn("不能在这里保存", self.window.settings_tab.read_only_label.text())

    def test_risk_reason_and_error_mapping(self):
        self.assertIn("单只", risk_reason("Single position limit exceeded"))
        self.assertIn("T+1", risk_reason("Insufficient T+1 available holdings"))
        self.assertIn("停止交易", risk_reason("Data stale: private traceback"))
        self.assertNotIn("traceback", user_error("private traceback"))

    def test_side_mapping(self):
        self.assertEqual(side_label(OrderSide.BUY), "买入")
        self.assertEqual(side_label("SELL"), "卖出")

    def test_money_format(self):
        self.assertEqual(money(100000), "¥100,000.00")
        self.assertEqual(money(-123.4, True), "-¥123.40")
        self.assertEqual(money(float("nan")), "—")

    def test_percentage_scales_and_colors(self):
        self.assertEqual(percent_ratio(0.0325, True), "+3.25%")
        self.assertEqual(percent_points(3.25, True), "+3.25%")
        self.assertNotEqual(gain_color(1), gain_color(-1))
        self.assertEqual(gain_color(1), "#C62828")

    def test_empty_states(self):
        self.assertEqual(self.window.paper_tab.position_empty.text(), "当前没有模拟持仓。")
        self.assertEqual(self.window.paper_tab.signal_empty.text(), "当前暂无交易信号。")
        self.assertIn("请设置参数", self.window.backtest_tab.summary.text())
        self.assertIn("暂无模拟交易", self.window.records_tab.empty_label.text())

    def test_tooltips(self):
        self.assertIn("最大跌幅", self.window.backtest_tab.metric_values["max_drawdown"].toolTip())
        self.assertIn("报价时间", self.window.dashboard_tab.status_label.toolTip())
        self.assertTrue(self.window.backtest_tab.chart.toolTip())

    def test_order_confirmation_emits_without_direct_execution(self):
        page = self.window.paper_tab
        commands = []
        page.order_requested.disconnect()
        page.order_requested.connect(lambda *command: commands.append(command))
        self.approve("确认模拟买入")
        page.request_order(OrderSide.BUY)
        self.assertEqual(commands, [("sz000001", OrderSide.BUY, 100)])
        self.assertEqual(self.journal.count("orders"), 0)
        self.assertTrue(page.pending)
        self.assertFalse(page.buy_button.isEnabled())

    def test_trade_feedback_and_record_filter(self):
        order, decision = self.engine.manual_paper_order("sz000001", OrderSide.BUY, 100, OPEN)
        self.window.paper_tab.show_order_result({"order": order, "decision": decision,
                                                "trade": self.engine.broker.trades[-1], "cash": self.engine.portfolio.available_cash})
        self.assertIn("模拟买入成功", self.window.paper_tab.feedback.text())
        self.assertIn("手续费", self.window.paper_tab.feedback.text())
        self.window.render_snapshot(MarketWorker(self.engine).snapshot())
        records = self.window.records_tab
        self.assertEqual(records.table.rowCount(), 1)
        self.assertEqual(self.journal.list_recent_trades()[0].strategy, "Manual Paper")
        records.side_filter.setCurrentIndex(records.side_filter.findData("SELL"))
        self.assertEqual(records.table.rowCount(), 0)
        with self.assertRaises(ValueError):
            self.journal.list_recent_trades(limit=0)

    def test_holding_selection_prefills_sell(self):
        self.engine.manual_paper_order("sz000001", OrderSide.BUY, 100, OPEN)
        self.engine.portfolio.roll_day((OPEN + timedelta(days=1)).date())
        page = self.window.paper_tab
        self.window.render_snapshot(MarketWorker(self.engine).snapshot())
        page.position_table.selectRow(0)
        self.assertEqual(page.symbol_input.text(), "sz000001")
        self.assertEqual(page.quantity.value(), 100)

    def test_first_use_preference_is_in_app_paths(self):
        page = self.window.paper_tab
        page.first_use_notice_enabled = True
        def dismiss():
            dialog = self.app.activeModalWidget()
            dialog.checkBox().setChecked(True)
            dialog.buttons()[0].click()
        QTimer.singleShot(0, dismiss)
        page.show_first_use_notice()
        self.assertTrue((self.paths.config_dir / "paper_notice.dismissed").exists())
        page.show_first_use_notice()

    def test_stale_data_disables_manual_orders(self):
        state = MarketWorker(self.engine).snapshot()
        state["stale"] = True
        self.window.render_snapshot(state)
        self.assertFalse(self.window.paper_tab.buy_button.isEnabled())
        self.assertIn("已过期", self.window.dashboard_tab.status_label.text())

    def test_worker_manual_order_reaches_risk_fill_and_gui_feedback(self):
        results = []
        watchdog = QTimer()
        watchdog.setSingleShot(True)
        watchdog.timeout.connect(self.app.quit)
        with patch("src.ui.main_window.datetime") as clock:
            clock.now.return_value = OPEN
            self.window.start_monitoring()
            self.window.worker.order_completed.connect(lambda result: (results.append(result), self.app.quit()))
            self.window.queue_command("paper", "sz000001", OrderSide.BUY, 100)
            watchdog.start(3000)
            self.app.exec()
            watchdog.stop()
            self.window.stop_monitoring()
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["decision"].accepted)
        self.assertEqual(self.journal.count("risk_decisions"), 1)
        self.assertEqual(self.journal.count("trades"), 1)
        self.assertIn("模拟买入成功", self.window.paper_tab.feedback.text())

    def test_quote_query_is_a_worker_request(self):
        page = self.window.paper_tab
        page.quote_requested.disconnect()
        requested = []
        page.quote_requested.connect(requested.append)
        page.symbol_input.setText("600000")
        page.request_quote()
        self.assertEqual(requested, ["sh600000"])
        self.assertEqual(self.journal.count("orders"), 0)

    def test_auto_start_confirmation_updates_worker_runtime(self):
        watchdog = QTimer()
        watchdog.setSingleShot(True)
        watchdog.timeout.connect(self.app.quit)
        with patch("src.ui.main_window.datetime") as clock:
            clock.now.return_value = OPEN
            self.window.start_monitoring()
            self.window.worker.updated.connect(lambda state: self.app.quit() if state["strategy"] else None)
            self.approve("确认")
            self.window.paper_tab.toggle_auto()
            watchdog.start(3000)
            self.app.exec()
            watchdog.stop()
            self.window.stop_monitoring()
        self.assertTrue(self.engine.strategy_enabled)
        self.assertEqual(self.journal.count("orders"), 0)
