import json
import tempfile
import threading
import unittest
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from pathlib import Path

from src.analytics.performance import PerformanceAnalyzer
from src.app.config import ROOT
from src.backtest.engine import BacktestCancelled, BacktestEngine
from src.backtest.models import BacktestConfig, EquityPoint, RoundTrip
from src.backtest.reporting import BacktestRunStore, export_result
from src.broker.costs import TradingCostModel
from src.market.calendar import SHANGHAI
from src.market.historical import (FakeHistoricalMarketDataProvider, HistoricalCache,
                                   InvalidHistoricalData, MarketBar, validate_bars)
from src.market.price_limits import PriceLimitRule
from src.market.trading_calendar import ChinaAMarketCalendar, UnknownTradingDay
from src.trading.models import OrderSide, OrderStatus
from src.ui.backtest_tab import fake_daily_provider
from tests.helpers import config


DAYS = [date(2025, 1, n) for n in (2, 3, 6, 7, 8, 9, 10)]


def bar(symbol: str, day: date, price: float, volume: float = 1_000_000,
        adjustment: str = "none") -> MarketBar:
    return MarketBar(symbol, datetime.combine(day, time(15), SHANGHAI), price, price + .03,
                     price - .03, price, volume, volume * price, adjustment)


def seven_day_provider(prices=(9, 10, 11, 12, 13, 11.8, 10.8), extra=None):
    stock = [bar("sz000001", day, price, 1_000_000 + i * 1000)
             for i, (day, price) in enumerate(zip(DAYS, prices))]
    benchmark = [bar("sh000300", day, 100 + i) for i, day in enumerate(DAYS)]
    data = {"sz000001": stock, "sh000300": benchmark}
    if extra:
        data.update(extra)
    return FakeHistoricalMarketDataProvider(data)


def bt_config(**changes):
    return replace(BacktestConfig(("sz000001",), DAYS[0], DAYS[-1],
                                  security_profiles={"sz000001": "main_normal"}), **changes)


