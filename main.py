import logging
import queue
import threading
from web3 import Web3

from app.abi_loader import load_all_abis
from app.config import DEFAULT_CONFIG
from app.multicall import MulticallClient
from app.state_machine import LiquidityStateMachine
from app.ui import start_ui


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler("app.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def start_event_loop(state: LiquidityStateMachine, sink: queue.Queue) -> None:
    def _loop() -> None:
        for event in state.adapter.stream_events():
            state.apply_event(event)
            sink.put(event)

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()


def main() -> None:
    setup_logging()
    config = DEFAULT_CONFIG
    provider = Web3(Web3.HTTPProvider(config.chain.rpc_url))
    if not config.chain.multicall_address:
        raise ValueError("MULTICALL_ADDRESS is required for batch RPC calls")

    abis = load_all_abis(config)
    abis["multicall"] = MulticallClient(provider, config.chain.multicall_address)

    state = LiquidityStateMachine(provider, config, abis)
    event_queue: queue.Queue = queue.Queue()
    start_event_loop(state, event_queue)
    start_ui(state, event_queue)


if __name__ == "__main__":
    main()
