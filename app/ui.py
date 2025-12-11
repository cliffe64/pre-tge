import logging
import queue
import threading
import time
from collections import deque
from typing import Deque

from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from app.state_machine import LiquidityStateMachine
from app.types import AggregatedDepth, LiquidityDeltaEvent

MAX_EVENTS = 50


def _format_event(event: LiquidityDeltaEvent) -> str:
    return (
        f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(event.timestamp))} "
        f"[{event.event_type}] tick {event.lower_tick}-{event.upper_tick} Δ{event.liquidity_delta} tx={event.tx_hash}"
    )


def _build_depth_table(depths: list[AggregatedDepth], current_price: float, step: float) -> Table:
    table = Table(title="Depth Chart (Buy Wall)", expand=True)
    table.add_column("Bucket")
    table.add_column("USDT Depth", justify="right")
    table.add_column("Step", justify="right")
    table.add_column("Bar")
    for depth in depths:
        bar_length = int(depth.usdt_depth // 1_000) + 1
        bar = "▮" * min(bar_length, 60)
        table.add_row(depth.bucket_label, f"{depth.usdt_depth:,.2f}", f"{step:,.6f}", bar)
    table.caption = f"Current Price: {current_price:,.6f}"
    return table


def _build_event_panel(events: Deque[str]) -> Panel:
    return Panel("\n".join(list(events)[-MAX_EVENTS:]), title="Recent Events", border_style="blue")


class EventRecorder(threading.Thread):
    def __init__(self, sink: queue.Queue, buffer: Deque[str]):
        super().__init__(daemon=True)
        self.sink = sink
        self.buffer = buffer

    def run(self) -> None:
        while True:
            try:
                event = self.sink.get()
                formatted = _format_event(event)
                logging.info(formatted)
                self.buffer.append(formatted)
            except Exception:
                continue


def start_ui(state: LiquidityStateMachine, event_queue: queue.Queue) -> None:
    event_buffer: Deque[str] = deque(maxlen=MAX_EVENTS)
    recorder = EventRecorder(event_queue, event_buffer)
    recorder.start()

    with Live(refresh_per_second=2, screen=False) as live:
        while True:
            scale = state.adaptive_scale()
            depths = state.buy_wall_depth()
            depth_table = _build_depth_table(depths, scale.current_price, scale.step)
            events_panel = _build_event_panel(event_buffer)
            live.update(Group(depth_table, events_panel))
            time.sleep(1)
