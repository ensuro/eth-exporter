# Copied from eth-pretty-events v0.0.5. We can't pull it in as a dependency yet because we're using web3py v7

from abc import ABC, abstractmethod
from typing import Dict, Optional, Union

from eth_utils.address import is_checksum_address, to_checksum_address
from hexbytes import HexBytes


class Address(str):
    def __new__(cls, value: Union[HexBytes, str]):
        if isinstance(value, HexBytes):
            value = value.hex()
            if len(value) != 42:
                raise ValueError(f"'{value}' is not a valid address")
            value = to_checksum_address(value)
        elif isinstance(value, str) and value == value.lower():
            value = to_checksum_address(value)
        elif not is_checksum_address(value):
            raise ValueError(f"'{value}' is not a valid address")

        return str.__new__(cls, value)


class AddressBook(ABC):
    @abstractmethod
    def addr_to_name(self, addr: Address) -> Union[str, Address]:
        """Returns the name associated with a given address, if found, otherwise returns the same addr"""
        ...

    @abstractmethod
    def name_to_addr(self, name: str) -> Optional[Address]:
        """Returns the address associated with a given name, if found, otherwise returns None"""
        ...

    @abstractmethod
    def has_addr(self, addr: Address) -> bool:
        """Returns if the AddressBook has a name associated to the address"""
        ...


class DummyAddressBook(AddressBook):
    def addr_to_name(self, addr: Address) -> Union[str, Address]:
        return addr

    def name_to_addr(self, name: str) -> Optional[Address]:
        return None

    def has_addr(self, addr: Address) -> bool:
        return False


_default_addr_book: AddressBook = DummyAddressBook()


class AddressMapAddressBook(AddressBook):
    reverse_address_map: Dict[Address, str]
    address_map: Dict[str, Address]

    def addr_to_name(self, addr: Address) -> Union[str, Address]:
        return self.reverse_address_map.get(addr, addr)

    def name_to_addr(self, name: str) -> Optional[Address]:
        return self.address_map.get(name, None)

    def has_addr(self, addr: Address) -> bool:
        return addr in self.reverse_address_map


class AddrToNameAddressBook(AddressMapAddressBook):
    def __init__(self, reverse_address_map: Dict[Address, str]):
        self.reverse_address_map = reverse_address_map
        self.address_map = dict((v, k) for (k, v) in reverse_address_map.items())


class NameToAddrAddressBook(AddressMapAddressBook):
    def __init__(self, address_map: Dict[str, Address]):
        self.address_map = address_map
        self.reverse_address_map = dict((v, k) for (k, v) in address_map.items())


def setup_default(addr_book: AddressBook):
    global _default_addr_book
    _default_addr_book = addr_book


def get_default() -> AddressBook:
    return _default_addr_book
