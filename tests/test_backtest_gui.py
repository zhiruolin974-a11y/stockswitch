import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate, QTimer
from PySide6.QtWidgets import QApplication, QTabWidget

from src.app.config import ROOT
from src.market.fake import FakeMarketDataProvider
from src.storage.journal import TradeJournal
from src.trading.engine import TradingEngine
from src.ui.main_window import MainWindow
from tests.helpers import config, frame


class BacktestGuiTests(unittest.TestCase):
    def test_full_gui_fake_run_chart_trades_export_and_phase1_tab(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            journal = TradeJournal(Path(directory) / "paper.sqlite")
            engine = TradingEngine(FakeMarketDataProvider([frame()]), config(), journal)
            window = MainWindow(engine)
            window.show()
            tabs = window.centralWidget()
            self.assertIsInstance(tabs, QTabWidget)
            self.assertEqual(tabs.tabText(0), "Live Paper Trading")
            tabs.setCurrentIndex(1)
            tab = window.backtest_tab
            tab.source.setCurrentText("Fake (offline smoke)")
            tab.security_profile.setCurrentText("main_normal")
            tab.start_date.setDate(QDate(2025, 1, 2))
            tab.end_date.setDate(QDate(2025, 9, 1))
            tab.output_path.setText(str(Path(directory) / "exports"))
            tab.run_button.click()
            self.assertTrue(tab.cancel_button.isEnabled())
            tab.worker.completed.connect(app.quit)
            tab.worker.failed.connect(app.quit)
            QTimer.singleShot(8000, app.quit)
            app.exec()
            self.assertIsNotNone(tab.result, tab.message.text())
            self.assertGreater(len(tab.chart.points), 100)
            self.assertGreater(tab.trades.rowCount(), 0)
            tab.export_button.click()
            exported = Path(directory) / "exports" / tab.result.run_id
            self.assertTrue((exported / "summary.json").exists())
            self.assertTrue((exported / "trades.csv").exists())
            self.assertTrue((exported / "equity_curve.csv").exists())
            tabs.setCurrentIndex(0)
            self.assertIn("PAPER TRADING", window.windowTitle())
            window.close()

    def test_gui_cancel_prevents_result(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            journal = TradeJournal(Path(directory) / "paper.sqlite")
            window = MainWindow(TradingEngine(FakeMarketDataProvider([frame()]), config(), journal))
            tab = window.backtest_tab
            tab.source.setCurrentText("Fake (offline smoke)")
            tab.start_date.setDate(QDate(2025, 1, 2))
            tab.end_date.setDate(QDate(2025, 9, 1))
            tab.run_button.click()
            tab.cancel_button.click()
            tab.worker.cancelled.connect(app.quit)
            tab.worker.completed.connect(app.quit)
            QTimer.singleShot(3000, app.quit)
            app.exec()
            self.assertIsNone(tab.result)
            self.assertIn("cancelled", tab.message.text().lower())
            window.close()
