from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from src.trading.models import Fill, OrderSide, Trade


@dataclass
class Position:
    symbol: str
    quantity: int = 0
    available_quantity: int = 0
    average_cost: float = 0.0
    market_price: float = 0.0
    today_bought: int = 0

    @property
    def market_value(self) -> float:
        return self.quantity * self.market_price

    @property
    def unrealized_pnl(self) -> float:
        return self.quantity * (self.market_price - self.average_cost)


@dataclass
class Portfolio:
    initial_cash: float
    available_cash: float = field(init=False)
    positions: dict[str, Position] = field(default_factory=dict)
    realized_pnl: float = 0.0
    current_day: date | None = None
    day_start_equity: float = field(init=False)

    def __post_init__(self) -> None:
        if self.initial_cash <= 0:
            raise ValueError("Initial cash must be positive")
        self.available_cash = self.initial_cash
        self.day_start_equity = self.initial_cash

    @property
    def market_value(self) -> float:
        return sum(position.market_value for position in self.positions.values())

    @property
    def total_equity(self) -> float:
        return self.available_cash + self.market_value

    @property
    def unrealized_pnl(self) -> float:
        return sum(position.unrealized_pnl for position in self.positions.values())

    @property
    def daily_pnl(self) -> float:
        return self.total_equity - self.day_start_equity

    def roll_day(self, new_day: date) -> None:
        if self.current_day == new_day:
            return
        self.day_start_equity = self.total_equity
        self.current_day = new_day
        for position in self.positions.values():
            position.available_quantity = position.quantity
            position.today_bought = 0

    def mark(self, symbol: str, price: float) -> None:
        if symbol in self.positions and price > 0:
            self.positions[symbol].market_price = price

    def apply_fill(self, fill: Fill) -> Trade:
        total_fees = fill.commission + fill.stamp_tax
        position = self.positions.setdefault(fill.symbol, Position(fill.symbol))
        realized = 0.0
        if fill.side == OrderSide.BUY:
            cost = fill.quantity * fill.fill_price + total_fees
            if cost > self.available_cash + 0.000001:
                raise ValueError("Insufficient virtual cash")
            old_cost = position.quantity * position.average_cost
            position.quantity += fill.quantity
            position.today_bought += fill.quantity
            position.average_cost = (old_cost + cost) / position.quantity
            self.available_cash -= cost
        else:
            if fill.quantity > position.available_quantity:
                raise ValueError("Insufficient T+1 available holdings")
            proceeds = fill.quantity * fill.fill_price - total_fees
            realized = proceeds - fill.quantity * position.average_cost
            self.available_cash += proceeds
            position.quantity -= fill.quantity
            position.available_quantity -= fill.quantity
            self.realized_pnl += realized
            if position.quantity == 0:
                del self.positions[fill.symbol]
        if fill.symbol in self.positions:
            self.positions[fill.symbol].market_price = fill.fill_price
        return Trade(fill.order_id, fill.symbol, fill.side, fill.quantity, fill.fill_price, total_fees, realized, fill.timestamp)
