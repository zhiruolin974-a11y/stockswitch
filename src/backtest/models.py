from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from src.trading.models import Fill, Order, Trade, TradingSignal


@dataclass(frozen=True)
class BacktestConfig:
    symbols: tuple[str, ...]
    start_date: date
    end_date: date
    initial_cash: float = 100000.0
    frequency: str = "daily"
    adjustment: str = "none"
    benchmark: str = "sh000300"
    risk_free_rate: float = 0.02
    annualization_factor: int = 252
    security_profiles: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if (not self.symbols or self.end_date < self.start_date or self.initial_cash <= 0
                or self.frequency != "daily" or self.adjustment not in ("none", "qfq", "hfq")
                or self.annualization_factor <= 0):
            raise ValueError("Invalid backtest configuration")


@dataclass(frozen=True)
class EquityPoint:
    timestamp: datetime
    cash: float
    market_value: float
    total_equity: float
    drawdown: float
    benchmark_equity: float


@dataclass(frozen=True)
class RoundTrip:
    symbol: str
    entry_time: datetime
    entry_price: float
    exit_time: datetime
    exit_price: float
    quantity: int
    fees: float
    gross_pnl: float
    net_pnl: float
    return_pct: float
    holding_period: int
    strategy: str


@dataclass
class BacktestResult:
    run_id: str
    created_at: datetime
    config: BacktestConfig
    provider: str
    data_start: date
    data_end: date
    data_hash: str
    strategy: str
    strategy_params: dict
    cost_params: dict
    equity_curve: list[EquityPoint]
    orders: list[Order]
    fills: list[Fill]
    trades: list[Trade]
    round_trips: list[RoundTrip]
    signals: list[TradingSignal]
    risk_decisions: list[tuple[str, str, bool, str]]
    performance: dict
