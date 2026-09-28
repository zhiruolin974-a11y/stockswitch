from __future__ import annotations

from dataclasses import dataclass

from src.app.config import AppConfig
from src.trading.models import OrderSide


@dataclass(frozen=True)
class TradingCostModel:
    slippage_bps: float
    commission_rate: float
    minimum_commission: float
    stamp_tax_rate: float

    @classmethod
    def from_config(cls, config: AppConfig) -> "TradingCostModel":
        return cls(config.slippage_bps, config.commission_rate, config.minimum_commission, config.stamp_tax_rate)

    def fill_price(self, reference_price: float, side: OrderSide) -> float:
        direction = 1 if side == OrderSide.BUY else -1
        return round(reference_price * (1 + direction * self.slippage_bps / 10000), 4)

    def fees(self, price: float, quantity: int, side: OrderSide) -> tuple[float, float]:
        amount = price * quantity
        commission = round(max(amount * self.commission_rate, self.minimum_commission), 2)
        stamp_tax = round(amount * self.stamp_tax_rate, 2) if side == OrderSide.SELL else 0.0
        return commission, stamp_tax