class HistoricalTests(unittest.TestCase):
    def test_valid_bar_and_adjustment(self):
        self.assertEqual(bar("sz000001", DAYS[0], 10).adjustment, "none")

    def test_invalid_ohlc_and_volume(self):
        with self.assertRaises(InvalidHistoricalData):
            MarketBar("sz000001", datetime.combine(DAYS[0], time(15), SHANGHAI), 12, 11, 9, 10, 1, 1)
        with self.assertRaises(InvalidHistoricalData):
            bar("sz000001", DAYS[0], 10, -1)

    def test_duplicate_and_unordered_timestamp(self):
        a, b = bar("sz000001", DAYS[0], 10), bar("sz000001", DAYS[1], 11)
        for bars in ([a, a], [b, a]):
            with self.assertRaises(InvalidHistoricalData):
                validate_bars(bars, "sz000001", "none")

    def test_fake_history_range(self):
        provider = seven_day_provider()
        self.assertEqual(len(provider.get_bars("sz000001", DAYS[1], DAYS[3])), 3)

    def test_cache_and_incremental_missing_interval(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            provider = seven_day_provider()
            cache = HistoricalCache(Path(directory) / "history.sqlite", provider)
            self.assertEqual(len(cache.get_bars("sz000001", DAYS[0], DAYS[3])), 4)
            self.assertEqual(len(cache.get_bars("sz000001", DAYS[0], DAYS[-1])), 7)
            self.assertEqual(provider.requests[-1][1:], (DAYS[4], DAYS[-1], "none"))
            cache.get_bars("sz000001", DAYS[0], DAYS[-1])
            self.assertEqual(len(provider.requests), 2)
            self.assertEqual(len(cache.coverage("sz000001", "none")), 2)
            cache.close()

    def test_cache_offline_replay(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            provider = seven_day_provider()
            cache = HistoricalCache(Path(directory) / "history.sqlite", provider)
            cache.get_bars("sz000001", DAYS[0], DAYS[-1])
            provider.bars = {}
            self.assertEqual(len(cache.get_bars("sz000001", DAYS[0], DAYS[-1])), 7)
            self.assertEqual(len(provider.requests), 1)
            cache.close()

    def test_cache_rejects_provider_mixing(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            location = Path(directory) / "history.sqlite"
            cache = HistoricalCache(location, seven_day_provider())
            cache.get_bars("sz000001", DAYS[0], DAYS[1])
            cache.close()
            other = seven_day_provider()
            other.name = "A different provider"
            with self.assertRaises(ValueError):
                HistoricalCache(location, other)

    def test_calendar_weekend_holiday_previous_next(self):
        calendar = ChinaAMarketCalendar(DAYS, DAYS[0], DAYS[-1])
        self.assertFalse(calendar.is_trading_day(date(2025, 1, 4)))
        self.assertFalse(calendar.is_trading_day(date(2025, 1, 5)))
        self.assertTrue(calendar.is_trading_day(date(2025, 1, 6)))
        self.assertEqual(calendar.previous_trading_day(DAYS[2]), DAYS[1])
        self.assertEqual(calendar.next_trading_day(DAYS[1]), DAYS[2])
        self.assertEqual(len(calendar.trading_days(DAYS[1], DAYS[3])), 3)
        with self.assertRaises(UnknownTradingDay):
            calendar.is_trading_day(date(2026, 1, 1))

    def test_calendar_explicit_weekday_holiday_fixture(self):
        sessions = [DAYS[0], DAYS[1], DAYS[3]]
        calendar = ChinaAMarketCalendar(sessions, DAYS[0], DAYS[3])
        self.assertTrue(calendar.is_holiday(DAYS[2]))
        self.assertEqual(calendar.next_trading_day(DAYS[1]), DAYS[3])

    def test_price_limit_profiles_and_unknown(self):
        rule = PriceLimitRule()
        b = bar("sz000001", DAYS[1], 10)
        self.assertFalse(rule.check(b, 10, 10, "unknown", OrderSide.BUY).allowed)
        self.assertTrue(rule.check(b, 10, 10, "main_normal", OrderSide.BUY).allowed)
        self.assertFalse(rule.check(b, 10, 12, "main_normal", OrderSide.BUY).allowed)
        self.assertFalse(rule.check(b, 10, 11.5, "chinext", OrderSide.BUY).allowed)
        self.assertTrue(rule.check(bar("sz300750", DAYS[1], 11.5), 10, 11.5,
                                   "chinext", OrderSide.BUY).allowed)

    def test_limit_open_conservatively_rejects_fill(self):
        rule = PriceLimitRule()
        self.assertFalse(rule.check(bar("sz000001", DAYS[1], 11), 10, 11,
                                    "main_normal", OrderSide.BUY).allowed)

    def test_cost_model_commission_tax_slippage(self):
        costs = TradingCostModel.from_config(config())
        self.assertGreater(costs.fill_price(10, OrderSide.BUY), 10)
        self.assertLess(costs.fill_price(10, OrderSide.SELL), 10)
        self.assertEqual(costs.fees(10, 100, OrderSide.BUY)[0], 5)
        self.assertGreater(costs.fees(10, 100, OrderSide.SELL)[1], 0)


class BacktestTests(unittest.TestCase):
    def setUp(self):
        self.app = config(short_window=2, long_window=3, breakout_window=2,
                          volume_multiplier=1, order_quantity=100)

    def run_basic(self, provider=None, settings=None, params=None):
        return BacktestEngine(provider or seven_day_provider(), settings or self.app).run(params or bt_config())

    def test_signal_after_close_and_next_open_fill(self):
        result = self.run_basic()
        self.assertTrue(result.signals)
        self.assertEqual(result.signals[0].timestamp.date(), DAYS[3])
        self.assertEqual(result.signals[0].timestamp.hour, 15)
        self.assertEqual(result.fills[0].timestamp.date(), DAYS[4])
        self.assertEqual(result.fills[0].timestamp.hour, 9)
        self.assertEqual(result.fills[0].signal_price, 12)
        self.assertGreater(result.fills[0].fill_price, 13)

    def test_buy_sell_t_plus_one_and_trade_record(self):
        result = self.run_basic()
        self.assertEqual([fill.side for fill in result.fills], [OrderSide.BUY, OrderSide.SELL])
        self.assertEqual(len(result.round_trips), 1)
        trip = result.round_trips[0]
        self.assertEqual(trip.quantity, 100)
        self.assertGreater(trip.fees, 0)
        self.assertEqual(trip.holding_period, 2)

    def test_next_session_fill_across_holiday_and_weekend(self):
        dates = [date(2024, 12, 27), date(2024, 12, 30), date(2024, 12, 31),
                 date(2025, 1, 3), date(2025, 1, 6), date(2025, 1, 7), date(2025, 1, 8)]
        prices = (9, 10, 11, 12, 13, 11.8, 10.8)
        provider = FakeHistoricalMarketDataProvider({
            "sz000001": [bar("sz000001", day, price, 1_000_000 + i * 1000)
                         for i, (day, price) in enumerate(zip(dates, prices))],
            "sh000300": [bar("sh000300", day, 100 + i) for i, day in enumerate(dates)],
        })
        result = self.run_basic(provider, params=bt_config(start_date=dates[0], end_date=dates[-1]))
        self.assertEqual([fill.timestamp.date() for fill in result.fills], [dates[4], dates[6]])
        self.assertEqual(result.round_trips[0].holding_period, 2)

    def test_no_lookahead_future_mutation(self):
        first = self.run_basic(seven_day_provider())
        second = self.run_basic(seven_day_provider(prices=(9, 10, 11, 12, 9, 9, 9)))
        earlier_a = [(s.timestamp, s.side, s.reference_price) for s in first.signals if s.timestamp.date() <= DAYS[3]]
        earlier_b = [(s.timestamp, s.side, s.reference_price) for s in second.signals if s.timestamp.date() <= DAYS[3]]
        self.assertEqual(earlier_a, earlier_b)
        self.assertTrue(earlier_a)

    def test_breakout_uses_prior_high_not_future_high(self):
        from src.strategy.trend import TrendBreakoutStrategy
        strategy = TrendBreakoutStrategy(2, 3, 2, 1)
        for i, price in enumerate((9, 10, 11)):
            strategy.on_bar(bar("sz000001", DAYS[i], price, 1_000_000 + i * 1000), False)
        current = MarketBar("sz000001", datetime.combine(DAYS[3], time(15), SHANGHAI),
                            10, 50, 10, 10.5, 1_010_000, 10_500_000)
        self.assertIsNone(strategy.on_bar(current, False))

    def test_warmup_generates_no_pre_start_orders(self):
        result = self.run_basic(params=bt_config(start_date=DAYS[3]))
        self.assertTrue(all(order.created_at.date() > DAYS[3] for order in result.orders))
        self.assertTrue(all(point.timestamp.date() >= DAYS[3] for point in result.equity_curve))

    def test_shared_portfolio_multi_symbol_timeline(self):
        extra = {"sh600519": [bar("sh600519", day, price + 1, 1_000_000 + i * 1000)
                              for i, (day, price) in enumerate(zip(DAYS, (9, 10, 11, 12, 13, 11.8, 10.8)))]}
        params = bt_config(symbols=("sz000001", "sh600519"),
                           security_profiles={"sz000001": "main_normal", "sh600519": "main_normal"})
        result = self.run_basic(seven_day_provider(extra=extra), params=params)
        self.assertEqual(len(result.equity_curve), len(DAYS))
        self.assertEqual(set(fill.symbol for fill in result.fills if fill.side == OrderSide.BUY),
                         {"sz000001", "sh600519"})

    def test_position_sizing_and_total_risk(self):
        settings = replace(self.app, order_quantity=10000, max_total_position=0.01)
        result = self.run_basic(settings=settings)
        self.assertTrue(all(fill.quantity <= 100 for fill in result.fills))

    def test_missing_bar_rejects_deferred_order(self):
        provider = seven_day_provider()
        provider.bars["sz000001"] = [b for b in provider.bars["sz000001"] if b.day != DAYS[4]]
        result = self.run_basic(provider)
        self.assertIn("No bar", result.orders[0].reject_reason)
        self.assertFalse(result.fills)

    def test_zero_volume_rejects_fill(self):
        provider = seven_day_provider()
        provider.bars["sz000001"][4] = bar("sz000001", DAYS[4], 13, 0)
        result = self.run_basic(provider)
        self.assertIn("zero-volume", result.orders[0].reject_reason)

    def test_unknown_profile_rejects_fill(self):
        result = self.run_basic(params=bt_config(security_profiles={}))
        self.assertIn("Price limit unavailable", result.orders[0].reject_reason)

    def test_insufficient_cash_rejects(self):
        result = self.run_basic(params=bt_config(initial_cash=1000))
        self.assertFalse(result.fills)
        self.assertIn("sizing", result.orders[0].reject_reason)

    def test_equity_benchmark_and_drawdown(self):
        result = self.run_basic()
        self.assertEqual(len(result.equity_curve), len(DAYS))
        self.assertGreater(result.equity_curve[-1].benchmark_equity, result.config.initial_cash)
        self.assertLessEqual(result.performance["max_drawdown"], 0)
        self.assertIn("peak_date", result.performance)

    def test_repeatability(self):
        provider = seven_day_provider()
        first = self.run_basic(provider)
        second = self.run_basic(provider)
        self.assertEqual(first.run_id, second.run_id)
        self.assertEqual(first.performance, second.performance)
        self.assertEqual(first.fills, second.fills)

    def test_cancel_before_result(self):
        cancelled = threading.Event()
        cancelled.set()
        with self.assertRaises(BacktestCancelled):
            BacktestEngine(seven_day_provider(), self.app).run(bt_config(), cancelled)

    def test_result_persistence_and_export(self):
        result = self.run_basic()
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            store = BacktestRunStore(Path(directory) / "runs.sqlite")
            store.save(result)
            self.assertEqual(store.count(), 1)
            store.close()
            target = export_result(result, Path(directory) / "exports" / result.run_id)
            self.assertTrue((target / "trades.csv").exists())
            self.assertEqual(len((target / "equity_curve.csv").read_text(encoding="utf-8-sig").splitlines()),
                             len(DAYS) + 1)
            self.assertEqual(json.loads((target / "summary.json").read_text(encoding="utf-8"))["run_id"], result.run_id)

    def test_export_rejects_outside_project(self):
        with self.assertRaises(ValueError):
            export_result(self.run_basic(), Path("C:/outside"))


class PerformanceTests(unittest.TestCase):
    def test_metrics_values_and_missing_sharpe(self):
        day = datetime.combine(DAYS[0], time(15), SHANGHAI)
        curve = [EquityPoint(day + timedelta(days=i), 100, 0, equity, drawdown, 100)
                 for i, (equity, drawdown) in enumerate(((100, 0), (110, 0), (90, -0.181818)))]
        p = PerformanceAnalyzer(0.02, 252).analyze(100, curve, [])
        self.assertAlmostEqual(p["total_return"], -0.1)
        self.assertAlmostEqual(p["max_drawdown"], -0.181818)
        self.assertIsNotNone(p["volatility"])
        self.assertIsNotNone(p["sharpe"])
        self.assertIsNone(PerformanceAnalyzer().analyze(100, curve[:1], [])["sharpe"])

    def test_win_rate_profit_factor_and_holding_period(self):
        at = datetime.combine(DAYS[0], time(15), SHANGHAI)
        curve = [EquityPoint(at, 100, 0, 100, 0, 100),
                 EquityPoint(at + timedelta(days=1), 110, 0, 110, 0, 100)]
        trades = [RoundTrip("a", at, 10, at, 12, 100, 10, 200, 190, .19, 2, "test"),
                  RoundTrip("b", at, 10, at, 9, 100, 10, -100, -110, -.11, 3, "test")]
        p = PerformanceAnalyzer().analyze(100, curve, trades)
        self.assertEqual(p["win_rate"], .5)
        self.assertAlmostEqual(p["profit_factor"], 190 / 110)
        self.assertEqual(p["average_holding_period"], 2.5)
