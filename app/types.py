from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class TickLiquidity:
    lower_tick: int
    upper_tick: int
    liquidity: int
    token0_reserves: float
    token1_reserves: float

    @property
    def width(self) -> int:
        return self.upper_tick - self.lower_tick


@dataclass
class LiquidityDeltaEvent:
    tx_hash: str
    lower_tick: int
    upper_tick: int
    liquidity_delta: int
    block_number: int
    timestamp: int
    event_type: str


@dataclass
class PriceState:
    sqrt_price_x96: Optional[int]
    tick: Optional[int]


@dataclass
class AggregatedDepth:
    bucket_label: str
    usdt_depth: float


@dataclass
class Snapshot:
    ticks: Dict[int, TickLiquidity]
    price_state: PriceState
    protocol: str
    pool_address: str


@dataclass
class DepthRow:
    price_label: str
    depth: float
    bar: str


@dataclass
class DepthTable:
    rows: List[DepthRow]
    as_of: int


@dataclass
class AdaptiveScale:
    current_price: float
    step: float
    min_price: float
    max_price: float
