from collections.abc import Iterator
from contextlib import contextmanager
from typing import BinaryIO, cast

from nitful.core.common import TRE, UnknownTRE
from nitful.dsl.rules import (
    BcsString,
    EmitContext,
    FixedBytes,
    Int,
    Item,
    ParseContext,
    Struct,
    item_size,
)

tre_read_registry: dict[str, Struct[TRE]] = {}
tre_write_registry: dict[type[TRE], Struct[TRE]] = {}


def register_tre[T: TRE](tag: str, spec: Struct[T]) -> None:
    tre_read_registry[tag] = cast(Struct[TRE], spec)
    tre_write_registry[spec.model_cls] = cast(Struct[TRE], spec)


@contextmanager
def disable_tre_parsing() -> Iterator[None]:
    saved_read = tre_read_registry.copy()
    saved_write = tre_write_registry.copy()

    tre_read_registry.clear()
    tre_write_registry.clear()

    try:
        yield
    finally:
        tre_read_registry.update(saved_read)
        tre_write_registry.update(saved_write)


def make_unknown_spec(cel: int) -> Struct[UnknownTRE]:
    return Struct(
        UnknownTRE,
        [
            BcsString("CETAG", 6),
            Int("CEL", 5),
            FixedBytes("raw_data", cel),
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
        parsed_tre = make_unknown_spec(cel).parse(fd, ctx)

    expected_end = start_pos + header_len + cel
    actual_end = fd.tell()
    if actual_end != expected_end:
        fd.seek(expected_end)
        total = actual_end - start_pos - header_len
        msg = f"TRE '{tag}' has payload len (CEL) {cel}, but {total} bytes were read."
        raise RuntimeError(msg)

    return parsed_tre


def read_tre_list(
    fd: BinaryIO, len_name: str, ofl_name: str, ctx: ParseContext
) -> list[TRE]:
    tres: list[TRE] = []
    length = Int(len_name, 5).parse(fd, ctx)
    if length > 0:
        overflow = Int(ofl_name, 3).parse(fd, ctx)
        if overflow > 0:
            msg = "TRE overflow is not supported."
            raise NotImplementedError(msg)

        end_pos = fd.tell() + (length - 3)
        while fd.tell() < end_pos:
            tres.append(read_tre(fd, ctx))

    return tres


def tre_to_fields(tre: TRE, ctx: EmitContext) -> list[Item]:

    if isinstance(tre, UnknownTRE):
        tag_field = BcsString("CETAG", 6).to_fields(tre.CETAG, ctx)
        len_field = Int("CEL", 5).to_fields(len(tre.raw_data), ctx)
        data_field = Item(name="CEDATA", value=tre.raw_data)
        return [*tag_field, *len_field, data_field]

    tre_type = type(tre)
    if tre_type not in tre_write_registry:
        msg = f"Unregistered TRE class: {tre_type.__name__}"
        raise TypeError(msg)

    spec = tre_write_registry[tre_type]
    return spec.to_fields(tre, ctx)


def tre_list_to_fields(
    tres: list[TRE], len_name: str, ofl_name: str, ctx: EmitContext
) -> list[Item]:
    ctx = EmitContext()

    if not tres:
        return Int(len_name, 5).to_fields(0, ctx)

    hd_fields: list[Item] = []
    for tre in tres:
        hd_fields.extend(tre_to_fields(tre, ctx))

    hd_len = Int(len_name, 5).to_fields(item_size(hd_fields) + 3, ctx)
    of_len = Int(ofl_name, 3).to_fields(0, ctx)

    return [*hd_len, *of_len, *hd_fields]
