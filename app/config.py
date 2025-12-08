from dataclasses import dataclass, field
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


DEFAULT_CONFIG = AppConfig(
    chain=ChainConfig(
        name="bsc",
        rpc_url="https://bsc-dataseed.binance.org",
        wss_url="wss://bsc-ws-node.nariox.org:443",
        explorer="https://bscscan.com/tx/",
    ),
    pool=PoolConfig(
        pool_address="0x0000000000000000000000000000000000000000",
        protocol="pancake_v3",
        token0="USDT",
        token1="TOKEN",
        fee=500,
    ),
    tokens=["USDT", "TOKEN"],
)
