import json
from pathlib import Path
from typing import Dict

from app.config import AppConfig


def _load_single_abi(abi_dir: Path, name: str) -> list[dict]:
    path = abi_dir / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"ABI file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_all_abis(config: AppConfig, abi_path: Path | None = None) -> Dict[str, object]:
    abi_dir = abi_path or Path(__file__).with_name("abis")
    if not abi_dir.exists():
        raise FileNotFoundError(f"ABI directory not found: {abi_dir}")

    abis: Dict[str, object] = {
        "uniswap_v3_pool": _load_single_abi(abi_dir, "uniswap_v3_pool"),
        "uniswap_v4_pool_manager": _load_single_abi(abi_dir, "uniswap_v4_pool_manager"),
        "pancake_pool": _load_single_abi(abi_dir, "pancake_pool"),
        "pancake_tick_lens": _load_single_abi(abi_dir, "pancake_tick_lens"),
    }

    abis["pancake_tick_lens_address"] = (
        config.pool.tick_lens_address or config.pool.pool_address
    )
    return abis
