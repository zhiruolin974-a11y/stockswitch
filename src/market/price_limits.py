from __future__ import annotations

from dataclasses import dataclass

from src.market.historical import MarketBar
from src.trading.models import OrderSide


PROFILE_LIMITS = {"main_normal": 0.10, "main_st": 0.05, "chinext": 0.20, "star": 0.20}


@dataclass(frozen=True)
class PriceLimitDecision:
    allowed: bool
    reason: str


class PriceLimitRule:
    """Explicit security profile is required; a ticker alone cannot identify ST/IPO state."""

    def check(self, bar: MarketBar, previous_close: float | None, fill_price: float, profile: str,
              side: OrderSide) -> PriceLimitDecision:
        if profile not in PROFILE_LIMITS:
            return PriceLimitDecision(False, "Price limit unavailable: explicit verified security profile required")
        main_board = bar.symbol.startswith(("sh600", "sh601", "sh603", "sh605", "sz000", "sz001", "sz002", "sz003"))
        if ((profile in ("main_normal", "main_st") and not main_board)
                or (profile == "chinext" and not bar.symbol.startswith(("sz300", "sz301")))
                or (profile == "star" and not bar.symbol.startswith("sh688"))):
            return PriceLimitDecision(False, "Security profile does not match ticker board")
        if previous_close is None or previous_close <= 0:
            return PriceLimitDecision(False, "Price limit unavailable: previous close missing")
        limit = PROFILE_LIMITS[profile]
        lower, upper = previous_close * (1 - limit), previous_close * (1 + limit)
        if not lower - 0.011 <= fill_price <= upper + 0.011:
            return PriceLimitDecision(False, f"Fill price outside {profile} {limit:.0%} limit")
        if side == OrderSide.BUY and bar.open >= upper - 0.011:
            return PriceLimitDecision(False, "Opening at upper price limit: fill not assumed")
        if side == OrderSide.SELL and bar.open <= lower + 0.011:
            return PriceLimitDecision(False, "Opening at lower price limit: fill not assumed")
        return PriceLimitDecision(True, "Price within configured limit profile")
