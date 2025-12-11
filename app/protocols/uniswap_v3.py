import math
import time
from typing import Iterable, List
from eth_abi import decode
from eth_utils import keccak
from web3 import Web3
from web3.contract.contract import ContractEvent

from app.types import LiquidityDeltaEvent, PriceState, Snapshot, TickLiquidity
from app.protocols.base import ProtocolAdapter
from app.wss import WebsocketLogStream


class UniswapV3Adapter(ProtocolAdapter):
    def __init__(self, web3: Web3, pool_address: str, abi: List[dict], wss_url: str):
        super().__init__(web3, pool_address)
        self.pool_contract = web3.eth.contract(address=self.pool_address, abi=abi)
        self._mint_event: ContractEvent = self.pool_contract.events.Mint
        self._burn_event: ContractEvent = self.pool_contract.events.Burn
        self._swap_event: ContractEvent = self.pool_contract.events.Swap
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
        tick_spacing = self.pool_contract.functions.tickSpacing().call()
        current_tick = slot0[1]
        sqrt_price_x96 = slot0[0]
        ticks: dict[int, TickLiquidity] = {}
        min_tick = -887272
        max_tick = 887272
        for tick_index in self._collect_initialized_ticks(min_tick, max_tick, tick_spacing):
            liquidity_gross, liquidity_net, *_ = self.pool_contract.functions.ticks(tick_index).call()
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
                liquidity_net=liquidity_net,
            )
        return Snapshot(
            ticks=ticks,
            price_state=PriceState(sqrt_price_x96=sqrt_price_x96, tick=current_tick),
            protocol="uniswap_v3",
            pool_address=self.pool_address,
        )

    def _event_to_delta(self, raw_log) -> LiquidityDeltaEvent:
        topics = raw_log.get("topics", [])
        data = raw_log.get("data", "0x")
        if not topics:
            raise ValueError("Missing topics in log")
        if topics[0] == self.stream.topics[0]:
            decoded = self._decode_mint_event(data)
            if decoded is None:
                raise ValueError("Unable to decode Mint event payload")
            lower_tick, upper_tick, liquidity = int(decoded["tickLower"]), int(decoded["tickUpper"]), int(decoded["amount"])
            event_type = "Mint"
        else:
            decoded = self._decode_burn_event(data)
            if decoded is None:
                raise ValueError("Unable to decode Burn event payload")
            lower_tick, upper_tick, liquidity = int(decoded["tickLower"]), int(decoded["tickUpper"]), -int(decoded["amount"])
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
            try:
                yield self._event_to_delta(raw)
            except ValueError:
                continue

    def _collect_initialized_ticks(self, min_tick: int, max_tick: int, tick_spacing: int) -> Iterable[int]:
        word_size = 256
        min_word = math.floor(min_tick / tick_spacing / word_size)
        max_word = math.ceil(max_tick / tick_spacing / word_size)
        for word_index in range(min_word, max_word + 1):
            bitmap = self.pool_contract.functions.tickBitmap(word_index).call()
            if bitmap == 0:
                continue
            for bit_pos in range(word_size):
                if (bitmap >> bit_pos) & 1 == 0:
                    continue
                normalized_tick = (word_index * word_size) + bit_pos
                tick_index = normalized_tick * tick_spacing
                if tick_index < min_tick or tick_index > max_tick:
                    continue
                yield tick_index

    def _decode_mint_event(self, data: str) -> dict | None:
        field_names = ["sender", "owner", "tickLower", "tickUpper", "amount", "amount0", "amount1"]
        try:
            decoded = decode(
                ["address", "address", "int24", "int24", "uint128", "uint256", "uint256"],
                bytes.fromhex(data[2:]),
            )
        except Exception:
            return None
        if len(decoded) != len(field_names):
            return None
        return dict(zip(field_names, decoded))

    def _decode_burn_event(self, data: str) -> dict | None:
        field_names = ["owner", "tickLower", "tickUpper", "amount", "amount0", "amount1"]
        try:
            decoded = decode(
                ["address", "int24", "int24", "uint128", "uint256", "uint256"],
                bytes.fromhex(data[2:]),
            )
        except Exception:
            return None
        if len(decoded) != len(field_names):
            return None
        return dict(zip(field_names, decoded))
