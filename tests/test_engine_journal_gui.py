import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from src.app.config import ROOT
from src.market.fake import FakeMarketDataProvider
from src.market.models import MarketDataError
from src.storage.journal import TradeJournal
from src.trading.engine import TradingEngine
from src.trading.models import OrderSide, OrderStatus
from src.ui.main_window import MainWindow
from tests.helpers import OPEN, config, frame


class EngineJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.path = Path(self.temp.name) / "test.db"
        self.journal = TradeJournal(self.path)
        self.cfg = config(watchlist=("sz000001",), short_window=2, long_window=3,
                          breakout_window=2, volume_multiplier=1, order_quantity=100)

    def tearDown(self):
        self.journal.close()
        self.temp.cleanup()

    def engine(self, frames, fail_at=None):
        return TradingEngine(FakeMarketDataProvider(frames, fail_at=fail_at), self.cfg, self.journal)

    def test_engine_manual_order_and_journal(self):
        engine = self.engine([frame()])
        engine.connect()
        engine.poll(OPEN)
        order, decision = engine.manual_paper_order("sz000001", OrderSide.BUY, 100, OPEN)
        self.assertTrue(decision.accepted)
        self.assertEqual(order.status, OrderStatus.FILLED)
        for table in ("signals", "risk_decisions", "orders", "fills", "trades", "portfolio_snapshots"):
            self.assertGreater(self.journal.count(table), 0, table)

    def test_restart_loads_position_and_t_plus_one(self):
        engine = self.engine([frame()])
        engine.connect()
        engine.poll(OPEN)
        engine.manual_paper_order("sz000001", OrderSide.BUY, 100, OPEN)
        restarted = self.engine([frame()])
        self.assertEqual(restarted.portfolio.positions["sz000001"].quantity, 100)
        self.assertEqual(restarted.portfolio.positions["sz000001"].available_quantity, 0)

    def test_provider_failure_stops_paper_orders(self):
        engine = self.engine([frame()], fail_at=1)
        engine.connect()
        engine.poll(OPEN)
        with self.assertRaises(MarketDataError):
            engine.poll(OPEN + timedelta(seconds=5))
        order, decision = engine.manual_paper_order("sz000001", OrderSide.BUY, 100, OPEN + timedelta(seconds=5))
        self.assertFalse(decision.accepted)
        self.assertEqual(order.status, OrderStatus.REJECTED)

    def test_stale_data_stops_order(self):
        engine = self.engine([frame()])
        engine.connect()
        engine.poll(OPEN + timedelta(seconds=30))
        self.assertTrue(engine.stale)
        order, _ = engine.manual_paper_order("sz000001", OrderSide.BUY, 100, OPEN + timedelta(seconds=30))
        self.assertEqual(order.status, OrderStatus.REJECTED)

    def test_strategy_to_risk_to_fill(self):
        frames = [frame(price, OPEN + timedelta(seconds=i * 5), 100 + 100 * i + (100 if i == 3 else 0))
                  for i, price in enumerate((9, 10, 11, 12))]
        engine = self.engine(frames)
        engine.connect()
        for i in range(4):
            engine.poll(OPEN + timedelta(seconds=i * 5))
            engine.provider.advance()
        self.assertEqual(engine.portfolio.positions["sz000001"].quantity, 100)
        self.assertEqual(self.journal.count("trades"), 1)

    def test_full_buy_mark_sell_pnl(self):
        next_day = OPEN + timedelta(days=1)
        frames = [frame(10, OPEN), frame(12, next_day)]
        engine = self.engine(frames)
        engine.connect()
        engine.poll(OPEN)
        engine.manual_paper_order("sz000001", OrderSide.BUY, 100, OPEN)
        engine.provider.advance()
        engine.poll(next_day)
        self.assertGreater(engine.portfolio.unrealized_pnl, 0)
        order, decision = engine.manual_paper_order("sz000001", OrderSide.SELL, 100, next_day)
        self.assertTrue(decision.accepted)
        self.assertEqual(order.status, OrderStatus.FILLED)
        self.assertGreater(engine.portfolio.realized_pnl, 0)
        self.assertEqual(self.journal.count("trades"), 2)

    def test_gui_smoke_with_fake_provider(self):
        app = QApplication.instance() or QApplication([])
        engine = self.engine([frame()])
        window = MainWindow(engine)
        window.show()
        window.start_monitoring()
        QTimer.singleShot(600, app.quit)
        app.exec()
        self.assertIn("PAPER TRADING", window.windowTitle())
        self.assertEqual(window.index_table.rowCount(), 4)
        window.close()
