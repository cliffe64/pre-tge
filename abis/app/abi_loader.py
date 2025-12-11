import json
from pathlib import Path
from typing import Dict, Any

def load_abi(name: str) -> Any:
    """从 app/abis/ 目录加载 JSON ABI 文件"""
    # 假设 abis 目录位于 app/abis
    base_path = Path(__file__).parent / "abis"
    file_path = base_path / f"{name}.json"
    
    if not file_path.exists():
        raise FileNotFoundError(f"ABI file not found: {file_path}")
        
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_all_abis(config) -> Dict[str, Any]:
    """加载所有需要的 ABI"""
    return {
        "uniswap_v3_pool": load_abi("uniswap_v3_pool"),
        "uniswap_v4_pool_manager": load_abi("uniswap_v4_pool_manager"),
        "pancake_tick_lens": load_abi("pancake_tick_lens"),
        "pancake_pool": load_abi("pancake_pool"),
        # Pancake lens 地址通常硬编码或配置在 config 中
        "pancake_tick_lens_address": config.pool.tick_lens_address or "0x0000000000000000000000000000000000000000", 
    }
