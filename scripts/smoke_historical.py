"""Read-only real history and paper-only historical backtest smoke."""

from datetime import date

from src.app.config import load_config
from src.app.paths import AppPaths
from src.backtest.engine import BacktestEngine
from src.backtest.models import BacktestConfig
from src.backtest.reporting import BacktestRunStore, export_result
from src.market.historical import HistoricalCache, TencentHistoricalMarketDataProvider


def main() -> int:
    paths = AppPaths.for_runtime()
    paths.initialize()
    # Fixed dates make the smoke reproducible and avoid an incomplete current-day bar.
    start, end = date(2026, 3, 2), date(2026, 9, 25)
    symbols = ("sz000001", "sh600519")
    provider = HistoricalCache(paths.history_database_path,
                               TencentHistoricalMarketDataProvider())
    last_decile = -1
    def progress(percent: int, stage: str) -> None:
        nonlocal last_decile
        if percent // 10 > last_decile:
            last_decile = percent // 10
            print(f"{percent}% {stage}")
    try:
        result = BacktestEngine(provider, load_config(paths=paths)).run(
            BacktestConfig(symbols, start, end, frequency="daily", adjustment="none",
                           benchmark="sh000300", security_profiles={
                               "sz000001": "main_normal", "sh600519": "main_normal"}),
            progress=progress)
    finally:
        provider.close()
    store = BacktestRunStore(paths.backtests_path, paths=paths)
    try:
        store.save(result)
    finally:
        store.close()
    location = export_result(result, paths=paths)
    print(f"run_id={result.run_id} provider={result.provider} adjustment={result.config.adjustment}")
    print(f"data_range={result.data_start}..{result.data_end} data_hash={result.data_hash}")
    print(f"equity_points={len(result.equity_curve)} fills={len(result.fills)} "
          f"round_trips={len(result.round_trips)}")
    print(f"performance={result.performance}")
    print(f"export={location}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
