from __future__ import annotations

from collections import deque

from src.market.models import MarketDataError, MarketQuote
from src.market.provider import MarketDataProvider


class FakeMarketDataProvider(MarketDataProvider):
    def __init__(self, frames: list[dict[str, MarketQuote]], *, fail_at: int | None = None):
        if not frames:
            raise ValueError("At least one deterministic frame is required")
        self._frames = deque(frames)
        self._current = frames[0]
        self._reads = 0
        self._fail_at = fail_at
        self._connected = False

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def health(self) -> bool:
        return self._connected and (self._fail_at is None or self._reads < self._fail_at)

    def advance(self) -> None:
        if len(self._frames) > 1:
            self._frames.popleft()
        self._current = self._frames[0]

    def get_quotes(self, symbols: list[str] | tuple[str, ...]) -> dict[str, MarketQuote]:
        if not self.health():
            raise MarketDataError("Fake provider disconnected or deliberately failed")
        self._reads += 1
        try:
            return {symbol: self._current[symbol] for symbol in symbols}
        except KeyError as exc:
            raise MarketDataError(f"No fake quote for {exc.args[0]}") from exc

    def get_quote(self, symbol: str) -> MarketQuote:
        return self.get_quotes([symbol])[symbol]
