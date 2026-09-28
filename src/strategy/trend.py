from __future__ import annotations

from collections import defaultdict, deque

from src.market.models import MarketQuote
from src.trading.models import OrderSide, TradingSignal


class TrendBreakoutStrategy:
    """Demonstration only; sampled snapshots are not exchange bars."""

    name = "TrendBreakoutStrategy"

    def __init__(self, short_window: int, long_window: int, breakout_window: int, volume_multiplier: float):
        self.short_window = short_window
        self.long_window = long_window
        self.breakout_window = breakout_window
        self.volume_multiplier = volume_multiplier
        self.history: dict[str, deque[MarketQuote]] = defaultdict(lambda: deque(maxlen=max(long_window, breakout_window) + 1))

    def on_quote(self, quote: MarketQuote, has_position: bool) -> TradingSignal | None:
        samples = self.history[quote.symbol]
        if samples and quote.timestamp <= samples[-1].timestamp:
            return None
        samples.append(quote)
        if len(samples) < max(self.long_window, self.breakout_window) + 1:
            return None
        prior = list(samples)[:-1]
        short_ma = sum(item.last_price for item in prior[-self.short_window:]) / self.short_window
        long_ma = sum(item.last_price for item in prior[-self.long_window:]) / self.long_window
        prior_high = max(item.high for item in prior[-self.breakout_window:])
        volumes = [max(0, right.volume - left.volume) for left, right in zip(prior[-self.short_window - 1:-1], prior[-self.short_window:])]
        current_volume = max(0, quote.volume - prior[-1].volume)
        average_volume = sum(volumes) / len(volumes) if volumes else 0
        if has_position and (quote.last_price < short_ma or short_ma <= long_ma):
            side, reason = OrderSide.SELL, "Trend exit: price or moving averages weakened"
        elif not has_position and short_ma > long_ma and quote.last_price > prior_high and average_volume > 0 and current_volume >= average_volume * self.volume_multiplier:
            side, reason = OrderSide.BUY, "MA trend, prior-high breakout and volume filter"
        else:
            return None
        return TradingSignal(self.name, quote.symbol, quote.timestamp, side, 1.0, reason, quote.last_price)
