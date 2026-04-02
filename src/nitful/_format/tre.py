from os import SEEK_CUR
from typing import BinaryIO, cast

from nitful._dsl.rules import (
    BcsString,
    EmitContext,
    Int,
    Item,
    ParseContext,
    Struct,
    item_size,
)
from nitful.core.common import TRE, UnknownTRE

tre_read_registry: dict[str, Struct[TRE]] = {}
tre_write_registry: dict[type[TRE], Struct[TRE]] = {}


def register_tre[T: TRE](tag: str, spec: Struct[T]) -> None:
    tre_read_registry[tag] = cast(Struct[TRE], spec)
    tre_write_registry[spec.model_cls] = cast(Struct[TRE], spec)


def read_tre(fd: BinaryIO, ctx: ParseContext) -> TRE:
    start_pos = fd.tell()

    # length of CETAG and CEL fields.
    peek_len = 11

    header = fd.read(peek_len)
    if len(header) != peek_len:
        msg = "Unexpected EOF while reading TRE header."
        raise RuntimeError(msg)

    tag = header[:6].decode().strip()
    try:
        cel = int(header[6:].decode())
    except ValueError as e:
        msg = f"Invalid TRE length field in tag '{tag}': {header[6:]!r}"
        raise RuntimeError(msg) from e

    if tag in tre_read_registry:
        fd.seek(-peek_len, SEEK_CUR)
        spec = tre_read_registry[tag]
        parsed_tre = spec.parse(fd, ctx)
    else:
        parsed_tre = UnknownTRE(CETAG=tag, raw_data=fd.read(cel))

    expected_end = start_pos + peek_len + cel
    actual_end = fd.tell()

    if actual_end != expected_end:
        fd.seek(expected_end)
        total = actual_end - start_pos - peek_len
        msg = f"TRE '{tag}' has payload len (CEL) {cel}, but {total} bytes were read."
        raise RuntimeError(msg)

    return parsed_tre


def read_tre_list(
    fd: BinaryIO, len_name: str, ofl_name: str, ctx: ParseContext
) -> list[TRE]:
    tres: list[TRE] = []
    ctx = ParseContext()
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
