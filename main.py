import logging
import queue
import threading

from web3 import Web3

from app.abi_loader import load_all_abis
from app.config import DEFAULT_CONFIG
from app.multicall import MulticallClient
from app.state_machine import LiquidityStateMachine
from app.ui import start_ui

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            # 只写入文件，避免控制台输出打断 UI 绘制
            logging.FileHandler("monitor.log"),
        ]
    )
    # 屏蔽第三方库的噪音日志
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def start_event_loop(state: LiquidityStateMachine, sink: queue.Queue) -> None:
    def _loop() -> None:
        # 在独立线程中处理 WebSocket 事件流
        for event in state.adapter.stream_events():
            state.apply_event(event)
            sink.put(event)

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()


def main() -> None:
    setup_logging()
    config = DEFAULT_CONFIG
    
    logging.info(f"Starting Auditor for {config.pool.protocol} on {config.chain.name}")

    # 1. 初始化 Web3 连接
    provider = Web3(Web3.HTTPProvider(config.chain.rpc_url))
    if not provider.is_connected():
        raise ConnectionError("Failed to connect to RPC")

    # 2. 加载资源 (ABI & Multicall)
    if not config.chain.multicall_address:
        raise ValueError("MULTICALL_ADDRESS is required for batch RPC calls")
        
    # 直接使用 abi_loader 模块，无需本地重复定义
    abis = load_all_abis(config)
    abis["multicall"] = MulticallClient(provider, config.chain.multicall_address)

    # 3. 初始化核心状态机 (自动拉取 Snapshot)
    logging.info("Initializing State Machine...")
    state = LiquidityStateMachine(provider, config, abis)
    logging.info("Snapshot fetched successfully.")

    # 4. 启动事件循环和 UI
    event_queue: queue.Queue = queue.Queue()
    start_event_loop(state, event_queue)
    start_ui(state, event_queue)


if __name__ == "__main__":
    main()
