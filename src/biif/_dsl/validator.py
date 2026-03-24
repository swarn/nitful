from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import override

type Numeric = int | float | Decimal


class Validator[T](ABC):

    @abstractmethod
    def __call__(self, val: T) -> bool:
        pass


class NonZero[T: Numeric](Validator[T]):

    @override
    def __call__(self, val: T) -> bool:
        return val != 0


class NonNegative[T: Numeric](Validator[T]):

    @override
    def __call__(self, val: T) -> bool:
        return val >= 0


class Positive[T: Numeric](Validator[T]):

    @override
    def __call__(self, val: T) -> bool:
        return val > 0


@dataclass
class Range[T: Numeric](Validator[T]):

    min: T
    max: T

    @override
    def __call__(self, val: T) -> bool:
        return self.min <= val <= self.max


@dataclass
class Literals[T](Validator[T]):

    options: list[T]

    @override
    def __call__(self, val: T) -> bool:
        return val in self.options


class NotBlank(Validator[str]):

    @override
    def __call__(self, val: str) -> bool:
        return len(val) > 0 and not val.isspace()
