# Pre-TGE Liquidity Depth Auditor

A console-based "God View" for pre-market liquidity that keeps the entire liquidity map in memory and reacts to real-time WebSocket deltas without on-demand RPC calls.

## Features
- Single-shot snapshot phase that loads every tick into memory for the target pool.
- WebSocket-driven delta ingestion for Mint/Burn/ModifyLiquidity events (no polling).
- In-memory buy-wall calculator that only counts USDT liquidity below or straddling the current price.
- Adaptive bin sizing (≈2% of price) keeps the depth table readable for any token price.
- Dual-pane console output: real-time liquidity adds plus a 15s-refresh ASCII depth chart.

## Running
1. Install dependencies: `pip install -r requirements.txt`.
2. Configure `app/config.py` with the target chain, pool, and protocol settings.
3. Supply protocol ABIs/addresses to `MOCK_ABIS` in `main.py` (replace placeholders).
4. Run the console: `python main.py`.

## Architecture
- `main.py` wires the config, snapshot builder, WebSocket stream, and UI threads.
- `app/state_machine.py` stores the full tick map and applies deltas without extra RPC calls.
- `app/protocols/` contains adapters for Uniswap V3, PancakeSwap V3 (TickLens), and Uniswap V4 (PoolManager singleton filtered by poolId).
- `app/ui.py` renders the streaming event feed and the 15-second depth chart using the in-memory state.

## Notes
- WebSocket reconnection is built into the log streamer; it resubscribes after disconnects.
- When price is undefined (pre-TGE), the buy-wall calculator treats all ticks as below price by default.
