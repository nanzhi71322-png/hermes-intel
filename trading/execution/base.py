from abc import ABC, abstractmethod


class BaseExecutor(ABC):
    mode: str = "unknown"

    @abstractmethod
    def open_position(self, decision, price, symbol, size_usd, metadata=None):
        raise NotImplementedError

    @abstractmethod
    def update_positions(self, current_price, symbol):
        raise NotImplementedError

    @abstractmethod
    def has_open_exposure(self, underlying_asset, action) -> bool:
        raise NotImplementedError
