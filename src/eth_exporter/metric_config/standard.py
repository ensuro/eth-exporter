from typing import TypedDict

from .base import HandlerRegistry
from .types import Argument, Call, MetricDef

__all__ = []


class ERC20BalanceConfig(TypedDict):
    address: str | list[str]
    metric: MetricDef
    holders: list[str]


@HandlerRegistry.register_handler("erc20_balance")
def erc20_balance_handler(metric_config: dict[str:ERC20BalanceConfig]) -> list[Call]:
    calls = []
    for metric_name, details in metric_config.items():
        addresses = details["address"] if isinstance(details["address"], list) else [details["address"]]
        total_supply_function = details.get("total_supply_function", "totalSupply")
        if total_supply_function is not None:
            calls.append(
                create_total_supply_call(
                    addresses, "erc20_total_supply", "ERC20 Total supply", total_supply_function
                )
            )

        calls += create_erc20_balance_calls(addresses, details["holders"], metric_name, details["metric"])

    return calls


class ERC4626BalanceConfig(ERC20BalanceConfig):
    ...


@HandlerRegistry.register_handler("erc4626_balance")
def erc4626_balance_handler(metric_config: dict[str:ERC4626BalanceConfig]) -> list[Call]:
    calls = []
    for metric_name, details in metric_config.items():
        addresses = details["address"] if isinstance(details["address"], list) else [details["address"]]
        total_supply_function = details.get("total_supply_function", "totalSupply")
        if total_supply_function is not None:
            calls.append(
                create_total_supply_call(
                    addresses, "erc4626_total_supply", "ERC20 Total supply", total_supply_function
                )
            )

        # Get the shares to assets conversion
        calls.append(
            Call(
                contract_type="ERC4626",
                function="convertToAssets",
                arguments=[Argument(value=int(1e18))],
                addresses=addresses,
                metrics={
                    "result": {
                        "name": "erc4626_shares_to_assets",
                        "type": "GAUGE",
                        "description": "Vault shares to assets conversion",
                    }
                },
            )
        )

        calls += create_erc20_balance_calls(addresses, details["holders"], metric_name, details["metric"])

    return calls


def create_total_supply_call(
    tokens: list[str], metric_name: str, metric_description: str, function_name="totalSupply"
) -> Call:
    """Create a call for the total supply of ERC20 tokens."""
    return Call(
        contract_type="ERC20",
        function=function_name,
        arguments=[],
        addresses=tokens,
        metrics={"result": MetricDef(name=metric_name, type="GAUGE", description=metric_description)},
    )


def create_erc20_balance_calls(
    tokens: list[str], holders: list[str], metric_name: str, metric_config: MetricDef
) -> list[Call]:
    """Create calls for the balance of ERC20 tokens."""
    calls = []
    for holder in holders:
        calls.append(
            Call(
                contract_type="ERC20",
                function="balanceOf",
                arguments=[Argument(value=holder, type="address", label="holder")],
                addresses=tokens,
                metrics={"result": {"name": metric_name} | metric_config},
            )
        )
    return calls
