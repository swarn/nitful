"""Field validators.

A collection of common functions used to validate user-provided values before
serializing.

- Any callable that accepts a value and returns a boolean can be a validator;
  the callables in this module are not special, just commonly useful.

- The goal in nitful is not to validate the full domain logic of NITF headers
  and segments, only what can be reasonably checked on individual fields.

- `Field` rules have a size attribute and automatically check that the
  serialized value fits within that size. E.g., there is no need to check that
  a four-digit integer is <= 9999.
"""

# ruff: noqa: N801

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol, override

type NumericT = int | float | Decimal


def nonzero(val: NumericT) -> bool:
    return val != 0


def nonnegative(val: NumericT) -> bool:
    return val >= 0


def positive(val: NumericT) -> bool:
    return val > 0


class Comparable(Protocol):

    def __le__(self, other: Any, /) -> bool: ...
    def __ge__(self, other: Any, /) -> bool: ...


@dataclass
class in_range[T: Comparable]:
    min_val: T
    max_val: T

    def __call__(self, val: T) -> bool:
        return self.min_val <= val <= self.max_val


class one_of[T]:
    options: tuple[T, ...]

    def __init__(self, *options: T) -> None:
        self.options = options

    def __call__(self, val: T) -> bool:
        return val in self.options

    @override
    def __repr__(self) -> str:
        args = ", ".join(repr(opt) for opt in self.options)
        return f"one_of({args})"


def notblank(val: str) -> bool:
    return len(val) > 0 and not val.isspace()
