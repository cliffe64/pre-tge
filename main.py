import json
import logging
import queue
import threading
from pathlib import Path

from web3 import Web3

from app.abi_loader import load_all_abis
from app.config import DEFAULT_CONFIG
from app.multicall import MulticallClient
from app.state_machine import LiquidityStateMachine
from app.ui import start_ui
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
