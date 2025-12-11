import time
from typing import Iterable, List, Sequence
from eth_abi import decode
from eth_utils import keccak
from web3 import Web3
from web3.contract.contract import ContractEvent, ContractFunction

from app.multicall import MulticallClient
from app.pricing import tick_to_price
from app.types import LiquidityDeltaEvent, PriceState, Snapshot, TickLiquidity
from app.protocols.base import ProtocolAdapter
from app.wss import WebsocketLogStream


class UniswapV3Adapter(ProtocolAdapter):
    def __init__(
        self,
        web3: Web3,
        pool_address: str,
        abi: List[dict],
        wss_url: str,
        multicall: MulticallClient,
        token0_decimals: int,
        token1_decimals: int,
    ):
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
        self.multicall = multicall
        self.token0_decimals = token0_decimals
        self.token1_decimals = token1_decimals

    def fetch_snapshot(self) -> Snapshot:
        slot0_fn = self.pool_contract.functions.slot0()
        tick_spacing_fn = self.pool_contract.functions.tickSpacing()
        slot0_result, tick_spacing_result = self.multicall.call_functions(
            [slot0_fn, tick_spacing_fn]
        )
        tick_spacing = tick_spacing_result[0]
        current_tick = slot0_result[1]
        sqrt_price_x96 = slot0_result[0]
        ticks: dict[int, TickLiquidity] = {}
        min_tick = -887272
        max_tick = 887272
        for tick_index in self._collect_initialized_ticks(min_tick, max_tick, tick_spacing):
            liquidity_gross, liquidity_net, *_ = self.pool_contract.functions.ticks(tick_index).call()
            if liquidity_gross == 0:
                continue
            price_lower = tick_to_price(tick_index, self.token0_decimals, self.token1_decimals)
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
        """
        [Refactored] Use Multicall to batch fetch tick bitmaps.
        """
        word_size = 256
        min_word = math.floor(min_tick / tick_spacing / word_size)
        max_word = math.ceil(max_tick / tick_spacing / word_size)
        
        word_indices = list(range(min_word, max_word + 1))
        
        # 将请求分批，每批查询 200 个 Bitmap Word (约 500ms)
        batch_size = 200
        for i in range(0, len(word_indices), batch_size):
            chunk = word_indices[i : i + batch_size]
            
            # 1. 构造 Multicall 请求
            calls = [self.pool_contract.functions.tickBitmap(w) for w in chunk]
            
            try:
                # 2. 批量执行
                bitmaps = self.multicall.call_functions(calls)
            except Exception as e:
                print(f"Bitmap batch fetch failed: {e}")
                continue
            
            # 3. 本地解析
            for word_index, (bitmap,) in zip(chunk, bitmaps):
                if bitmap == 0:
                    continue
                for bit_pos in range(word_size):
                    if (bitmap >> bit_pos) & 1:
                        normalized_tick = (word_index * word_size) + bit_pos
                        tick_index = normalized_tick * tick_spacing
                        if min_tick <= tick_index <= max_tick:
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
