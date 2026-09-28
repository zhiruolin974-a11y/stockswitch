from __future__ import annotations

from datetime import datetime

from src.broker.paper import PaperBroker
from src.market.historical import MarketBar
from src.market.models import MarketQuote
from src.market.price_limits import PriceLimitRule
from src.trading.models import Fill, Order, OrderStatus, Trade


class BacktestBroker(PaperBroker):
    """Same virtual account and cost model, filled only at the next bar open."""

    def __init__(self, config, portfolio, profiles: dict[str, str]):
        super().__init__(config, portfolio)
        self.profiles = profiles
        self.limits = PriceLimitRule()

    def submit_at_open(self, order: Order, bar: MarketBar, previous_close: float | None,
                       at: datetime) -> tuple[Fill | None, Trade | None]:
        if bar.volume <= 0:
            return self._reject(order, "Suspended or zero-volume bar: no fill")
        fill_price = self.costs.fill_price(bar.open, order.side)
        decision = self.limits.check(bar, previous_close, fill_price,
                                     self.profiles.get(bar.symbol, "unknown"), order.side)
        if not decision.allowed:
            return self._reject(order, decision.reason)
        quote = MarketQuote(bar.symbol, bar.symbol, at, at, bar.open, bar.open, bar.open,
                            bar.open, previous_close or bar.open, 0, 0, 0, 0,
                            "Backtest next daily open", True)
        return self.submit_order(order, quote, at)

    def _reject(self, order: Order, reason: str) -> tuple[None, None]:
        order.status = OrderStatus.REJECTED
        order.reject_reason = reason
        self.orders.append(order)
        return None, None
