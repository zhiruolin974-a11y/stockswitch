from __future__ import annotations

import logging
import os
import sys
import threading
from dataclasses import replace
from pathlib import Path

from src.app.paths import AppPaths, DATA_HOME_OVERRIDE, is_frozen, resource_path
from src.app.version import VERSION
from src.utils.logging import setup_logging


def main() -> int:
    self_test = "--self-test" in sys.argv
    network_smoke = "--network-smoke" in sys.argv
    smoke_mode = self_test or network_smoke
    paths = None
    app = None
    message_box = None

    def report_exception(exc_type, exc_value, traceback):
        logging.critical("Unhandled exception", exc_info=(exc_type, exc_value, traceback))
        if app is not None and message_box is not None and paths is not None:
            message_box.critical(None, "StockSwitch", "程序遇到未预期错误。\n"
                                 f"请查看日志：{paths.log_path}")

    sys.excepthook = report_exception
    threading.excepthook = lambda args: report_exception(args.exc_type, args.exc_value, args.exc_traceback)
    try:
        if smoke_mode:
            override = os.environ.get(DATA_HOME_OVERRIDE)
            if not is_frozen() or not override or not Path(override).is_absolute():
                raise RuntimeError("Frozen smoke requires an absolute STOCKSWITCH_DATA_HOME override")
            local_app_data = Path(os.environ.get("LOCALAPPDATA", "C:/")).resolve()
            if Path(override).resolve().is_relative_to(local_app_data):
                raise RuntimeError("Smoke tests must not write to real LocalAppData")
        paths = AppPaths.for_runtime()
        paths.initialize()
        setup_logging(paths)
        logging.info("Startup StockSwitch %s; mode=%s; data=%s; PAPER TRADING only",
                     VERSION, "frozen" if is_frozen() else "development", paths.app_data_dir)

        if network_smoke:
            from src.app.config import load_config
            from src.app.network_smoke import run_network_smoke
            run_network_smoke(load_config(paths=paths), paths)
            logging.info("Network smoke completed")
            return 0

        from PySide6.QtGui import QFont, QIcon
        from PySide6.QtWidgets import QApplication, QMessageBox

        from src.app.config import load_config
        from src.app.self_test import fake_provider, run_self_test
        from src.market.tencent import TencentMarketDataProvider
        from src.storage.journal import TradeJournal
        from src.trading.engine import TradingEngine
        from src.ui.main_window import MainWindow

        message_box = QMessageBox
        config = load_config(paths=paths)
        if self_test:
            config = replace(config, watchlist=("sz000001",), strategy_enabled=False)
        journal = TradeJournal(paths.database_path)
        engine = TradingEngine(fake_provider() if self_test else TencentMarketDataProvider(), config, journal)
        app = QApplication(sys.argv)
        app.setFont(QFont("Microsoft YaHei UI", 9))
        icon = resource_path("assets/StockSwitch.ico")
        if icon.exists():
            app.setWindowIcon(QIcon(str(icon)))
        window = MainWindow(engine, paths=paths)
        window.show()
        logging.info("GUI initialized")
        outcome: dict[str, bool] = {}
        if self_test:
            run_self_test(app, window, engine, paths, outcome)
        else:
            window.start_monitoring()
        result = app.exec()
        logging.info("Shutdown; exit=%s", result)
        return 0 if self_test and outcome.get("ok") else 1 if self_test else result
    except Exception:
        logging.exception("Fatal startup/runtime error")
        if app is not None and message_box is not None and paths is not None:
            message_box.critical(None, "StockSwitch", "程序遇到未预期错误。\n"
                                 f"请查看日志：{paths.log_path}")
        elif not smoke_mode:
            # Startup can fail before Qt or logging exists; do not silently exit.
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, "StockSwitch 无法启动，请检查用户数据目录访问权限。",
                                              "StockSwitch", 0x10)
        return 1
