import asyncio
import logging
from dataclasses import dataclass
from typing import List, Union

import yaml

from . import config
from .build_artifacts import ArtifactLibrary
from .metrics import create_metric

contracts = ArtifactLibrary(config.ABIS_PATH)


logger = logging.getLogger(__name__)


class CallArgument:
    def __init__(self, value: str, label: str = None, transform: Union[str, None] = None):
        self.value = value

        if transform is not None:
            raise NotImplementedError("To be implemented")

        self.transform = transform
        self.label = label

    def __str__(self):
        return self.value


@dataclass
class CallResult:
    address: str
    value: Union[int, tuple]
    labels: List[str]


class CallMetricDefinition:
    DEFAULT_LABELS = [
        "address",
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
            self.metric.labels(address=address, **call.labels)

    def update(self, results: List[CallResult]):
        for result in results:
            value = result.value
            if isinstance(value, tuple):
                # This is a struct, we need to extract the value from a specific field
                value = getattr(value, self.source)
            self.metric.labels(address=result.address, **result.labels).set(value)


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
        self.metrics: List[CallMetricDefinition] = []

    @property
    def labels(self):
        return {arg.label: arg.value for arg in self.arguments if arg.label}

    def bind(self, metric: CallMetricDefinition):
        self.metrics.append(metric)

    async def __call__(self, w3, block) -> List[CallResult]:
        calls = []
        for address in self.addresses:
            contract = w3.eth.contract(address=address, abi=self.abi, decode_tuples=True)
            function = contract.functions[self.function](*[arg.value for arg in self.arguments])
            calls.append(function.call(block_identifier=block.number))

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
                arguments=[CallArgument(**arg) for arg in call.get("arguments", [])],
                addresses=call["addresses"],
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
