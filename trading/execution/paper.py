"""Paper 执行器：封装 intel.paper_trading。"""

from intel.paper_trading import (
    execute_virtual_trade,
    has_open_exposure,
    update_positions,
)
from trading.execution.base import BaseExecutor


class PaperExecutor(BaseExecutor):
    mode = "paper"

    def open_position(self, decision, price, symbol, size_usd, metadata=None):
        return execute_virtual_trade(
            decision,
            price,
            symbol,
            metadata=metadata,
            size_override=size_usd,
        )

    def update_positions(self, current_price, symbol):
        return update_positions(current_price, symbol)

    def has_open_exposure(self, underlying_asset, action) -> bool:
        return has_open_exposure(underlying_asset, action)
