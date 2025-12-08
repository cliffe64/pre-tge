import queue
import threading
from web3 import Web3

from app.config import DEFAULT_CONFIG
from app.state_machine import LiquidityStateMachine
from app.ui import start_ui


MOCK_ABIS = {
    "uniswap_v3_pool": [],
    "uniswap_v4_pool_manager": [],
    "pancake_tick_lens": [],
    "pancake_tick_lens_address": "0x0000000000000000000000000000000000000001",
    "pancake_pool": [],
}


def load_config():
    return DEFAULT_CONFIG


def start_event_loop(state: LiquidityStateMachine, sink: queue.Queue) -> None:
    def _loop() -> None:
        for event in state.adapter.stream_events():
            state.apply_event(event)
            sink.put(event)
    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()


def main() -> None:
    config = load_config()
    provider = Web3(Web3.HTTPProvider(config.chain.rpc_url))
    state = LiquidityStateMachine(provider, config, MOCK_ABIS)
    event_queue: queue.Queue = queue.Queue()
    start_event_loop(state, event_queue)
    start_ui(state, event_queue)


if __name__ == "__main__":
    main()
