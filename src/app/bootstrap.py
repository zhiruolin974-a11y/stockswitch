from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from src.app.config import ROOT, load_config
from src.market.tencent import TencentMarketDataProvider
from src.storage.journal import TradeJournal
from src.trading.engine import TradingEngine
from src.ui.main_window import MainWindow
from src.utils.logging import setup_logging


def main() -> int:
    setup_logging()
    logging.info("StockSwitch starting in PAPER TRADING mode")
    config = load_config()
    journal = TradeJournal(ROOT / "data" / "stockswitch.db")
    engine = TradingEngine(TencentMarketDataProvider(), config, journal)
    app = QApplication(sys.argv)
    window = MainWindow(engine)
    window.show()
    window.start_monitoring()
    return app.exec()
