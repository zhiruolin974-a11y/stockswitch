from __future__ import annotations

from abc import ABC, abstractmethod

from src.market.models import MarketQuote


INDEX_SYMBOLS = ("sh000001", "sz399001", "sz399006", "sh000300")


class MarketDataProvider(ABC):
    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def get_quote(self, symbol: str) -> MarketQuote: ...

    @abstractmethod
    def get_quotes(self, symbols: list[str] | tuple[str, ...]) -> dict[str, MarketQuote]: ...

    def get_index_quotes(self) -> dict[str, MarketQuote]:
        return self.get_quotes(INDEX_SYMBOLS)

    @abstractmethod
    def health(self) -> bool: ...
