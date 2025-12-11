from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence

from web3 import Web3
from web3.contract.contract import ContractFunction


MULTICALL2_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "address", "name": "target", "type": "address"},
                    {"internalType": "bytes", "name": "callData", "type": "bytes"},
                ],
                "internalType": "struct Multicall2.Call[]",
                "name": "calls",
                "type": "tuple[]",
            }
        ],
        "name": "aggregate",
        "outputs": [
            {"internalType": "uint256", "name": "blockNumber", "type": "uint256"},
            {"internalType": "bytes[]", "name": "returnData", "type": "bytes[]"},
        ],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]


@dataclass
class MulticallResult:
    block_number: int
    return_data: List[bytes]


class MulticallClient:
    def __init__(self, web3: Web3, address: str):
        self.web3 = web3
        self.contract = web3.eth.contract(
            address=Web3.to_checksum_address(address), abi=MULTICALL2_ABI
        )

    def _encode_call(self, fn: ContractFunction) -> tuple[str, bytes]:
        return fn.address, bytes.fromhex(fn._encode_transaction_data()[2:])

    def aggregate(self, functions: Sequence[ContractFunction]) -> MulticallResult:
        if not functions:
            return MulticallResult(block_number=0, return_data=[])
        calls = [self._encode_call(fn) for fn in functions]
        block_number, return_data = self.contract.functions.aggregate(calls).call()
        return MulticallResult(block_number=block_number, return_data=return_data)

    def call_functions(self, functions: Sequence[ContractFunction]) -> List[tuple]:
        """Execute multiple view calls via Multicall2 and decode outputs.

        Returns a list of tuples, matching the decoded outputs of each function.
        """

        result = self.aggregate(functions)
        decoded: List[tuple] = []
        for fn, raw in zip(functions, result.return_data):
            decoded.append(fn.contract.decode_function_output(fn.fn_name, raw))
        return decoded

    def batched_call(self, function_batches: Iterable[Sequence[ContractFunction]]) -> List[tuple]:
        outputs: List[tuple] = []
        for batch in function_batches:
            outputs.extend(self.call_functions(batch))
        return outputs
