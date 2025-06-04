import json
import logging
from dataclasses import dataclass
from typing import Callable, List

import yaml

from .. import config
from ..chaindata import (
    CallArgument,
    CallMetricDefinition,
    ContractCall,
    ContractCallMulticall3,
    NamedAddress,
)
from .types import Call

logger = logging.getLogger(__name__)


class HandlerRegistry:
    """Handlers are used to pre-process the metrics configuration.

    Each handler receives a value defined in the configuration for a given type_key and return
    s a list of Call objects.
    """

    _registry = {}

    @classmethod
    def register_handler(cls, type_key: str):
        def do_register(handler: Callable[[dict], list[Call]]):
            cls._registry[type_key] = handler

        return do_register

    @classmethod
    def get_handler(cls, type_key: str) -> Callable[[dict], list[Call]]:
        """Get a handler for a given type_key, raises KeyError if not found."""
        if type_key not in cls._registry:
            raise KeyError(f"No handler registered for type_key: {type_key}")
        return cls._registry[type_key]


@dataclass
class MetricsConfig:
    calls: List[ContractCall]

    @classmethod
    def contract_call_class(cls):
        if config.USE_MULTICALL3:
            return ContractCallMulticall3
        else:
            return ContractCall

    @classmethod
    def load(cls, config: dict) -> "MetricsConfig":
        """Load a metrics configuration from a dictionary, usually parsed from a yaml file"""
        call_configs: list[Call] = config.get("calls", [])

        for type_key in config.keys():
            if type_key == "calls":
                continue
            handler = HandlerRegistry.get_handler(type_key)
            call_configs += handler(config[type_key])

        logger.debug("Calls: %s", json.dumps(call_configs, indent=2))

        return cls(calls=cls._load_direct_calls(call_configs))

    @classmethod
    def load_yaml(cls, yaml_file: str) -> "MetricsConfig":
        with open(yaml_file, "r") as f:
            return cls.load(yaml.safe_load(f))

    @classmethod
    def _load_direct_calls(cls, call_definitions: List[Call]) -> List[ContractCall]:
        calls = []
        for call in call_definitions:
            contract_call = cls.contract_call_class()(
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
        return calls
