from types import SimpleNamespace

from eth_exporter.chaindata import AddressCallArgument, NamedAddress, contracts
from eth_exporter.metric_config import MetricsConfig
from eth_exporter.metric_config.ensuro import pa_loans_handler
from eth_exporter.metric_config.standard import erc20_balance_handler
from eth_exporter.vendor import address_book

USDC = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
SOME_ADDRESS = "0x976EA74026E726554dB657fA54763abd0C3a0aa9"


def test_named_address_resolves_name_to_address():
    address_book.setup_default(address_book.NameToAddrAddressBook({"USDC": address_book.Address(USDC)}))

    named = NamedAddress("USDC")

    assert named.name == "USDC"
    assert named.address == USDC


def test_named_address_resolves_address_to_name():
    address_book.setup_default(address_book.AddrToNameAddressBook({address_book.Address(USDC): "USDC"}))

    named = NamedAddress(USDC)

    assert named.name == "USDC"
    assert named.address == USDC


def test_address_call_argument_exposes_name_and_address_labels():
    address_book.setup_default(address_book.AddrToNameAddressBook({address_book.Address(USDC): "USDC"}))

    arg = AddressCallArgument(value=USDC, label="holder")

    assert arg.value == USDC
    assert arg.labels == {"holder": "USDC", "holder_address": USDC}


def test_erc20_balance_handler_builds_total_supply_and_balance_calls():
    calls = erc20_balance_handler(
        {
            "usdc_balance": {
                "address": USDC,
                "holders": [SOME_ADDRESS],
                "metric": {"name": "usdc_balance", "type": "GAUGE", "description": "USDC balance"},
            }
        }
    )

    assert len(calls) == 2

    total_supply, balance_of = calls

    assert total_supply["contract_type"] == "ERC20"
    assert total_supply["function"] == "totalSupply"
    assert total_supply["addresses"] == [USDC]
    assert total_supply["metrics"] == {
        "result": {"name": "erc20_total_supply", "type": "GAUGE", "description": "ERC20 Total supply"}
    }

    assert balance_of["contract_type"] == "ERC20"
    assert balance_of["function"] == "balanceOf"
    assert balance_of["arguments"] == [{"value": SOME_ADDRESS, "type": "address", "label": "holder"}]
    assert balance_of["metrics"] == {"result": {"name": "usdc_balance", "type": "GAUGE", "description": "USDC balance"}}


def test_pa_loans_handler_builds_limit_and_loan_calls():
    calls = pa_loans_handler(
        {
            "premiums_account": {
                "limit_function": "getLoanLimit",
                "loans": [{"borrower": SOME_ADDRESS, "etoken": USDC}],
                "metric": {"type": "GAUGE", "description": "Premiums account loan"},
            }
        }
    )

    assert len(calls) == 2

    limit_call, loan_call = calls

    assert limit_call["contract_type"] == "PremiumsAccount"
    assert limit_call["function"] == "getLoanLimit"
    assert limit_call["addresses"] == [SOME_ADDRESS]

    assert loan_call["contract_type"] == "EToken"
    assert loan_call["function"] == "getLoan"
    assert loan_call["addresses"] == [USDC]
    assert loan_call["arguments"] == [{"value": SOME_ADDRESS, "type": "address", "label": "premiums_account"}]
    assert loan_call["metrics"]["result"]["name"] == "premiums_account"


def test_metrics_config_loads_direct_calls(mocker):
    mocker.patch.object(contracts, "get_artifact_by_name", return_value=SimpleNamespace(abi=[]))

    metrics_config = MetricsConfig.load(
        {
            "calls": [
                {
                    "contract_type": "ERC20",
                    "function": "balanceOf",
                    "arguments": [{"value": SOME_ADDRESS, "type": "address", "label": "holder"}],
                    "addresses": [USDC],
                    "metrics": {"result": {"name": "usdc_balance", "type": "GAUGE", "description": "USDC balance"}},
                }
            ]
        }
    )

    assert len(metrics_config.calls) == 1
    call = metrics_config.calls[0]
    assert call.contract_type == "ERC20"
    assert call.function == "balanceOf"
    assert len(call.metrics) == 1
    assert call.metrics[0].name == "usdc_balance"
