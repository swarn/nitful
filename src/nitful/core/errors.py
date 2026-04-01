from dataclasses import dataclass
from typing import ClassVar, override


class NitfError(Exception):
    """Base exception for all nitful library errors."""


@dataclass
class SpecError(NitfError):
    """Base exception for errors during parsing and serialization."""

    base_msg: str
    path: list[str]
    offset: int
    history: str

    action: ClassVar[str] = "processing"

    def __post_init__(self) -> None:
        super().__init__(self.__str__())

    @override
    def __str__(self) -> str:
        msg = f"Error {self.action} at byte [{self.offset}]"

        msg += f"\n\nCause: {self.base_msg}"

        path_str = "\n  -> ".join(self.path)
        msg += f"\n\nWhere:\n  {path_str}"

        if self.history:
            msg += f"\n\nRecent fields:\n{self.history}"

        return msg


@dataclass
class ParseError(SpecError):
    action: ClassVar[str] = "parsing"


@dataclass
class SerializeError(SpecError):
    action: ClassVar[str] = "emitting"
