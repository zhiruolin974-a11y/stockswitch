from __future__ import annotations

import logging
from datetime import datetime

from src.app.config import AppConfig
from src.broker.costs import TradingCostModel
from src.market.models import MarketQuote
from src.portfolio.portfolio import Portfolio, Position
from src.trading.models import Fill, Order, OrderSide, OrderStatus, Trade


LOG = logging.getLogger(__name__)


class PaperBroker:
    """Virtual-only synchronous fill simulator; no real brokerage transport."""

    def __init__(self, config: AppConfig, portfolio: Portfolio):
        self.config = config
        self.costs = TradingCostModel.from_config(config)
        self.portfolio = portfolio
        self.orders: list[Order] = []
        self.fills: list[Fill] = []
        self.trades: list[Trade] = []

    def submit_order(self, order: Order, quote: MarketQuote, at: datetime) -> tuple[Fill | None, Trade | None]:
        self.orders.append(order)
        position = self.portfolio.positions.get(order.symbol)
        odd_lot_exit = (order.side == OrderSide.SELL and position is not None
                        and order.quantity == position.available_quantity and order.quantity > 0)
        if (order.status != OrderStatus.NEW or order.symbol != quote.symbol or order.quantity <= 0
                or (order.quantity % self.config.lot_size and not odd_lot_exit)
                or order.side not in (OrderSide.BUY, OrderSide.SELL)):
            order.status = OrderStatus.REJECTED
            order.reject_reason = "Invalid paper order"
            return None, None
        price = self.costs.fill_price(quote.last_price, order.side)
        commission, stamp_tax = self.costs.fees(price, order.quantity, order.side)
        order.order_price = price
        fill = Fill(order.id, order.symbol, order.side, order.quantity, order.signal_price, order.order_price,
                    price, round(price - quote.last_price, 4), commission, stamp_tax, at)
        try:
            trade = self.portfolio.apply_fill(fill)
        except ValueError as exc:
            order.status = OrderStatus.REJECTED
            order.reject_reason = str(exc)
            LOG.warning("Paper order rejected %s: %s", order.id, exc)
            return None, None
        order.status = OrderStatus.FILLED
        self.fills.append(fill)
        self.trades.append(trade)
        LOG.info("Paper fill %s %s %s x%s at %.4f", order.id, order.side.value, order.symbol, order.quantity, price)
        return fill, trade

    def cancel_order(self, order_id: str) -> bool:
        for order in self.orders:
            if order.id == order_id and order.status == OrderStatus.NEW:
                order.status = OrderStatus.CANCELLED
                return True
        return False

    def query_orders(self) -> list[Order]:
        return list(self.orders)

    def query_trades(self) -> list[Trade]:
        return list(self.trades)

    def query_positions(self) -> dict[str, Position]:
        return dict(self.portfolio.positions)

    def query_cash(self) -> float:
        return self.portfolio.available_cash
