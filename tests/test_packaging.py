import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.app.config import ROOT, load_config
from src.app.paths import AppPaths, PROJECT_ROOT, is_frozen, resource_path
from src.app.version import VERSION
from src.utils.logging import setup_logging


class PackagingPathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.root = Path(self.temp.name)
        self.paths = AppPaths(self.root)

    def tearDown(self):
        import logging
        logging.shutdown()
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
            handler.close()
        self.temp.cleanup()

    def test_app_paths(self):
        self.assertEqual(self.paths.app_data_dir, self.root)
        self.assertEqual(self.paths.config_dir, self.root / "config")
        self.assertEqual(self.paths.data_dir, self.root / "data")
        self.assertEqual(self.paths.cache_dir, self.root / "cache")

    def test_development_path(self):
        self.assertEqual(AppPaths.for_runtime(frozen=False, environ={}).app_data_dir, PROJECT_ROOT)

    def test_frozen_local_app_data_path(self):
        paths = AppPaths.for_runtime(frozen=True, environ={"LOCALAPPDATA": str(self.root)})
        self.assertEqual(paths.app_data_dir, self.root / "StockSwitch")

    def test_frozen_without_local_app_data_fails(self):
        with self.assertRaises(RuntimeError):
            AppPaths.for_runtime(frozen=True, environ={})

    def test_test_override(self):
        value = str(self.root / "override")
        paths = AppPaths.for_runtime(frozen=True, environ={"STOCKSWITCH_DATA_HOME": value})
        self.assertEqual(paths.app_data_dir, Path(value))

    def test_first_run_creates_all_directories_and_config(self):
        self.paths.initialize()
        for directory in (self.paths.config_dir, self.paths.data_dir, self.paths.history_dir,
                          self.paths.logs_dir, self.paths.exports_dir, self.paths.cache_dir):
            self.assertTrue(directory.is_dir(), directory)
        self.assertTrue(self.paths.config_path.exists())
        self.assertIn(b"config_schema_version = 1", self.paths.config_path.read_bytes())

    def test_existing_files_preserved_on_restart(self):
        self.paths.initialize()
        self.paths.config_path.write_text("custom = true", encoding="utf-8")
        self.paths.database_path.write_bytes(b"private-user-database")
        self.paths.initialize()
        self.assertEqual(self.paths.config_path.read_text(encoding="utf-8"), "custom = true")
        self.assertEqual(self.paths.database_path.read_bytes(), b"private-user-database")

    def test_database_and_history_paths(self):
        self.assertEqual(self.paths.database_path, self.root / "data" / "stockswitch.db")
        self.assertEqual(self.paths.backtests_path, self.root / "data" / "backtests.db")
        self.assertEqual(self.paths.history_database_path, self.root / "data" / "history" / "daily.sqlite")

    def test_log_and_export_paths(self):
        self.assertEqual(self.paths.log_path, self.root / "logs" / "stockswitch.log")
        self.assertEqual(self.paths.exports_dir, self.root / "exports")

    def test_config_initialization_loads_default(self):
        self.paths.initialize()
        config = load_config(paths=self.paths)
        self.assertEqual(config.initial_cash, 100000)

    def test_resource_lookup_and_traversal_guard(self):
        self.assertEqual(resource_path("config.example.toml"), PROJECT_ROOT / "config.example.toml")
        with self.assertRaises(ValueError):
            resource_path("../private.txt")

    def test_frozen_resource_lookup(self):
        with patch.object(sys, "frozen", True, create=True), patch.object(sys, "_MEIPASS", str(self.root), create=True):
            self.assertTrue(is_frozen())
            self.assertEqual(resource_path("assets/StockSwitch.ico"), self.root / "assets" / "StockSwitch.ico")

    def test_runtime_detection_development(self):
        with patch.object(sys, "frozen", False, create=True):
            self.assertFalse(is_frozen())

    def test_version(self):
        self.assertEqual(VERSION, "0.2.0")

    def test_logging_stays_in_override_root(self):
        import logging
        self.paths.initialize()
        setup_logging(self.paths)
        logging.info("packaging test")
        self.assertTrue(self.paths.log_path.exists())
        self.assertIn("packaging test", self.paths.log_path.read_text(encoding="utf-8"))

    def test_no_real_user_data_written(self):
        self.paths.initialize()
        self.assertTrue(self.paths.app_data_dir.is_relative_to(ROOT))
        self.assertNotEqual(self.paths.app_data_dir, Path(os.environ.get("LOCALAPPDATA", "C:/Users/none/AppData/Local")) / "StockSwitch")


if __name__ == "__main__":
    unittest.main()
