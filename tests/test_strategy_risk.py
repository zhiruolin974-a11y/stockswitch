import unittest
from dataclasses import replace
from datetime import timedelta

from src.market.calendar import ChinaAMarketRules
from src.portfolio.portfolio import Portfolio, Position
from src.risk.manager import RiskManager
from src.strategy.trend import TrendBreakoutStrategy
from src.trading.models import OrderSide, TradingSignal
from tests.helpers import OPEN, config, quote


def signal(q, side=OrderSide.BUY):
    return TradingSignal("test", q.symbol, q.timestamp, side, 1, "test", q.last_price)


class StrategyRiskTests(unittest.TestCase):
    def setUp(self):
        self.cfg = config()
        self.portfolio = Portfolio(100000)
        self.portfolio.roll_day(OPEN.date())
        self.risk = RiskManager(self.cfg, ChinaAMarketRules())

    def test_strategy_generates_buy_without_future_data(self):
        strategy = TrendBreakoutStrategy(2, 3, 2, 1)
        outputs = []
        for i, price in enumerate((9, 10, 11, 12)):
            q = quote(price=price, at=OPEN + timedelta(seconds=i), volume=100 + 100 * i + (100 if i == 3 else 0))
            outputs.append(strategy.on_quote(q, False))
        self.assertTrue(all(item is None for item in outputs[:-1]))
        self.assertEqual(outputs[-1].side, OrderSide.BUY)

    def test_strategy_generates_exit(self):
        strategy = TrendBreakoutStrategy(2, 3, 2, 1)
        for i, price in enumerate((9, 10, 11)):
            strategy.on_quote(quote(price=price, at=OPEN + timedelta(seconds=i), volume=100 * (i + 1)), True)
        result = strategy.on_quote(quote(price=8, at=OPEN + timedelta(seconds=3), volume=400), True)
        self.assertEqual(result.side, OrderSide.SELL)

    def test_risk_allows_small_buy(self):
        q = quote()
        self.assertTrue(self.risk.assess(signal(q), 100, q, self.portfolio, OPEN).accepted)

    def test_risk_single_position(self):
        q = quote()
        self.portfolio.positions[q.symbol] = Position(q.symbol, 900, 900, 10, 10)
        self.assertIn("Single position", self.risk.assess(signal(q), 200, q, self.portfolio, OPEN).reason)

    def test_risk_total_position(self):
        q = quote()
        self.portfolio.available_cash = 41000
        self.portfolio.positions["sh600000"] = Position("sh600000", 5900, 5900, 10, 10)
        self.assertIn("Total position", self.risk.assess(signal(q), 200, q, self.portfolio, OPEN).reason)

    def test_risk_daily_loss(self):
        q = quote()
        self.portfolio.available_cash = 97000
        self.assertIn("Daily", self.risk.assess(signal(q), 100, q, self.portfolio, OPEN).reason)

    def test_risk_stale_and_closed(self):
        q = quote()
        self.assertIn("Data stale", self.risk.assess(signal(q), 100, q, self.portfolio, OPEN + timedelta(seconds=21)).reason)
        self.assertIn("not open", self.risk.assess(signal(q), 100, q, self.portfolio, OPEN.replace(hour=12)).reason)

    def test_risk_insufficient_cash_and_holdings(self):
        q = quote()
        self.portfolio.available_cash = 100
        self.portfolio.positions["sh600000"] = Position("sh600000", 9990, 9990, 10, 10)
        self.assertIn("cash", self.risk.assess(signal(q), 100, q, self.portfolio, OPEN).reason)
        self.assertIn("holdings", self.risk.assess(signal(q, OrderSide.SELL), 100, q, self.portfolio, OPEN).reason)
