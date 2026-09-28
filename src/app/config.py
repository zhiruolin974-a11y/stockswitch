from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class AppConfig:
    initial_cash: float
    watchlist: tuple[str, ...]
    market_refresh_seconds: int
    closed_refresh_seconds: int
    max_quote_age_seconds: int
    strategy_enabled: bool
    slippage_bps: float
    commission_rate: float
    minimum_commission: float
    stamp_tax_rate: float
    lot_size: int
    max_single_position: float
    max_total_position: float
    max_order_fraction: float
    max_daily_loss: float
    allow_buy: bool
    allow_sell: bool
    short_window: int
    long_window: int
    breakout_window: int
    volume_multiplier: float
    order_quantity: int
    backtest_risk_free_rate: float = 0.02
    backtest_annualization_factor: int = 252
    backtest_benchmark: str = "sh000300"
    backtest_security_profile: str = "unknown"


def load_config(path: Path | None = None) -> AppConfig:
    source = path or (ROOT / "config.toml" if (ROOT / "config.toml").exists() else ROOT / "config.example.toml")
    with source.open("rb") as handle:
        data = tomllib.load(handle)
    app, paper, risk, strategy = (data[key] for key in ("app", "paper", "risk", "strategy"))
    backtest = data.get("backtest", {})
    config = AppConfig(
        initial_cash=float(app["initial_cash"]),
        watchlist=tuple(app["watchlist"]),
        market_refresh_seconds=int(app["market_refresh_seconds"]),
        closed_refresh_seconds=int(app["closed_refresh_seconds"]),
        max_quote_age_seconds=int(app["max_quote_age_seconds"]),
        strategy_enabled=bool(app["strategy_enabled"]),
        slippage_bps=float(paper["slippage_bps"]),
        commission_rate=float(paper["commission_rate"]),
        minimum_commission=float(paper["minimum_commission"]),
        stamp_tax_rate=float(paper["stamp_tax_rate"]),
        lot_size=int(paper["lot_size"]),
        max_single_position=float(risk["max_single_position"]),
        max_total_position=float(risk["max_total_position"]),
        max_order_fraction=float(risk["max_order_fraction"]),
        max_daily_loss=float(risk["max_daily_loss"]),
        allow_buy=bool(risk["allow_buy"]),
        allow_sell=bool(risk["allow_sell"]),
        short_window=int(strategy["short_window"]),
        long_window=int(strategy["long_window"]),
        breakout_window=int(strategy["breakout_window"]),
        volume_multiplier=float(strategy["volume_multiplier"]),
        order_quantity=int(strategy["order_quantity"]),
        backtest_risk_free_rate=float(backtest.get("risk_free_rate", 0.02)),
        backtest_annualization_factor=int(backtest.get("annualization_factor", 252)),
        backtest_benchmark=str(backtest.get("benchmark", "sh000300")),
        backtest_security_profile=str(backtest.get("security_profile", "unknown")),
    )
    if config.initial_cash <= 0 or config.market_refresh_seconds < 5 or config.closed_refresh_seconds < 60:
        raise ValueError("Invalid cash or refresh interval")
    if config.max_quote_age_seconds <= 0 or config.lot_size <= 0:
        raise ValueError("Invalid quote age or lot size")
    if config.short_window < 2 or config.long_window <= config.short_window or config.breakout_window < 2:
        raise ValueError("Invalid strategy windows")
    if any(not 0 <= value <= 1 for value in (config.max_single_position, config.max_total_position, config.max_order_fraction, config.max_daily_loss)):
        raise ValueError("Invalid risk fractions")
    return config
