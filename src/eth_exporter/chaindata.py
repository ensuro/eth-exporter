import asyncio
import logging
from dataclasses import dataclass
from typing import List, Union

import yaml

from . import config
from .metrics import create_metric
from .vendor.address_book import Address
from .vendor.address_book import get_default as get_address_book
from .vendor.build_artifacts import ArtifactLibrary

contracts = ArtifactLibrary(config.ABIS_PATH)


logger = logging.getLogger(__name__)


class NamedAddress:
    address: Address
    name: str

    def __init__(self, value: str):
        if value.startswith("0x"):
            # We got an actual address, let's try to get the name for it
            self.address = Address(value)
            name = get_address_book().addr_to_name(self.address)
            if name == self.address:
                name = f"0x{self.address[2:6]}...{self.address[-4:]}"
            self.name = name
        else:
            self.name = value
            self.address = get_address_book().name_to_addr(value)
            if self.address is None:
                raise ValueError(f"Cannot resolve '{value}' to an address")

    @classmethod
    def load_list(cls, values: List[str]) -> List["NamedAddress"]:
        return [cls(value) for value in values]


class CallArgument:
    _types = {}

    def __init__(self, value: str, label: str = None, **kwargs):
        self.value = value
        self.label = label

    @classmethod
    def register_type(cls, type: str):
        def decorator(klass):
            cls._types[type] = klass
            return klass

        return decorator

    @classmethod
    def load(cls, arg: dict) -> "CallArgument":
        return cls._types.get(arg["type"], cls)(**arg)

    @property
    def labels(self) -> dict:
        return {self.label: self.value} if self.label else {}

    def __str__(self):
        return self.value


@CallArgument.register_type("address")
class AddressCallArgument(CallArgument):
    def __init__(self, value: str, label: str = None, **kwargs):
        super().__init__(value, label, **kwargs)
        self.address = NamedAddress(value)
        self.value = self.address.address

    @property
    def labels(self) -> dict:
        return (
            {self.label: self.address.name, f"{self.label}_address": self.address.address}
            if self.label
            else {}
        )

    def __str__(self):
        return self.address.name


@dataclass
class CallResult:
    address: Address
    value: Union[int, tuple]
    labels: List[str]


class CallMetricDefinition:
    DEFAULT_LABELS = [
        "contract",
        "contract_address",
    ]

    def __init__(
        self,
        name: str,
        description: str,
        type: str,
        source: str,
        transform: Union[None, str] = None,
        call: "ContractCall" = None,
    ):
        self.name = name
        self.description = description
        self.type = type
        self.source = source

        if transform is not None:
            raise NotImplementedError("To be implemented")
        self.transform = transform

        self.labels = [label for label in self.DEFAULT_LABELS]

        self._metric = None

        self.call = None
        if call is not None:
            self.bind(call)

    @property
    def metric(self):
        # Lazily create the metric to wait until all labels are available
        if self._metric is None:
            self._metric = create_metric(self.name, self.description, self.type, self.labels)
        return self._metric

    def bind(self, call: "ContractCall"):
        call.bind(self)
        self.labels += call.labels
        self.call = call
        for address in call.addresses:
            self.metric.labels(contract=address.name, contract_address=address.address, **call.labels)

    def update(self, results: List[CallResult]):
        for result in results:
            value = result.value
            if isinstance(value, tuple):
                # This is a struct, we need to extract the value from a specific field
                value = getattr(value, self.source)
            self.metric.labels(
                contract=result.address.name,
                contract_address=result.address.address,
                **result.labels,
            ).set(value)


class ContractCall:
    def __init__(
        self,
        contract_type: str,
        function: str,
        arguments: List[CallArgument],
        addresses: List[NamedAddress],
    ):
        self.contract_type = contract_type
        self.abi = contracts.get_artifact_by_name(contract_type).abi
        self.function = function
        self.arguments = arguments
        self.addresses = addresses
        self.metrics: List[CallMetricDefinition] = []

    @property
    def labels(self):
        return dict(label for arg in self.arguments for label in arg.labels.items())

    def bind(self, metric: CallMetricDefinition):
        self.metrics.append(metric)

    async def __call__(self, w3, block, sem: asyncio.Semaphore) -> List[CallResult]:
        async def execute_call(address, func):
            async with sem:
                try:
                    return await func.call(block_identifier=block.number)
                except Exception as e:
                    logger.error("Error calling %s.%s: %s", address.name, func, e)
                    raise

        calls = []
        for address in self.addresses:
            contract = w3.eth.contract(address=address.address, abi=self.abi, decode_tuples=True)
            function = contract.functions[self.function](*[arg.value for arg in self.arguments])
            calls.append(execute_call(address, function))

        results = []
        for address, result in zip(self.addresses, await asyncio.gather(*calls)):
            results.append(CallResult(address=address, value=result, labels=self.labels))

        for metric in self.metrics:
            metric.update(results)

        logger.info("%s: updated %s metrics for %s addresses", self, len(self.metrics), len(self.addresses))

        return results

    def __str__(self):
        return f"{self.contract_type}.{self.function}({','.join(arg.value for arg in self.arguments)})"


@dataclass
class MetricsConfig:
    calls: List[ContractCall]

    @classmethod
    def load(cls, config: dict) -> "MetricsConfig":
        """Load a metrics configuration from a dictionary, usually parsed from a yaml file"""
        calls = []
        for call in config["calls"]:
            contract_call = ContractCall(
                contract_type=call["contract_type"],
                function=call["function"],
                arguments=[CallArgument.load(arg) for arg in call.get("arguments", [])],
                addresses=NamedAddress.load_list(call["addresses"]),
            )

            for source, metric in call["metrics"].items():
                CallMetricDefinition(
                    name=metric["name"],
                    description=metric["description"],
                    type=metric.get("type", "GAUGE"),
                    source=source,
                    call=contract_call,
                )

            calls.append(contract_call)

        return cls(calls=calls)

    @classmethod
    def load_yaml(cls, yaml_file: str) -> "MetricsConfig":

        with open(yaml_file, "r") as f:
            return cls.load(yaml.safe_load(f))
