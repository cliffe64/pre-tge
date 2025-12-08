import math
import threading
from collections import defaultdict
from typing import Dict, List

from web3 import Web3

from app.config import AppConfig
from app.protocols.pancake_v3 import PancakeV3Adapter
from app.protocols.uniswap_v3 import UniswapV3Adapter
from app.protocols.uniswap_v4 import UniswapV4Adapter
from app.types import AdaptiveScale, AggregatedDepth, LiquidityDeltaEvent, PriceState, Snapshot, TickLiquidity


class LiquidityStateMachine:
    def __init__(self, web3: Web3, config: AppConfig, abis: dict):
        self.web3 = web3
        self.config = config
        self.lock = threading.Lock()
        self.adapter = self._build_adapter(abis)
        self.snapshot = self.adapter.fetch_snapshot()

    def _build_adapter(self, abis: dict):
        protocol = self.config.pool.protocol
        if protocol == "uniswap_v3":
            return UniswapV3Adapter(self.web3, self.config.pool.pool_address, abis["uniswap_v3_pool"], self.config.chain.wss_url)
        if protocol == "uniswap_v4":
            return UniswapV4Adapter(
                self.web3,
                self.config.pool.pool_address,
                self.config.pool.pool_id or "0x",
                abis["uniswap_v4_pool_manager"],
                self.config.chain.wss_url,
            )
        return PancakeV3Adapter(
            self.web3,
            self.config.pool.pool_address,
            abis["pancake_tick_lens"],
            abis["pancake_tick_lens_address"],
            abis["pancake_pool"],
            self.config.chain.wss_url,
        )

    def apply_event(self, event: LiquidityDeltaEvent) -> None:
        with self.lock:
            bucket = self.snapshot.ticks.get(event.lower_tick)
            if bucket is None:
                price_lower = math.pow(1.0001, event.lower_tick)
                price_upper = math.pow(1.0001, event.upper_tick)
                bucket = TickLiquidity(
                    lower_tick=event.lower_tick,
                    upper_tick=event.upper_tick,
                    liquidity=0,
                    token0_reserves=price_lower,
                    token1_reserves=price_upper,
                )
                self.snapshot.ticks[event.lower_tick] = bucket
            bucket.liquidity += event.liquidity_delta

    def update_price(self, price_state: PriceState) -> None:
        with self.lock:
            self.snapshot.price_state = price_state

    def _tick_price(self, tick: int) -> float:
        return math.pow(1.0001, tick)

    def _current_price(self) -> float:
        tick = self.snapshot.price_state.tick
        if tick is None:
            return 0.0
        return self._tick_price(tick)

    def _adaptive_scale(self) -> AdaptiveScale:
        price = self._current_price()
        if price <= 0:
            price = 1.0
        step = max(price * 0.02, 1e-8)
        min_price = max(price - step * 10, step)
        max_price = price + step * 10
        return AdaptiveScale(current_price=price, step=step, min_price=min_price, max_price=max_price)

    def _bucket_label(self, price: float) -> str:
        return f"{price:,.6f}"

    def buy_wall_depth(self) -> List[AggregatedDepth]:
        scale = self._adaptive_scale()
        with self.lock:
            price_state = scale.current_price
            buckets: Dict[str, float] = defaultdict(float)
            for tick_liquidity in self.snapshot.ticks.values():
                price_lower = self._tick_price(tick_liquidity.lower_tick)
                price_upper = self._tick_price(tick_liquidity.upper_tick)
                if tick_liquidity.liquidity <= 0:
                    continue
                if price_state == 0:
                    is_below = True
                else:
                    is_below = price_upper < price_state
                contains_price = price_lower <= price_state <= price_upper if price_state else False
                if not is_below and not contains_price:
                    continue
                quote_value = tick_liquidity.liquidity
                if contains_price and price_state:
                    span = price_upper - price_lower
                    quote_value = tick_liquidity.liquidity * max(price_state - price_lower, 0) / span if span else tick_liquidity.liquidity
                bucket_index = int((price_upper - scale.min_price) // scale.step)
                bucket_price = scale.min_price + bucket_index * scale.step
                label = self._bucket_label(bucket_price)
                buckets[label] += quote_value
            depths = [AggregatedDepth(bucket_label=k, usdt_depth=v) for k, v in sorted(buckets.items(), key=lambda x: float(x[0].replace(',', '')))]
        return depths

    def adaptive_scale(self) -> AdaptiveScale:
        return self._adaptive_scale()

    def latest_price(self) -> float:
        return self._current_price()
