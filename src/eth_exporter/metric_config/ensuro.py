from typing import TypedDict

from .base import HandlerRegistry
from .types import Argument, Call, MetricDef

__all__ = []


class Loan(TypedDict):
    borrower: str | list[str]
    etoken: str


class PALoanConfig(TypedDict):
    limit_function: str
    loans: list[Loan]
    metric: MetricDef


@HandlerRegistry.register_handler("pa_loans")
def pa_loans_handler(metric_config: dict[str:PALoanConfig]) -> list[Call]:
    calls = []
    for metric_name, details in metric_config.items():
        for loan in details["loans"]:
            borrowers = loan["borrower"] if isinstance(loan["borrower"], list) else [loan["borrower"]]
            # Get the loan limit on all borrowers
            calls.append(
                Call(
                    contract_type="PremiumsAccount",
                    function=details["limit_function"],
                    arguments=[],
                    addresses=borrowers,
                    metrics={
                        "result": {
                            "name": f"{metric_name}_limit",
                            "type": "GAUGE",
                            "description": "Premiums account loan limit",
                        }
                    },
                )
            )

            for borrower in borrowers:
                # Get the current loan for each borrower
                calls.append(
                    Call(
                        contract_type="EToken",
                        function="getLoan",
                        arguments=[Argument(value=borrower, type="address", label="premiums_account")],
                        addresses=[loan["etoken"]],
                        metrics={
                            "result": {"name": metric_name} | details["metric"],
                        },
                    )
                )

    return calls
