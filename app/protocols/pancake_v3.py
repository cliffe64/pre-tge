import math
import time
from typing import Iterable, List
from eth_abi import decode
from eth_utils import keccak
from web3 import Web3

from app.protocols.base import ProtocolAdapter
from app.types import LiquidityDeltaEvent, PriceState, Snapshot, TickLiquidity
from app.wss import WebsocketLogStream


class PancakeV3Adapter(ProtocolAdapter):
    def __init__(self, web3: Web3, pool_address: str, tick_lens_abi: List[dict], tick_lens_address: str, pool_abi: List[dict], wss_url: str):
        super().__init__(web3, pool_address)
        self.pool_contract = web3.eth.contract(address=self.pool_address, abi=pool_abi)
        self.tick_lens = web3.eth.contract(address=Web3.to_checksum_address(tick_lens_address), abi=tick_lens_abi)
        self.stream = WebsocketLogStream(
            wss_url,
            self.pool_address,
            [
                keccak(text="Mint(address,address,int24,int24,uint128,uint256,uint256)").hex(),
                keccak(text="Burn(address,int24,int24,uint128,uint256,uint256)").hex(),
            ],
        )

    def _tick_to_price(self, tick: int) -> float:
        return math.pow(1.0001, tick)

    def fetch_snapshot(self) -> Snapshot:
        slot0 = self.pool_contract.functions.slot0().call()
        current_tick = slot0[1]
        sqrt_price_x96 = slot0[0]
        tick_spacing = self.pool_contract.functions.tickSpacing().call()
        ticks: dict[int, TickLiquidity] = {}
        # TickLens batch call to minimize RPC load.
        indexes = list(range(-887272, 887272, tick_spacing * 50))
        for batch_start in indexes:
            lower = batch_start
            upper = min(batch_start + tick_spacing * 50, 887272)
            response = self.tick_lens.functions.getPopulatedTicksInWord(self.pool_address, lower // tick_spacing).call()
            for tick_info in response:
                tick_index = tick_info[0]
                liquidity_gross = tick_info[1]
                if liquidity_gross == 0:
                    continue
                price_lower = self._tick_to_price(tick_index)
                price_upper = self._tick_to_price(tick_index + tick_spacing)
                ticks[tick_index] = TickLiquidity(
                    lower_tick=tick_index,
                    upper_tick=tick_index + tick_spacing,
                    liquidity=liquidity_gross,
                    token0_reserves=price_lower,
                    token1_reserves=price_upper,
                )
        return Snapshot(
            ticks=ticks,
            price_state=PriceState(sqrt_price_x96=sqrt_price_x96, tick=current_tick),
            protocol="pancake_v3",
            pool_address=self.pool_address,
        )

    def _event_to_delta(self, raw_log) -> LiquidityDeltaEvent:
        topics = raw_log.get("topics", [])
        data = raw_log.get("data", "0x")
        if topics[0] == self.stream.topics[0]:
            decoded = decode(["address", "address", "int24", "int24", "uint128", "uint256", "uint256"], bytes.fromhex(data[2:]))
            lower_tick, upper_tick, liquidity = int(decoded[2]), int(decoded[3]), int(decoded[4])
            event_type = "Mint"
        else:
            decoded = decode(["address", "int24", "int24", "uint128", "uint256", "uint256"], bytes.fromhex(data[2:]))
            lower_tick, upper_tick, liquidity = int(decoded[1]), int(decoded[2]), -int(decoded[3])
            event_type = "Burn"
        return LiquidityDeltaEvent(
            tx_hash=raw_log.get("transactionHash", "0x"),
            lower_tick=lower_tick,
            upper_tick=upper_tick,
            liquidity_delta=liquidity,
            block_number=int(raw_log.get("blockNumber", 0), 16) if isinstance(raw_log.get("blockNumber"), str) else raw_log.get("blockNumber", 0),
            timestamp=int(time.time()),
            event_type=event_type,
        )

    def stream_events(self) -> Iterable[LiquidityDeltaEvent]:
        for raw in self.stream.stream():
            yield self._event_to_delta(raw)
