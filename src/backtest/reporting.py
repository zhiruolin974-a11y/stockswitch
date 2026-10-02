from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from src.app.paths import AppPaths
from src.backtest.models import BacktestResult


def _within_data_root(path: Path, paths: AppPaths) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(paths.app_data_dir.resolve()):
        raise ValueError("Backtest outputs must remain inside the application data directory")
    return resolved


class BacktestRunStore:
    """Separate from live paper-trading journal."""

    def __init__(self, path: Path, *, paths: AppPaths | None = None):
        path = _within_data_root(path, paths or AppPaths.for_runtime())
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS backtest_runs (
              run_id TEXT PRIMARY KEY, created_at TEXT, config_json TEXT, symbols TEXT,
              start_date TEXT, end_date TEXT, strategy TEXT, parameters_json TEXT,
              performance_json TEXT, trade_count INTEGER, provider TEXT, data_hash TEXT,
              cost_json TEXT)
        """)
        self.connection.commit()

    def save(self, result: BacktestResult) -> None:
        with self.connection:
            self.connection.execute("INSERT OR REPLACE INTO backtest_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                result.run_id, result.created_at.isoformat(), json.dumps(asdict(result.config), default=str),
                ",".join(result.config.symbols), result.config.start_date.isoformat(),
                result.config.end_date.isoformat(), result.strategy, json.dumps(result.strategy_params),
                json.dumps(result.performance), len(result.round_trips), result.provider,
                result.data_hash, json.dumps(result.cost_params)))

    def count(self) -> int:
        return self.connection.execute("SELECT COUNT(*) FROM backtest_runs").fetchone()[0]

    def close(self) -> None:
        self.connection.close()


def export_result(result: BacktestResult, output_dir: Path | None = None,
                  *, paths: AppPaths | None = None) -> Path:
    paths = paths or AppPaths.for_runtime()
    target = _within_data_root(output_dir or paths.exports_dir / "backtests" / result.run_id, paths)
    target.mkdir(parents=True, exist_ok=True)
    summary = {
        "run_id": result.run_id, "created_at": result.created_at.isoformat(),
        "config": asdict(result.config), "provider": result.provider, "frequency": result.config.frequency,
        "adjustment": result.config.adjustment, "data_start": result.data_start,
        "data_end": result.data_end, "data_hash": result.data_hash, "strategy": result.strategy,
        "strategy_params": result.strategy_params, "cost_params": result.cost_params,
        "benchmark": result.config.benchmark, "performance": result.performance,
        "trade_count": len(result.round_trips),
    }
    (target / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    with (target / "trades.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(result.round_trips[0])) if result.round_trips else
                                ["symbol", "entry_time", "entry_price", "exit_time", "exit_price", "quantity",
                                 "fees", "gross_pnl", "net_pnl", "return_pct", "holding_period", "strategy"])
        writer.writeheader()
        for trade in result.round_trips:
            writer.writerow(asdict(trade))
    with (target / "equity_curve.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["timestamp", "cash", "market_value", "total_equity",
                                                  "drawdown", "benchmark_equity"])
        writer.writeheader()
        for point in result.equity_curve:
            writer.writerow(asdict(point))
    return target
