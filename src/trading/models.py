from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import uuid4


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class OrderStatus(str, Enum):
    NEW = "NEW"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class TradingSignal:
    strategy: str
    symbol: str
    timestamp: datetime
    side: OrderSide
    strength: float
    reason: str
    reference_price: float


@dataclass
class Order:
    symbol: str
    side: OrderSide
    quantity: int
    signal_price: float
    created_at: datetime
    strategy: str
    id: str = field(default_factory=lambda: uuid4().hex)
    status: OrderStatus = OrderStatus.NEW
    reject_reason: str = ""
    order_price: float = 0.0


@dataclass(frozen=True)
class Fill:
    order_id: str
    symbol: str
    side: OrderSide
    quantity: int
    signal_price: float
    order_price: float
    fill_price: float
    slippage: float
    commission: float
    stamp_tax: float
    timestamp: datetime


@dataclass(frozen=True)
class Trade:
    order_id: str
    symbol: str
    side: OrderSide
    quantity: int
    price: float
    fees: float
    realized_pnl: float
    timestamp: datetime
