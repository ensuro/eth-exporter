import asyncio
import logging
from dataclasses import dataclass
from typing import List, Union

import yaml

from . import config, multicall3
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
    def load_list(cls, values: List[str] | str) -> List["NamedAddress"]:
        return [cls(value) for value in values] if isinstance(values, list) else [cls(values)]


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
        if self.type != "GAUGE":
            # Initializing GAUGE metrics with 0 causes issues for alerting and graphing, better to
            # have them missing until there's a value
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
        return f"{self.contract_type}.{self.function}({','.join(str(arg.value) for arg in self.arguments)})"


class ContractCallMulticall3(ContractCall):
    async def __call__(self, w3, block, sem: asyncio.Semaphore) -> List[CallResult]:
        functions = []
        for address in self.addresses:
            contract = w3.eth.contract(address=address.address, abi=self.abi, decode_tuples=True)
            function = contract.functions[self.function](*[arg.value for arg in self.arguments])
            functions.append(function)

        errors = 0
        results = []
        async with sem:
            chain_results = await multicall3.aggregate3(w3, functions, block.number)

        for address, function, (success, result) in zip(self.addresses, functions, chain_results):
            if not success:
                logger.error("Error calling %s.%s: %s", address.name, function, result)
                errors += 1
            else:
                results.append(CallResult(address=address, value=result, labels=self.labels))

        if errors:
            raise RuntimeError(f"{errors} errors calling {self.function}")

        for metric in self.metrics:
            metric.update(results)

        logger.info("%s: updated %s metrics for %s addresses", self, len(self.metrics), len(self.addresses))

        return results


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
        calls = cls._load_direct_calls(config.get("calls", []))
        erc20_balance_calls = cls._load_erc20_calls(config.get("erc20_balance", {}))
        erc4626_balance_calls = cls._load_erc4626_calls(config.get("erc4626_balance", {}))
        pa_loan_calls = cls._load_pa_loan_calls(config.get("pa_loans", {}))

        return cls(calls=calls + erc20_balance_calls + erc4626_balance_calls + pa_loan_calls)

    @classmethod
    def load_yaml(cls, yaml_file: str) -> "MetricsConfig":
        with open(yaml_file, "r") as f:
            return cls.load(yaml.safe_load(f))

    @classmethod
    def _load_direct_calls(cls, call_definitions) -> List[ContractCall]:
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

    @classmethod
    def _load_erc20_calls(cls, erc20_calls: dict) -> List[ContractCall]:
        calls = []

        for metric_name, details in erc20_calls.items():
            if details.get("total_supply_function", "totalSupply") is not None:
                calls.append(cls._token_total_supply_call(details["address"], "erc20_total_supply"))

            calls += cls._token_balance_calls(
                details["address"], details["holders"], metric_name, details.get("metric", {})
            )

        return calls

    @classmethod
    def _load_erc4626_calls(cls, erc4626_calls: dict) -> List[ContractCall]:
        calls = []

        for metric_name, details in erc4626_calls.items():
            total_supply_function = details.get("total_supply_function", "totalSupply")
            if total_supply_function is not None:
                calls.append(
                    cls._token_total_supply_call(
                        details["address"],
                        "erc4626_total_supply",
                        metric_description="Vault total supply in shares",
                        function_name=total_supply_function,
                    )
                )
            calls.append(
                cls._vault_to_assets_call(
                    details["address"], "erc4626_shares_to_assets", details.get("metric", {})
                )
            )

            calls += cls._token_balance_calls(
                details["address"], details["holders"], metric_name, details.get("metric", {})
            )

        return calls

    @classmethod
    def _load_pa_loan_calls(cls, pa_loans: dict) -> List[ContractCall]:
        calls = []

        for metric_name, details in pa_loans.items():
            metric_config = details.get("metric", {})
            for loan in details["loans"]:
                # Get the loan limit on all borrowers
                loan_limit_call = cls.contract_call_class()(
                    contract_type="PremiumsAccount",
                    function=details["limit_function"],
                    arguments=[],
                    addresses=NamedAddress.load_list(loan["borrower"]),
                )
                calls.append(loan_limit_call)
                CallMetricDefinition(
                    name=f"{metric_name}_limit",
                    description=metric_config.get("description", "Premiums account loan limit"),
                    type="GAUGE",
                    source=f"{metric_name}_limit",
                    call=loan_limit_call,
                )

                # Get the current loan for each borrower
                borrower = loan["borrower"]
                if not isinstance(borrower, list):
                    borrower = [borrower]
                for borrower in borrower:
                    current_loan_call = cls.contract_call_class()(
                        contract_type="EToken",
                        function="getLoan",
                        arguments=[AddressCallArgument(borrower, label="premiums_account")],
                        addresses=NamedAddress.load_list([loan["etoken"]]),
                    )
                    calls.append(current_loan_call)
                    CallMetricDefinition(
                        name=metric_name,
                        description=metric_config.get("description", "Premiums account loan"),
                        type=metric_config.get("type", "GAUGE"),
                        source=metric_name,
                        call=current_loan_call,
                    )

        return calls

    @classmethod
    def _token_balance_calls(
        cls, tokens: list[str], holders: list[str], metric_name: str, metric_config: dict
    ):
        calls = []
        tokens = NamedAddress.load_list(tokens)
        for holder in holders:
            contract_call = cls.contract_call_class()(
                contract_type="ERC4626",
                function="balanceOf",
                arguments=[AddressCallArgument(holder, label="holder")],
                addresses=tokens,
            )
            calls.append(contract_call)
            CallMetricDefinition(
                name=metric_name,
                description=metric_config.get("description", f"Balance of {tokens}"),
                type=metric_config.get("type", "GAUGE"),
                source=metric_name,
                call=contract_call,
            )
        return calls

    @classmethod
    def _token_total_supply_call(
        cls,
        tokens: list[str],
        metric_name: str,
        metric_description="Token total supply",
        function_name="totalSupply",
    ) -> ContractCall:
        """Gets token total supply"""
        call = ContractCall(
            contract_type="ERC20",
            function=function_name,
            arguments=[],
            addresses=NamedAddress.load_list(tokens),
        )
        CallMetricDefinition(
            name=metric_name,
            description=metric_description,
            type="GAUGE",
            source=metric_name,
            call=call,
        )
        return call

    @classmethod
    def _vault_to_assets_call(
        cls, vaults: list[str], metric_name: str, metric_config: dict = None, function_name="convertToAssets"
    ) -> ContractCall:
        """Gets shares to assets conversion ratio for ERC4626 vaults"""
        if metric_config is None:
            metric_config = {}
        call = ContractCall(
            contract_type="ERC4626",
            function=function_name,
            arguments=[CallArgument(int(1e18))],
            addresses=NamedAddress.load_list(vaults),
        )
        CallMetricDefinition(
            name=metric_name,
            description=metric_config.get("description", "Vault shares to assets conversion"),
            type=metric_config.get("type", "GAUGE"),
            source=metric_name,
            call=call,
        )
        return call
