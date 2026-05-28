"""按 TRADING_MODE 返回执行器。"""

from config.trading import is_live_mode
from trading.execution.base import BaseExecutor
from trading.execution.live import LiveExecutor
from trading.execution.paper import PaperExecutor


def get_executor() -> BaseExecutor:
    if is_live_mode():
        return LiveExecutor()
    return PaperExecutor()
