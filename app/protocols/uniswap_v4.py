import math
import time
from typing import Iterable, List
from eth_abi import decode
from eth_utils import keccak
from web3 import Web3

from app.protocols.base import ProtocolAdapter
from app.types import LiquidityDeltaEvent, PriceState, Snapshot, TickLiquidity
from app.wss import WebsocketLogStream


class UniswapV4Adapter(ProtocolAdapter):
    def __init__(self, web3: Web3, pool_manager_address: str, pool_id: str, abi: List[dict], wss_url: str):
        super().__init__(web3, pool_manager_address)
        self.pool_id = pool_id
        self.pool_manager = web3.eth.contract(address=self.pool_address, abi=abi)
        self.stream = WebsocketLogStream(
            wss_url,
            self.pool_address,
            [
                keccak(text="ModifyLiquidity((bytes32,address,int24,int24,int256,int256))").hex(),
                keccak(text="Mint(address,bytes32,int24,int24,int128)").hex(),
            ],
        )

    def _tick_to_price(self, tick: int) -> float:
        return math.pow(1.0001, tick)

    def fetch_snapshot(self) -> Snapshot:
        # PoolManager exposes concentrated liquidity via poolId.
        ticks: dict[int, TickLiquidity] = {}
        tick_spacing = self.pool_manager.functions.tickSpacing(self.pool_id).call()
        current_tick = self.pool_manager.functions.getCurrentTick(self.pool_id).call()
        sqrt_price_x96 = self.pool_manager.functions.getCurrentSqrtPrice(self.pool_id).call()
        min_tick = -887272
        max_tick = 887272
        for tick_index in range(min_tick, max_tick, tick_spacing):
            liquidity = self.pool_manager.functions.getTickLiquidity(self.pool_id, tick_index).call()
            if liquidity == 0:
                continue
            price_lower = self._tick_to_price(tick_index)
            price_upper = self._tick_to_price(tick_index + tick_spacing)
            ticks[tick_index] = TickLiquidity(
                lower_tick=tick_index,
                upper_tick=tick_index + tick_spacing,
                liquidity=liquidity,
                token0_reserves=price_lower,
                token1_reserves=price_upper,
            )
        return Snapshot(
            ticks=ticks,
            price_state=PriceState(sqrt_price_x96=sqrt_price_x96, tick=current_tick),
            protocol="uniswap_v4",
            pool_address=self.pool_address,
        )

    def _event_to_delta(self, raw_log) -> LiquidityDeltaEvent:
        topics = raw_log.get("topics", [])
        data = raw_log.get("data", "0x")
        if topics[0] == self.stream.topics[0]:
            decoded = decode(["bytes32", "address", "int24", "int24", "int256", "int256"], bytes.fromhex(data[2:]))
            pool_id, lower_tick, upper_tick, _, delta, _ = decoded
            liquidity = int(delta)
            event_type = "ModifyLiquidity"
            if pool_id.hex() != self.pool_id[2:]:
                return None  # Ignore unrelated pools in PoolManager singleton.
        else:
            decoded = decode(["address", "bytes32", "int24", "int24", "int128"], bytes.fromhex(data[2:]))
            pool_id, lower_tick, upper_tick, delta = decoded[1], decoded[2], decoded[3], decoded[4]
            if pool_id.hex() != self.pool_id[2:]:
                return None
            liquidity = int(delta)
            event_type = "Mint"
        return LiquidityDeltaEvent(
            tx_hash=raw_log.get("transactionHash", "0x"),
            lower_tick=int(lower_tick),
            upper_tick=int(upper_tick),
            liquidity_delta=int(liquidity),
            block_number=int(raw_log.get("blockNumber", 0), 16) if isinstance(raw_log.get("blockNumber"), str) else raw_log.get("blockNumber", 0),
            timestamp=int(time.time()),
            event_type=event_type,
        )

    def stream_events(self) -> Iterable[LiquidityDeltaEvent]:
        for raw in self.stream.stream():
            event = self._event_to_delta(raw)
            if event:
                yield event
