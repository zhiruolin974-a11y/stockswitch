from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.app.config import AppConfig
from src.market.calendar import ChinaAMarketRules
from src.market.models import MarketQuote
from src.portfolio.portfolio import Portfolio
from src.trading.models import OrderSide, TradingSignal


@dataclass(frozen=True)
class RiskDecision:
    accepted: bool
    reason: str


class RiskManager:
    def __init__(self, config: AppConfig, rules: ChinaAMarketRules):
        self.config = config
        self.rules = rules

    def assess(self, signal: TradingSignal, quantity: int, quote: MarketQuote, portfolio: Portfolio, now: datetime) -> RiskDecision:
        def reject(reason: str) -> RiskDecision:
            return RiskDecision(False, reason)

        if not self.rules.can_trade(now):
            return reject("A-share market is not open")
        if signal.side not in (OrderSide.BUY, OrderSide.SELL):
            return reject("Only BUY and SELL can become orders")
        if signal.symbol != quote.symbol or signal.timestamp != quote.timestamp or signal.reference_price != quote.last_price:
            return reject("Signal does not match current market quote")
        try:
            quote.require_fresh(now, self.config.max_quote_age_seconds)
        except Exception as exc:
            return reject(f"Data stale: {exc}")
        if quantity <= 0 or quantity % self.config.lot_size:
            return reject(f"Quantity must be a positive multiple of {self.config.lot_size}")
        if portfolio.daily_pnl <= -portfolio.day_start_equity * self.config.max_daily_loss:
            return reject("Daily virtual loss limit reached")
        position = portfolio.positions.get(signal.symbol)
        if signal.side == OrderSide.SELL:
            if not self.config.allow_sell:
                return reject("Selling disabled by configuration")
            if not position or quantity > position.available_quantity:
                return reject("Insufficient T+1 available holdings")
            return RiskDecision(True, "Sell allowed")
        if not self.config.allow_buy:
            return reject("Buying disabled by configuration")
        estimated_price = quote.last_price * (1 + self.config.slippage_bps / 10000)
        estimated_fee = max(quantity * estimated_price * self.config.commission_rate, self.config.minimum_commission)
        estimated_cost = quantity * estimated_price + estimated_fee
        equity = portfolio.total_equity
        if estimated_cost > portfolio.available_cash:
            return reject("Insufficient virtual cash")
        if estimated_cost > equity * self.config.max_order_fraction:
            return reject("Single order limit exceeded")
        current_value = position.market_value if position else 0
        if current_value + estimated_cost > equity * self.config.max_single_position:
            return reject("Single position limit exceeded")
        if portfolio.market_value + estimated_cost > equity * self.config.max_total_position:
            return reject("Total position limit exceeded")
        return RiskDecision(True, "Buy allowed")
