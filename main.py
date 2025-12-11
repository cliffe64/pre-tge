import json
import logging
import queue
import threading
from pathlib import Path

from web3 import Web3

from app.config import DEFAULT_CONFIG
from app.multicall import MulticallClient
from app.state_machine import LiquidityStateMachine
from app.ui import start_ui

MOCK_ABIS = {
    "uniswap_v3_pool": [
        {
            "inputs": [],
            "name": "slot0",
            "outputs": [
                {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
                {"internalType": "int24", "name": "tick", "type": "int24"},
                {"internalType": "uint16", "name": "observationIndex", "type": "uint16"},
                {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"},
                {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"},
                {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"},
                {"internalType": "bool", "name": "unlocked", "type": "bool"},
            ],
            "stateMutability": "view",
            "type": "function",
        },
        {
            "inputs": [],
            "name": "tickSpacing",
            "outputs": [{"internalType": "int24", "name": "", "type": "int24"}],
            "stateMutability": "view",
            "type": "function",
        },
        {
            "inputs": [{"internalType": "int24", "name": "tick", "type": "int24"}],
            "name": "ticks",
            "outputs": [
                {"internalType": "uint128", "name": "liquidityGross", "type": "uint128"},
                {"internalType": "int128", "name": "liquidityNet", "type": "int128"},
                {"internalType": "uint256", "name": "feeGrowthOutside0X128", "type": "uint256"},
                {"internalType": "uint256", "name": "feeGrowthOutside1X128", "type": "uint256"},
                {"internalType": "int56", "name": "tickCumulativeOutside", "type": "int56"},
                {"internalType": "uint160", "name": "secondsPerLiquidityOutsideX128", "type": "uint160"},
                {"internalType": "uint32", "name": "secondsOutside", "type": "uint32"},
                {"internalType": "bool", "name": "initialized", "type": "bool"},
            ],
            "stateMutability": "view",
            "type": "function",
        },
        {
            "inputs": [{"internalType": "int16", "name": "wordPosition", "type": "int16"}],
            "name": "tickBitmap",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function",
        },
        {
            "anonymous": False,
            "inputs": [
                {"indexed": True, "internalType": "address", "name": "sender", "type": "address"},
                {"indexed": True, "internalType": "address", "name": "owner", "type": "address"},
                {"indexed": False, "internalType": "int24", "name": "tickLower", "type": "int24"},
                {"indexed": False, "internalType": "int24", "name": "tickUpper", "type": "int24"},
                {"indexed": False, "internalType": "uint128", "name": "amount", "type": "uint128"},
                {"indexed": False, "internalType": "uint256", "name": "amount0", "type": "uint256"},
                {"indexed": False, "internalType": "uint256", "name": "amount1", "type": "uint256"},
            ],
            "name": "Mint",
            "type": "event",
        },
        {
            "anonymous": False,
            "inputs": [
                {"indexed": True, "internalType": "address", "name": "owner", "type": "address"},
                {"indexed": False, "internalType": "int24", "name": "tickLower", "type": "int24"},
                {"indexed": False, "internalType": "int24", "name": "tickUpper", "type": "int24"},
                {"indexed": False, "internalType": "uint128", "name": "amount", "type": "uint128"},
                {"indexed": False, "internalType": "uint256", "name": "amount0", "type": "uint256"},
                {"indexed": False, "internalType": "uint256", "name": "amount1", "type": "uint256"},
            ],
            "name": "Burn",
            "type": "event",
        },
    ],
    "uniswap_v4_pool_manager": [
        {
            "anonymous": False,
            "inputs": [
                {"indexed": True, "internalType": "address", "name": "sender", "type": "address"},
                {"indexed": True, "internalType": "bytes32", "name": "poolId", "type": "bytes32"},
                {"indexed": False, "internalType": "int24", "name": "tickLower", "type": "int24"},
                {"indexed": False, "internalType": "int24", "name": "tickUpper", "type": "int24"},
                {"indexed": False, "internalType": "int128", "name": "liquidityDelta", "type": "int128"},
                {"indexed": False, "internalType": "uint256", "name": "amount0", "type": "uint256"},
                {"indexed": False, "internalType": "uint256", "name": "amount1", "type": "uint256"},
            ],
            "name": "ModifyLiquidity",
            "type": "event",
        }
    ],
    "pancake_tick_lens": [
        {
            "inputs": [
                {"internalType": "address", "name": "pool", "type": "address"},
                {"internalType": "int16", "name": "tickBitmapIndex", "type": "int16"},
            ],
            "name": "getPopulatedTicksInWord",
            "outputs": [
                {
                    "components": [
                        {"internalType": "int24", "name": "tick", "type": "int24"},
                        {"internalType": "int128", "name": "liquidityNet", "type": "int128"},
                        {"internalType": "uint128", "name": "liquidityGross", "type": "uint128"},
                    ],
                    "internalType": "struct ITickLens.PopulatedTick[]",
                    "name": "populatedTicks",
                    "type": "tuple[]",
                }
            ],
            "stateMutability": "view",
            "type": "function",
        }
    ],
    "pancake_tick_lens_address": "0x0000000000000000000000000000000000000001",
    "pancake_pool": [
        {
            "inputs": [],
            "name": "slot0",
            "outputs": [
                {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
                {"internalType": "int24", "name": "tick", "type": "int24"},
                {"internalType": "uint16", "name": "observationIndex", "type": "uint16"},
                {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"},
                {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"},
                {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"},
                {"internalType": "bool", "name": "unlocked", "type": "bool"},
            ],
            "stateMutability": "view",
            "type": "function",
        },
        {
            "inputs": [],
            "name": "tickSpacing",
            "outputs": [{"internalType": "int24", "name": "", "type": "int24"}],
            "stateMutability": "view",
            "type": "function",
        },
        {
            "inputs": [{"internalType": "int24", "name": "tick", "type": "int24"}],
            "name": "ticks",
            "outputs": [
                {"internalType": "uint128", "name": "liquidityGross", "type": "uint128"},
                {"internalType": "int128", "name": "liquidityNet", "type": "int128"},
                {"internalType": "uint256", "name": "feeGrowthOutside0X128", "type": "uint256"},
                {"internalType": "uint256", "name": "feeGrowthOutside1X128", "type": "uint256"},
                {"internalType": "int56", "name": "tickCumulativeOutside", "type": "int56"},
                {"internalType": "uint160", "name": "secondsPerLiquidityOutsideX128", "type": "uint160"},
                {"internalType": "uint32", "name": "secondsOutside", "type": "uint32"},
                {"internalType": "bool", "name": "initialized", "type": "bool"},
            ],
            "stateMutability": "view",
            "type": "function",
        },
        {
            "inputs": [{"internalType": "int16", "name": "wordPosition", "type": "int16"}],
            "name": "tickBitmap",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function",
        },
        {
            "anonymous": False,
            "inputs": [
                {"indexed": True, "internalType": "address", "name": "sender", "type": "address"},
                {"indexed": True, "internalType": "address", "name": "owner", "type": "address"},
                {"indexed": False, "internalType": "int24", "name": "tickLower", "type": "int24"},
                {"indexed": False, "internalType": "int24", "name": "tickUpper", "type": "int24"},
                {"indexed": False, "internalType": "uint128", "name": "amount", "type": "uint128"},
                {"indexed": False, "internalType": "uint256", "name": "amount0", "type": "uint256"},
                {"indexed": False, "internalType": "uint256", "name": "amount1", "type": "uint256"},
            ],
            "name": "Mint",
            "type": "event",
        },
        {
            "anonymous": False,
            "inputs": [
                {"indexed": True, "internalType": "address", "name": "owner", "type": "address"},
                {"indexed": False, "internalType": "int24", "name": "tickLower", "type": "int24"},
                {"indexed": False, "internalType": "int24", "name": "tickUpper", "type": "int24"},
                {"indexed": False, "internalType": "uint128", "name": "amount", "type": "uint128"},
                {"indexed": False, "internalType": "uint256", "name": "amount0", "type": "uint256"},
                {"indexed": False, "internalType": "uint256", "name": "amount1", "type": "uint256"},
            ],
            "name": "Burn",
            "type": "event",
        },
    ],
}


def load_config():
    return DEFAULT_CONFIG


def _load_abi(name: str) -> list[dict]:
    path = Path(__file__).with_name("abis") / f"{name}.json"
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_abis(web3: Web3, config) -> dict:
    if not config.chain.multicall_address:
        raise ValueError("MULTICALL_ADDRESS is required for batch RPC calls")
    multicall_client = MulticallClient(web3, config.chain.multicall_address)
    tick_lens_address = config.pool.tick_lens_address or config.pool.pool_address
    return {
        "uniswap_v3_pool": _load_abi("uniswap_v3_pool"),
        "uniswap_v4_pool_manager": _load_abi("uniswap_v4_pool_manager"),
        "pancake_tick_lens": _load_abi("pancake_tick_lens"),
        "pancake_pool": _load_abi("pancake_pool"),
        "pancake_tick_lens_address": tick_lens_address,
        "multicall": multicall_client,
    }


def start_event_loop(state: LiquidityStateMachine, sink: queue.Queue) -> None:
    def _loop() -> None:
        for event in state.adapter.stream_events():
            state.apply_event(event)
            sink.put(event)
    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()


def main() -> None:
    setup_logging()
    config = load_config()
    provider = Web3(Web3.HTTPProvider(config.chain.rpc_url))
    abis = _load_abis(provider, config)
    state = LiquidityStateMachine(provider, config, abis)
    event_queue: queue.Queue = queue.Queue()
    start_event_loop(state, event_queue)
    start_ui(state, event_queue)


if __name__ == "__main__":
    main()
