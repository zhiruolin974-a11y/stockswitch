import unittest
from datetime import timedelta

from src.broker.paper import PaperBroker
from src.portfolio.portfolio import Portfolio
from src.trading.models import Order, OrderSide, OrderStatus
from tests.helpers import OPEN, config, quote


class PaperTests(unittest.TestCase):
    def setUp(self):
        self.config = config()
        self.portfolio = Portfolio(self.config.initial_cash)
        self.portfolio.roll_day(OPEN.date())
        self.broker = PaperBroker(self.config, self.portfolio)

    def submit(self, side, quantity=100, price=10, at=OPEN):
        order = Order("sz000001", side, quantity, price, at, "test")
        fill, trade = self.broker.submit_order(order, quote(price=price, at=at), at)
        return order, fill, trade

    def test_initial_portfolio(self):
        self.assertEqual(self.portfolio.total_equity, 100000)
        self.assertEqual(self.portfolio.market_value, 0)

    def test_buy_fill_slippage_commission(self):
        order, fill, _ = self.submit(OrderSide.BUY)
        self.assertEqual(order.status, OrderStatus.FILLED)
        self.assertGreater(fill.fill_price, fill.signal_price)
        self.assertEqual(fill.commission, 5)
        self.assertEqual(self.portfolio.positions["sz000001"].available_quantity, 0)

    def test_t_plus_one_rejects_same_day_sell(self):
        self.submit(OrderSide.BUY)
        order, _, _ = self.submit(OrderSide.SELL)
        self.assertEqual(order.status, OrderStatus.REJECTED)
        self.assertIn("T+1", order.reject_reason)

    def test_sell_fill_realized_pnl_and_tax(self):
        self.submit(OrderSide.BUY)
        next_day = OPEN + timedelta(days=1)
        self.portfolio.roll_day(next_day.date())
        order, fill, trade = self.submit(OrderSide.SELL, price=12, at=next_day)
        self.assertEqual(order.status, OrderStatus.FILLED)
        self.assertLess(fill.fill_price, 12)
        self.assertGreater(fill.stamp_tax, 0)
        self.assertGreater(trade.realized_pnl, 0)
        self.assertEqual(self.portfolio.realized_pnl, trade.realized_pnl)

    def test_unrealized_pnl(self):
        self.submit(OrderSide.BUY)
        self.portfolio.mark("sz000001", 12)
        self.assertGreater(self.portfolio.unrealized_pnl, 0)

    def test_insufficient_cash(self):
        order, _, _ = self.submit(OrderSide.BUY, quantity=20000)
        self.assertEqual(order.status, OrderStatus.REJECTED)

    def test_insufficient_holdings(self):
        order, _, _ = self.submit(OrderSide.SELL)
        self.assertEqual(order.status, OrderStatus.REJECTED)

    def test_broker_query_and_cancel(self):
        order, _, _ = self.submit(OrderSide.BUY)
        self.assertEqual(len(self.broker.query_orders()), 1)
        self.assertEqual(len(self.broker.query_trades()), 1)
        self.assertFalse(self.broker.cancel_order(order.id))
        self.assertEqual(self.broker.query_cash(), self.portfolio.available_cash)
