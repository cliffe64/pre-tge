import time
from typing import Iterable, List, Sequence
from eth_abi import decode
from eth_utils import keccak
from web3 import Web3

from app.multicall import MulticallClient
from app.pricing import tick_to_price
from app.protocols.base import ProtocolAdapter
from app.types import LiquidityDeltaEvent, PriceState, Snapshot, TickLiquidity
from app.wss import WebsocketLogStream


class PancakeV3Adapter(ProtocolAdapter):
    def __init__(
        self,
        web3: Web3,
        pool_address: str,
        tick_lens_abi: List[dict],
        tick_lens_address: str,
        pool_abi: List[dict],
        wss_url: str,
        multicall: MulticallClient,
        token0_decimals: int,
        token1_decimals: int,
    ):
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
        self.multicall = multicall
        self.token0_decimals = token0_decimals
        self.token1_decimals = token1_decimals

    def fetch_snapshot(self) -> Snapshot:
        slot0_fn = self.pool_contract.functions.slot0()
        tick_spacing_fn = self.pool_contract.functions.tickSpacing()
        slot0_result, tick_spacing_result = self.multicall.call_functions([slot0_fn, tick_spacing_fn])
        current_tick = slot0_result[1]
        sqrt_price_x96 = slot0_result[0]
        tick_spacing = tick_spacing_result[0]
        ticks: dict[int, TickLiquidity] = {}
        word_indices = list(range(-887272 // tick_spacing, 887272 // tick_spacing + 1))
        word_functions = [
            self.tick_lens.functions.getPopulatedTicksInWord(
                self.pool_address, int(word_index)
            )
            for word_index in word_indices
        ]
        for batch in self._batched_functions(word_functions):
            response_batch = self.multicall.call_functions(batch)
            for response in response_batch:
                for tick_info in response[0]:
                    tick_index = tick_info[0]
                    liquidity_net = tick_info[1]
                    liquidity_gross = tick_info[2]
                    if liquidity_gross == 0:
                        continue
                    price_lower = tick_to_price(
                        tick_index, self.token0_decimals, self.token1_decimals
                    )
                    price_upper = tick_to_price(
                        tick_index + tick_spacing, self.token0_decimals, self.token1_decimals
                    )
                    ticks[tick_index] = TickLiquidity(
                        lower_tick=tick_index,
                        upper_tick=tick_index + tick_spacing,
                        liquidity=liquidity_gross,
                        token0_reserves=price_lower,
                        token1_reserves=price_upper,
                        liquidity_net=liquidity_net,
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

    def _batched_functions(
        self, functions: Sequence, batch_size: int = 80
    ) -> Iterable[Sequence]:
        for i in range(0, len(functions), batch_size):
            yield functions[i : i + batch_size]
