import math


def tick_to_price(tick: int, token0_decimals: int, token1_decimals: int) -> float:
    decimal_correction = math.pow(10, token0_decimals - token1_decimals)
    return math.pow(1.0001, tick) * decimal_correction
