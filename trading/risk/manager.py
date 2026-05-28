"""Live 模式最小风控。"""

from config.trading import MAX_DAILY_LOSS_USD, MAX_POSITION_USD, is_live_mode


class RiskManager:
    def __init__(
        self,
        max_position_usd: float | None = None,
        max_daily_loss_usd: float | None = None,
        allow_spot_short: bool = False,
    ):
        self.max_position_usd = max_position_usd or MAX_POSITION_USD
        self.max_daily_loss_usd = max_daily_loss_usd or MAX_DAILY_LOSS_USD
        self.allow_spot_short = allow_spot_short
        self._daily_pnl = 0.0

    def check_open_allowed(self, decision, size_usd) -> tuple[bool, str]:
        action = decision.get("action")
        if action not in ("long", "short"):
            return False, "action is not tradeable"

        if is_live_mode() and action == "short" and not self.allow_spot_short:
            return False, "spot short blocked in live mode"

        if size_usd is None or size_usd <= 0:
            return False, "invalid trade size"

        if size_usd > self.max_position_usd:
            return False, f"size exceeds max_position_usd={self.max_position_usd}"

        if self._daily_pnl <= -abs(self.max_daily_loss_usd):
            return False, f"daily loss limit reached ({self.max_daily_loss_usd})"

        return True, "risk check passed"
