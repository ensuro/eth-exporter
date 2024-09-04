import asyncio
import logging
from typing import List

from . import config
from .build_artifacts import ArtifactLibrary

contracts = ArtifactLibrary(config.ABIS_PATH)


logger = logging.getLogger(__name__)


class CallArgument:
    def __init__(self, value: str, transform: str = None):
        self.value = value

        if transform is not None:
            raise NotImplementedError("To be implemented")

        self.transform = transform


class ContractCall:
    def __init__(
        self,
        contract_type: str,
        function: str,
        arguments: List[CallArgument],
        addresses: List[str],
    ):
        self.contract_type = contract_type
        self.abi = contracts.get_artifact_by_name(contract_type).abi
        self.function = function
        self.arguments = arguments
        self.addresses = addresses

    async def __call__(self, w3):
        calls = []
        for address in self.addresses:
            logger.info(
                "Calling %s.%s(%s) on %s",
                self.contract_type,
                self.function,
                ",".join(self.arguments),
                address,
            )
            contract = w3.eth.contract(address=address, abi=self.abi, decode_tuples=True)
            function = contract.functions[self.function](*[arg.value for arg in self.arguments])
            calls.append(function.call())
        return await asyncio.gather(*calls)


class Metric:
    def __init__(self, name: str, description: str, type: str):
        self.name = name
        self.description = description
        self.type = type
