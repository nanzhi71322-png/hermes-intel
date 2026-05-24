"""回测虚拟持仓 — 对齐 paper_trading 开平仓规则。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Position:
    """单笔虚拟持仓。"""

    entry_bar: int
    entry_price: float
    size: float
    side: str
    symbol: str


@dataclass
class ClosedTrade:
    """已平仓交易记录。"""

    side: str
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    pnl_pct: float
    entry_bar: int
    exit_bar: int
    reason: str


@dataclass
class BacktestPortfolio:
    """回测账户状态。"""

    balance: float
    max_positions: int = 3
    positions: list[Position] = field(default_factory=list)
    closed_trades: list[ClosedTrade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)

    def open_position(
        self,
        side: str,
        price: float,
        bar_index: int,
        size_pct: float,
        symbol: str,
        slippage_pct: float = 0.0,
    ) -> Optional[Position]:
        """开仓，扣除滑点。"""
        if len(self.positions) >= self.max_positions or self.balance <= 0:
            return None
        if self._has_same_side(symbol, side):
            return None

        size = min(self.balance * size_pct, self.balance)
        if size <= 0:
            return None

        fill = price * (1 + slippage_pct) if side == "long" else price * (1 - slippage_pct)
        pos = Position(entry_bar=bar_index, entry_price=fill, size=size, side=side, symbol=symbol)
        self.positions.append(pos)
        return pos

    def _has_same_side(self, symbol: str, side: str) -> bool:
        return any(p.symbol == symbol and p.side == side for p in self.positions)

    def update(
        self,
        price: float,
        bar_index: int,
        tp_pct: float,
        sl_pct: float,
        ttl_bars: int,
        min_hold_bars: int,
        fee_rate: float,
        slippage_pct: float = 0.0,
    ) -> None:
        """逐 bar 检查止盈/止损/TTL。"""
        remaining: list[Position] = []
        for pos in self.positions:
            held = bar_index - pos.entry_bar
            if held < min_hold_bars:
                remaining.append(pos)
                continue

            if pos.side == "long":
                pnl_pct = (price - pos.entry_price) / pos.entry_price
            else:
                pnl_pct = (pos.entry_price - price) / pos.entry_price

            reason = None
            if pnl_pct >= tp_pct:
                reason = "take_profit"
            elif pnl_pct <= -sl_pct:
                reason = "stop_loss"
            elif held >= ttl_bars:
                reason = "ttl"

            if reason:
                exit_price = price * (1 - slippage_pct) if pos.side == "long" else price * (1 + slippage_pct)
                gross = pos.size * pnl_pct
                fee = pos.size * fee_rate * 2
                net = gross - fee
                self.balance = max(0.0, self.balance + net)
                self.closed_trades.append(
                    ClosedTrade(
                        side=pos.side,
                        entry_price=pos.entry_price,
                        exit_price=exit_price,
                        size=pos.size,
                        pnl=net,
                        pnl_pct=pnl_pct,
                        entry_bar=pos.entry_bar,
                        exit_bar=bar_index,
                        reason=reason,
                    )
                )
            else:
                remaining.append(pos)

        self.positions = remaining
        unrealized = sum(self._unrealized(p, price) for p in self.positions)
        self.equity_curve.append(self.balance + unrealized)

    def _unrealized(self, pos: Position, price: float) -> float:
        if pos.side == "long":
            return pos.size * (price - pos.entry_price) / pos.entry_price
        return pos.size * (pos.entry_price - price) / pos.entry_price
