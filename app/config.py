import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class ChainConfig:
    name: str
    rpc_url: str
    wss_url: str
    explorer: str
    multicall_address: str | None = None


@dataclass
class PoolConfig:
    pool_address: str
    protocol: str  # v3, v4, pancake_v3
    token0: str
    token1: str
    fee: int
    token0_decimals: int
    token1_decimals: int
    pool_id: str | None = None  # for Uniswap V4
    tick_lens_address: str | None = None


@dataclass
class AppConfig:
    chain: ChainConfig
    pool: PoolConfig
    tokens: List[str] = field(default_factory=list)


def _load_config_from_file(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _get_env_or_default(key: str, fallback: Optional[str]) -> Optional[str]:
    return os.getenv(key, fallback)


_CONFIG_PATH = Path(__file__).with_name("config.json")
_CONFIG_DATA = _load_config_from_file(_CONFIG_PATH)


chain_data = _CONFIG_DATA.get("chain", {})
pool_data = _CONFIG_DATA.get("pool", {})
tokens_data = _CONFIG_DATA.get("tokens", [])


DEFAULT_CONFIG = AppConfig(
    chain=ChainConfig(
        name=_get_env_or_default("CHAIN_NAME", chain_data.get("name", "bsc")),
        rpc_url=_get_env_or_default("RPC_URL", chain_data.get("rpc_url", "https://bsc-dataseed.binance.org")),
        wss_url=_get_env_or_default("WSS_URL", chain_data.get("wss_url", "wss://bsc-ws-node.nariox.org:443")),
        explorer=_get_env_or_default("EXPLORER_URL", chain_data.get("explorer", "https://bscscan.com/tx/")),
    ),
    pool=PoolConfig(
        pool_address=_get_env_or_default("POOL_ADDRESS", pool_data.get("pool_address")),
        protocol=_get_env_or_default("POOL_PROTOCOL", pool_data.get("protocol", "pancake_v3")),
        token0=_get_env_or_default("TOKEN0_SYMBOL", pool_data.get("token0", "USDT")),
        token1=_get_env_or_default("TOKEN1_SYMBOL", pool_data.get("token1", "TOKEN")),
        fee=int(_get_env_or_default("POOL_FEE", str(pool_data.get("fee", 500)))) if _get_env_or_default("POOL_FEE", None) or pool_data.get("fee") is not None else 500,
        pool_id=_get_env_or_default("POOL_ID", pool_data.get("pool_id")),
    ),
    tokens=(
        _get_env_or_default("TOKENS", None).split(",")
        if _get_env_or_default("TOKENS", None)
        else tokens_data
        if tokens_data
        else ["USDT", "TOKEN"]
    ),
)


if not DEFAULT_CONFIG.pool.pool_address:
    raise ValueError("POOL_ADDRESS must be provided via environment variables or config.json")
