import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class ChainConfig:
    name: str
    rpc_url: str
    wss_url: str
    explorer: str


@dataclass
class PoolConfig:
    pool_address: str
    protocol: str  # v3, v4, pancake_v3
    token0: str
    token1: str
    fee: int
    pool_id: str | None = None  # for Uniswap V4


@dataclass
class AppConfig:
    chain: ChainConfig
    pool: PoolConfig
    tokens: List[str] = field(default_factory=list)


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _load_tokens_from_env() -> List[str]:
    token_env = os.getenv("TOKENS", "USDT,TOKEN")
    return [token.strip() for token in token_env.split(",") if token.strip()]


def _load_json_config() -> dict | None:
    path = Path("config.json")
    if path.exists():
        with path.open() as f:
            return json.load(f)
    return None


DEFAULT_CONFIG = AppConfig(
    chain=ChainConfig(
        name=_env("CHAIN_NAME", "bsc"),
        rpc_url=_env("RPC_URL", "https://bsc-dataseed.binance.org"),
        wss_url=_env("WSS_URL", "wss://bsc-ws-node.nariox.org:443"),
        explorer=_env("EXPLORER_URL", "https://bscscan.com/tx/"),
    ),
    pool=PoolConfig(
        pool_address=_env("POOL_ADDRESS", ""),
        protocol=_env("PROTOCOL", "pancake_v3"),
        token0=_env("TOKEN0", "USDT"),
        token1=_env("TOKEN1", "TOKEN"),
        fee=int(_env("FEE", "500")),
        pool_id=os.getenv("POOL_ID"),
    ),
    tokens=_load_tokens_from_env(),
)
