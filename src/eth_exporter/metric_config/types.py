from typing import Literal, TypedDict


class Argument(TypedDict):
    """An argument for a contract call as defined in the metrics config."""

    value: str
    type: str
    label: str | None


class MetricDef(TypedDict):
    name: str
    type: Literal["GAUGE", "COUNTER", "HISTOGRAM"]
    description: str


class Call(TypedDict):
    """A call as defined in the metrics config."""

    contract_type: str
    function: str
    arguments: list[Argument]
    addresses: list[str]
    metrics: dict[str, MetricDef]
