from abc import ABC, abstractmethod
from typing import Iterable
from web3 import Web3

from app.types import LiquidityDeltaEvent, Snapshot


class ProtocolAdapter(ABC):
    def __init__(self, web3: Web3, pool_address: str):
        self.web3 = web3
        self.pool_address = Web3.to_checksum_address(pool_address)

    @abstractmethod
    def fetch_snapshot(self) -> Snapshot:
        ...

    @abstractmethod
    def stream_events(self) -> Iterable[LiquidityDeltaEvent]:
        ...
