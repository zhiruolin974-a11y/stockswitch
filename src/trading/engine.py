from __future__ import annotations

import logging
from datetime import datetime

from src.app.config import AppConfig
from src.broker.paper import PaperBroker
from src.market.calendar import ChinaAMarketRules, SHANGHAI
from src.market.models import MarketDataError, MarketQuote
from src.market.provider import MarketDataProvider
from src.portfolio.portfolio import Portfolio
from src.risk.manager import RiskDecision, RiskManager
from src.storage.journal import TradeJournal
from src.strategy.trend import TrendBreakoutStrategy
from src.trading.models import Order, OrderSide, TradingSignal


LOG = logging.getLogger(__name__)


class TradingEngine:
    def __init__(self, provider: MarketDataProvider, config: AppConfig, journal: TradeJournal,
                 rules: ChinaAMarketRules | None = None):
        self.provider = provider
        self.config = config
        self.journal = journal
        self.rules = rules or ChinaAMarketRules()
        self.portfolio: Portfolio = journal.load_portfolio(config.initial_cash)
        self.broker = PaperBroker(config, self.portfolio)
        self.risk = RiskManager(config, self.rules)
        self.strategy = TrendBreakoutStrategy(config.short_window, config.long_window, config.breakout_window, config.volume_multiplier)
        self.watchlist = list(dict.fromkeys(config.watchlist))
        self.latest_quotes: dict[str, MarketQuote] = {}
        self.latest_indexes: dict[str, MarketQuote] = {}
        self.connected = False
        self.stale = True
        self.last_update: datetime | None = None
        self.events: list[str] = []
        # The GUI can pause/resume simulated strategy signals without changing
        # the immutable startup configuration or the RiskManager order path.
        self.strategy_enabled = config.strategy_enabled
        self.event_records: list[dict] = []

    def set_strategy_enabled(self, enabled: bool) -> None:
        self.strategy_enabled = bool(enabled)

    def connect(self) -> None:
        self.provider.connect()
        self.connected = True

    def disconnect(self) -> None:
        self.provider.disconnect()
        self.connected = False
        self.stale = True

    def add_symbol(self, symbol: str) -> None:
        from src.market.tencent import validate_symbol
        normalized = validate_symbol(symbol)
        if normalized not in self.watchlist:
            if len(self.watchlist) >= 8:
                raise ValueError("Watchlist is limited to eight stocks")
            self.watchlist.append(normalized)

    def remove_symbol(self, symbol: str) -> None:
        if symbol in self.portfolio.positions:
            raise ValueError("Cannot remove a stock with an open paper position")
        self.watchlist.remove(symbol)
        self.latest_quotes.pop(symbol, None)

    def poll(self, now: datetime | None = None) -> None:
        at = now or datetime.now(SHANGHAI)
        self.portfolio.roll_day(at.astimezone(SHANGHAI).date())
        try:
            symbols = list(self.watchlist) + ["sh000001", "sz399001", "sz399006", "sh000300"]
            quotes = self.provider.get_quotes(symbols)
            self.latest_indexes = {symbol: quotes[symbol] for symbol in symbols[-4:]}
            self.latest_quotes = {symbol: quotes[symbol] for symbol in self.watchlist}
            self.last_update = at
            self.connected = True
            self.stale = False
            for symbol, quote in self.latest_quotes.items():
                self.portfolio.mark(symbol, quote.last_price)
                try:
                    quote.require_fresh(at, self.config.max_quote_age_seconds)
                except MarketDataError:
                    self.stale = True
            if self.rules.can_trade(at) and not self.stale and self.strategy_enabled:
                for symbol, quote in self.latest_quotes.items():
                    signal = self.strategy.on_quote(quote, symbol in self.portfolio.positions)
                    if signal:
                        quantity = (self.portfolio.positions[symbol].available_quantity if signal.side == OrderSide.SELL
                                    else self.config.order_quantity)
                        if quantity > 0:
                            self.process_signal(signal, quantity, at)
            self.journal.record_snapshot(self.portfolio, at)
        except (MarketDataError, ValueError, KeyError) as exc:
            self.connected = False
            self.stale = True
            self.events.append(f"Disconnected / Data Stale: {exc}")
            LOG.warning("Market polling failed: %s", exc)
            raise

    def process_signal(self, signal: TradingSignal, quantity: int, at: datetime | None = None) -> tuple[Order, RiskDecision]:
        now = at or datetime.now(SHANGHAI)
        self.journal.record_signal(signal)
        quote = self.latest_quotes.get(signal.symbol)
        if not self.connected or self.stale or quote is None:
            decision = RiskDecision(False, "Disconnected / Data Stale")
        else:
            decision = self.risk.assess(signal, quantity, quote, self.portfolio, now)
        self.journal.record_risk(now, signal.symbol, decision.accepted, decision.reason)
        order = Order(signal.symbol, signal.side, quantity, signal.reference_price, now, signal.strategy)
        if not decision.accepted:
            order.status = order.status.REJECTED
            order.reject_reason = decision.reason
        else:
            fill, trade = self.broker.submit_order(order, quote, now)
            if fill and trade:
                self.journal.record_execution(fill, trade)
                self.journal.record_snapshot(self.portfolio, now)
        self.journal.record_order(order)
        event = f"{signal.strategy} {signal.side.value} {signal.symbol}: {order.status.value} ({decision.reason})"
        self.events.append(event)
        self.event_records.append({
            "timestamp": now,
            "symbol": signal.symbol,
            "side": signal.side,
            "strategy": signal.strategy,
            "reference_price": signal.reference_price,
            "signal_reason": signal.reason,
            "reason": order.reject_reason or decision.reason,
            "status": order.status,
        })
        if len(self.event_records) > 100:
            del self.event_records[:-100]
        LOG.info("Signal and risk: %s", event)
        return order, decision

    def manual_paper_order(self, symbol: str, side: OrderSide, quantity: int, at: datetime | None = None) -> tuple[Order, RiskDecision]:
        quote = self.latest_quotes.get(symbol)
        now = at or datetime.now(SHANGHAI)
        if quote is None:
            signal = TradingSignal("Manual Paper", symbol, now, side, 1.0, "User paper order", 0)
        else:
            signal = TradingSignal("Manual Paper", symbol, quote.timestamp, side, 1.0, "User paper order", quote.last_price)
        return self.process_signal(signal, quantity, now)
