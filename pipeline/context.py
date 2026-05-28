from dataclasses import dataclass, field


@dataclass
class TradePipelineContext:
    source_key: str
    decision: dict
    market_price: float
    previous_price: float | None
    market_state: dict
    market_candidate: dict
    direction_adjustment: dict
    signal: dict
    alpha: dict
    narrative: dict
    underlying_asset: str = "BTCUSDT"
    last_trade_action: str | None = None


@dataclass
class TradePipelineResult:
    opened_position: dict | None = None
    skip_signal_send: bool = False
    last_trade_action: str | None = None
    trade_size: float | None = None
