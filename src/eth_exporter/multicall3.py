import itertools
from typing import Any
from eth_utils.abi import get_abi_output_types
from eth_abi.exceptions import (
    DecodingError,
)
from web3._utils.normalizers import (
    BASE_RETURN_NORMALIZERS,
)
from web3._utils.abi import (
    map_abi_data,
    named_tree,
    recursive_dict_to_namedtuple,
)
from web3.exceptions import (
    BadFunctionCallOutput,
)

MULTICALL_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "address", "name": "target", "type": "address"},
                    {"internalType": "bool", "name": "allowFailure", "type": "bool"},
                    {"internalType": "bytes", "name": "callData", "type": "bytes"},
                ],
                "internalType": "struct Multicall3.Call3[]",
                "name": "calls",
                "type": "tuple[]",
            }
        ],
        "name": "aggregate3",
        "outputs": [
            {
                "components": [
                    {"internalType": "bool", "name": "success", "type": "bool"},
                    {"internalType": "bytes", "name": "returnData", "type": "bytes"},
                ],
                "internalType": "struct Multicall3.Result[]",
                "name": "returnData",
                "type": "tuple[]",
            }
        ],
        "stateMutability": "payable",
        "type": "function",
    },
]

MULTICALL_ADDRESS = "0xcA11bde05977b3631167028862bE2a173976CA11"


def decode_return_data(w3, function, return_data) -> Any:
    # Adapted from https://github.com/ethereum/web3.py/blob/v7.8.0/web3/contract/utils.py#L124
    # removing all the call part
    output_types = get_abi_output_types(function.abi)

    try:
        output_data = w3.codec.decode(output_types, return_data)
    except DecodingError as e:
        msg = (
            f"Could not decode contract function call to {function.abi_element_identifier} "
            f"with return data: {str(return_data)}, output_types: {output_types}"
        )
        raise BadFunctionCallOutput(msg) from e

    _normalizers = itertools.chain(
        BASE_RETURN_NORMALIZERS,
        function._return_data_normalizers,
    )
    normalized_data = map_abi_data(_normalizers, output_types, output_data)

    decoded = named_tree(function.abi["outputs"], normalized_data)
    normalized_data = recursive_dict_to_namedtuple(decoded)

    if len(normalized_data) == 1:
        return normalized_data[0]
    else:
        return normalized_data


async def aggregate3(w3, functions, block_identifier):
    multicall3 = w3.eth.contract(address=MULTICALL_ADDRESS, abi=MULTICALL_ABI, decode_tuples=True)
    agg3 = multicall3.functions.aggregate3(
        [(fn.address, True, fn._encode_transaction_data()) for fn in functions]
    )
    results = await agg3.call(block_identifier=block_identifier)
    return [
        (
            result.success,
            (result.returnData if not result.success else decode_return_data(w3, fn, result.returnData)),
        )
        for result, fn in zip(results, functions)
    ]
