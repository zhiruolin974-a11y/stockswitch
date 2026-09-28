from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import asdict, replace
from datetime import date, datetime, time, timedelta
from typing import Callable

from src.analytics.performance import PerformanceAnalyzer
from src.app.config import AppConfig
from src.backtest.models import BacktestConfig, BacktestResult, EquityPoint, RoundTrip
from src.broker.backtest import BacktestBroker
from src.broker.costs import TradingCostModel
from src.market.calendar import ChinaAMarketRules, SHANGHAI
from src.market.historical import HistoricalMarketDataProvider, InvalidHistoricalData, MarketBar, validate_bars
from src.market.models import MarketQuote
from src.market.trading_calendar import ChinaAMarketCalendar
from src.market.tencent import validate_symbol
from src.portfolio.portfolio import Portfolio
from src.risk.manager import RiskManager
from src.strategy.trend import TrendBreakoutStrategy
from src.trading.models import Order, OrderSide, OrderStatus, TradingSignal


class BacktestCancelled(RuntimeError):
    pass


class BacktestEngine:
    def __init__(self, provider: HistoricalMarketDataProvider, app_config: AppConfig):
        self.provider = provider
        self.app_config = app_config

    def run(self, config: BacktestConfig, cancel: threading.Event | None = None,
            progress: Callable[[int, str], None] | None = None) -> BacktestResult:
        stopped = cancel or threading.Event()
        report = progress or (lambda percent, stage: None)

        def check_cancel():
            if stopped.is_set():
                raise BacktestCancelled("Backtest cancelled; no result was saved")

        symbols = tuple(dict.fromkeys(validate_symbol(symbol) for symbol in config.symbols))
        benchmark = validate_symbol(config.benchmark, allow_index=True)
        warm_days = max(self.app_config.long_window, self.app_config.breakout_window) * 3 + 15
        warm_start = config.start_date - timedelta(days=warm_days)
        all_symbols = tuple(dict.fromkeys((*symbols, benchmark)))
        history: dict[str, list[MarketBar]] = {}
        report(0, "Loading historical daily bars")
        for index, symbol in enumerate(all_symbols):
            check_cancel()
            bars = self.provider.get_bars(symbol, warm_start, config.end_date, config.adjustment)
            validate_bars(bars, symbol, config.adjustment)
            if not bars:
                raise InvalidHistoricalData(f"{symbol}: no historical bars in requested period")
            history[symbol] = bars
            report(int((index + 1) / len(all_symbols) * 30), f"Loaded {symbol}")
        check_cancel()
        benchmark_bars = history[benchmark]
        if not benchmark_bars:
            raise InvalidHistoricalData("Benchmark has no observed sessions")
        calendar = ChinaAMarketCalendar([bar.day for bar in benchmark_bars], warm_start, config.end_date)
        sessions = calendar.trading_days(config.start_date, config.end_date)
        if not sessions:
            raise InvalidHistoricalData("No verified trading sessions in requested range")
        benchmark_by_day = {bar.day: bar for bar in benchmark_bars}
        if any(day not in benchmark_by_day for day in sessions):
            raise InvalidHistoricalData("Benchmark missing a trading session")
        by_symbol = {symbol: {bar.day: bar for bar in history[symbol]} for symbol in symbols}
        for symbol in symbols:
            if any(bar.day not in benchmark_by_day for bar in history[symbol]):
                raise InvalidHistoricalData(f"{symbol}: trading date absent from benchmark calendar")
        data_hash = hashlib.sha256(json.dumps(
            {symbol: [asdict(bar) for bar in bars] for symbol, bars in history.items()},
            default=str, sort_keys=True).encode()).hexdigest()
        settings = replace(self.app_config, initial_cash=config.initial_cash)
        signature = json.dumps({"data": data_hash, "config": asdict(config), "settings": asdict(settings)},
                               sort_keys=True, default=str)
        run_id = hashlib.sha256(signature.encode()).hexdigest()[:20]
        portfolio = Portfolio(config.initial_cash)
        broker = BacktestBroker(settings, portfolio, config.security_profiles)
        risk = RiskManager(settings, ChinaAMarketRules(calendar))
        strategy = TrendBreakoutStrategy(settings.short_window, settings.long_window,
                                         settings.breakout_window, settings.volume_multiplier)
        signals: list[TradingSignal] = []
        risk_decisions: list[tuple[str, str, bool, str]] = []
        pending: dict[str, TradingSignal] = {}
        last_close: dict[str, float] = {}
        entries: dict[str, tuple] = {}
        round_trips: list[RoundTrip] = []
        equity_curve: list[EquityPoint] = []
        peak = config.initial_cash
        first_benchmark_close = benchmark_by_day[sessions[0]].close
        session_index = {day: i for i, day in enumerate(sessions)}

        # Warmup bars are observed chronologically but generate no orders or PnL.
        for day in calendar.trading_days(warm_start, config.start_date - timedelta(days=1)):
            check_cancel()
            for symbol in symbols:
                bar = by_symbol[symbol].get(day)
                if bar:
                    strategy.on_bar(bar, False)
                    last_close[symbol] = bar.close

        for day_number, day in enumerate(sessions):
            check_cancel()
            portfolio.roll_day(day)
            open_time = datetime.combine(day, time(9, 30), SHANGHAI)
            close_time = datetime.combine(day, time(15), SHANGHAI)
            for held_symbol in portfolio.positions:
                opening_bar = by_symbol[held_symbol].get(day)
                if opening_bar and opening_bar.volume > 0:
                    portfolio.mark(held_symbol, opening_bar.open)
            stale_held_position = any(
                by_symbol[held_symbol].get(day) is None or by_symbol[held_symbol][day].volume <= 0
                for held_symbol in portfolio.positions)
            # Yesterday's signals are evaluated at today's open. The broker sees
            # open/volume for tradability, never today's close/high/low for price.
            for symbol in sorted(pending):
                check_cancel()
                signal = pending[symbol]
                bar = by_symbol[symbol].get(day)
                quantity = (portfolio.positions[symbol].available_quantity
                            if signal.side == OrderSide.SELL and symbol in portfolio.positions
                            else settings.order_quantity)
                if signal.side == OrderSide.BUY:
                    current_value = portfolio.positions[symbol].market_value if symbol in portfolio.positions else 0
                    budget = min(portfolio.total_equity * settings.max_order_fraction,
                                 portfolio.total_equity * settings.max_single_position - current_value,
                                 portfolio.total_equity * settings.max_total_position - portfolio.market_value,
                                 portfolio.available_cash)
                    estimated_price = TradingCostModel.from_config(settings).fill_price(
                        bar.open if bar else signal.reference_price, OrderSide.BUY)
                    budget_lots = max(0, int((budget - settings.minimum_commission) /
                                             estimated_price // settings.lot_size))
                    quantity = min(quantity, budget_lots * settings.lot_size)
                order = Order(symbol, signal.side, quantity, signal.reference_price, open_time, signal.strategy,
                              id=f"{run_id}-{day.isoformat()}-{symbol}-{signal.side.value}")
                if bar is None:
                    order.status = OrderStatus.REJECTED
                    order.reject_reason = "No bar on benchmark trading day: suspended or missing data"
                    broker.orders.append(order)
                    risk_decisions.append((day.isoformat(), symbol, False, order.reject_reason))
                    continue
                if stale_held_position:
                    order.status = OrderStatus.REJECTED
                    order.reject_reason = "Held position market data unavailable at open"
                    broker.orders.append(order)
                    risk_decisions.append((day.isoformat(), symbol, False, order.reject_reason))
                    continue
                if quantity <= 0:
                    order.status = OrderStatus.REJECTED
                    order.reject_reason = "Position sizing below one legal lot"
                    broker.orders.append(order)
                    risk_decisions.append((day.isoformat(), symbol, False, order.reject_reason))
                    continue
                previous = last_close.get(symbol)
                open_quote = MarketQuote(symbol, symbol, open_time, open_time, bar.open, bar.open,
                                         bar.open, bar.open, previous or bar.open, 0, 0, 0, 0,
                                         "Backtest next daily open", True)
                decision = risk.assess(signal, quantity, open_quote, portfolio, open_time, deferred=True)
                risk_decisions.append((day.isoformat(), symbol, decision.accepted, decision.reason))
                if not decision.accepted:
                    order.status = OrderStatus.REJECTED
                    order.reject_reason = decision.reason
                    broker.orders.append(order)
                    continue
                fill, trade = broker.submit_at_open(order, bar, previous, open_time)
                if fill and trade:
                    if fill.side == OrderSide.BUY:
                        entries[symbol] = (fill, day_number, signal.strategy)
                    elif symbol in entries:
                        entry, entry_index, entry_strategy = entries.pop(symbol)
                        gross = (fill.fill_price - entry.fill_price) * fill.quantity
                        fees = entry.commission + entry.stamp_tax + fill.commission + fill.stamp_tax
                        net = gross - fees
                        round_trips.append(RoundTrip(symbol, entry.timestamp, entry.fill_price,
                            fill.timestamp, fill.fill_price, fill.quantity, fees, gross, net,
                            net / (entry.fill_price * fill.quantity + entry.commission),
                            day_number - entry_index, entry_strategy))
            pending.clear()
            for symbol in symbols:
                bar = by_symbol[symbol].get(day)
                if bar:
                    portfolio.mark(symbol, bar.close)
                    # Current completed bar is visible at its close, never earlier.
                    signal = strategy.on_bar(bar, symbol in portfolio.positions)
                    if signal:
                        signals.append(signal)
                        pending[symbol] = signal
                    last_close[symbol] = bar.close
            equity = portfolio.total_equity
            peak = max(peak, equity)
            benchmark_equity = config.initial_cash * benchmark_by_day[day].close / first_benchmark_close
            equity_curve.append(EquityPoint(close_time, portfolio.available_cash, portfolio.market_value,
                                            equity, equity / peak - 1, benchmark_equity))
            report(30 + int((day_number + 1) / len(sessions) * 70), f"Processed {day}")
        check_cancel()
        performance = PerformanceAnalyzer(config.risk_free_rate, config.annualization_factor).analyze(
            config.initial_cash, equity_curve, round_trips)
        return BacktestResult(run_id, datetime.now(SHANGHAI), config, self.provider.name,
                              warm_start, config.end_date, data_hash, strategy.name,
                              {"short_window": settings.short_window, "long_window": settings.long_window,
                               "breakout_window": settings.breakout_window,
                               "volume_multiplier": settings.volume_multiplier,
                               "order_quantity": settings.order_quantity},
                              asdict(TradingCostModel.from_config(settings)), equity_curve,
                              broker.orders, broker.fills, broker.trades, round_trips, signals,
                              risk_decisions, performance)
