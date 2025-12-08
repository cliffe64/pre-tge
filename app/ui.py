import os
import queue
import threading
import time
from typing import List

from app.state_machine import LiquidityStateMachine
from app.types import DepthRow, LiquidityDeltaEvent

BAR_CHAR = "▮"


def _clear_screen() -> None:
    os.system("clear")


def _format_event(event: LiquidityDeltaEvent) -> str:
    return (
        f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(event.timestamp))} "
        f"[{event.event_type}] tick {event.lower_tick}-{event.upper_tick} Δ{event.liquidity_delta} tx={event.tx_hash}"
    )


def render_depth_table(state: LiquidityStateMachine) -> None:
    scale = state.adaptive_scale()
    depths = state.buy_wall_depth()
    _clear_screen()
    print("=== Depth Chart (Buy Wall) ===")
    print(f"Current Price: {scale.current_price:,.6f}  Step: {scale.step:,.6f}")
    rows: List[DepthRow] = []
    for depth in depths:
        bar_length = int(depth.usdt_depth // 1_000) + 1
        bar = BAR_CHAR * min(bar_length, 60)
        rows.append(DepthRow(price_label=depth.bucket_label, depth=depth.usdt_depth, bar=bar))
    for row in rows:
        print(f"{row.price_label} | USDT {row.depth:,.2f} | {row.bar}")


class StreamPrinter(threading.Thread):
    def __init__(self, sink: queue.Queue):
        super().__init__(daemon=True)
        self.sink = sink

    def run(self) -> None:
        while True:
            try:
                event = self.sink.get()
                print(_format_event(event))
            except Exception:
                continue


def start_ui(state: LiquidityStateMachine, event_queue: queue.Queue) -> None:
    printer = StreamPrinter(event_queue)
    printer.start()
    while True:
        render_depth_table(state)
        time.sleep(15)
