from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, BinaryIO, cast, override

from nitful.core.common import TRE, UnknownTRE
from nitful.dsl.rules import (
    BcsString,
    Combinator,
    EmitContext,
    Int,
    Item,
    ParseContext,
    PrefixedBytes,
    Struct,
    item_size,
)

tre_read_registry: dict[str, Struct[TRE]] = {}
tre_write_registry: dict[type[TRE], Struct[TRE]] = {}


def register_tre[T: TRE](tag: str, spec: Struct[T]) -> None:
    tre_read_registry[tag] = cast(Struct[TRE], spec)
    tre_write_registry[spec.model_cls] = cast(Struct[TRE], spec)


@contextmanager
def disable_tre_parsing() -> Generator[None]:
    saved_read = tre_read_registry.copy()
    saved_write = tre_write_registry.copy()

    tre_read_registry.clear()
    tre_write_registry.clear()

    try:
        yield
    finally:
        tre_read_registry.update(saved_read)
        tre_write_registry.update(saved_write)


unknown_tre_spec = Struct(
    UnknownTRE,
    [
        BcsString("CETAG", 6),
        PrefixedBytes(
            len_rule=Int("CEL", 5),
            name="CEDATA",
        ),
    ],
)


def read_tre(fd: BinaryIO, ctx: ParseContext) -> TRE:
    # Peek at the CETAG and CEL fields.
    start_pos = fd.tell()
    header_len = 11
    header = fd.read(header_len)
    fd.seek(start_pos)

    if len(header) != header_len:
        msg = "Unexpected EOF while reading TRE header."
        raise RuntimeError(msg)

    tag = header[:6].decode().strip()
    try:
        cel = int(header[6:].decode())
    except ValueError as e:
        msg = f"Invalid TRE length field in tag '{tag}': {header[6:]!r}"
        raise RuntimeError(msg) from e

    if tag in tre_read_registry:
        parsed_tre = tre_read_registry[tag].parse(fd, ctx)
    else:
        parsed_tre = unknown_tre_spec.parse(fd, ctx)

    expected_end = start_pos + header_len + cel
    actual_end = fd.tell()
    if actual_end != expected_end:
        fd.seek(expected_end)
        total = actual_end - start_pos - header_len
        msg = f"TRE '{tag}' has payload len (CEL) {cel}, but {total} bytes were read."
        raise RuntimeError(msg)

    return parsed_tre


def tre_to_fields(tre: TRE, ctx: EmitContext) -> list[Item]:

    if isinstance(tre, UnknownTRE):
        return unknown_tre_spec.to_fields(tre, ctx)

    tre_type = type(tre)
    if tre_type not in tre_write_registry:
        msg = f"Unregistered TRE class: {tre_type.__name__}"
        raise TypeError(msg)

    spec = tre_write_registry[tre_type]
    return spec.to_fields(tre, ctx)


@dataclass
class TreBlock(Combinator[Any]):
    """Parse and emit TRE blocks, such as UDHD.

    The NITF file header and segments each include one or two lists of TREs.
    The TRE data can also overflow into a DES.

    Because this is an anonymous rule, it injects the length, overflow, and
    list of TREs directly into the current scope during parsing, to be unpacked
    into the full dataclass. It also extracts them from the full context
    dictionary during emit.
    """

    len_name: str
    ofl_name: str
    data_name: str

    name: str = field(default="", init=False)

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> None:
        tres: list[TRE] = []

        length = Int(self.len_name, 5).parse(fd, ctx)

        # Add default values to the context if there's nothing else to parse.
        if length == 0:
            ctx[self.ofl_name] = 0
            ctx[self.data_name] = tres
            return

        # Otherwise, Int.parse automatically puts ofl_name into the context.
        Int(self.ofl_name, 3).parse(fd, ctx)

        start_pos = fd.tell()
        end_pos = start_pos + (length - 3)

        while fd.tell() < end_pos:
            tres.append(read_tre(fd, ctx))

        if fd.tell() > end_pos:
            msg = f"{self.len_name} is {length}, but read {end_pos - start_pos} bytes"
            raise RuntimeError(msg)

        # Add the parsed TREs to the context.
        ctx[self.data_name] = tres

    @override
    def _emit(self, value: dict[str, Any], *, ctx: EmitContext) -> list[Item]:
        tres: list[TRE] = value[self.data_name]
        overflow: int = value[self.ofl_name]

        if not tres and overflow == 0:
            return Int(self.len_name, 5).to_fields(0, ctx)

        data_fields = Int(self.ofl_name, 3).to_fields(overflow, ctx)

        for tre in tres:
            data_fields.extend(tre_to_fields(tre, ctx))

        # This will throw if there is too much data.
        length_fields = Int(self.len_name, 5).to_fields(item_size(data_fields), ctx)

        return [*length_fields, *data_fields]
