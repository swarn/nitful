from collections.abc import Generator
from contextlib import contextmanager
from typing import BinaryIO, cast

from nitful.core.common import DES, UnknownDES
from nitful.core.errors import ParseError
from nitful.dsl.rules import (
    BcsString,
    Constant,
    EmitContext,
    FixedBytes,
    Int,
    Item,
    ParseContext,
)

from .shared import Segment, security_len, security_spec

des_read_registry: dict[tuple[str, int], Segment[DES]] = {}
des_write_registry: dict[type[DES], Segment[DES]] = {}


def register_des[T: DES](desid: str, desver: int, spec: Segment[T]) -> None:
    """Register a specification for a DES."""
    des_read_registry[desid, desver] = cast(Segment[DES], spec)
    des_write_registry[spec.model_cls] = cast(Segment[DES], spec)


@contextmanager
def disable_des_parsing() -> Generator[None]:
    saved_read = des_read_registry.copy()
    saved_write = des_write_registry.copy()

    des_read_registry.clear()
    des_write_registry.clear()

    try:
        yield
    finally:
        des_read_registry.update(saved_read)
        des_write_registry.update(saved_write)


def make_unknown_spec(header_len: int, data_len: int) -> Segment[UnknownDES]:
    return Segment[UnknownDES](
        UnknownDES,
        subheader=[
            Constant(BcsString("DE", 2), "DE"),
            BcsString("DESID", 25),
            Int("DESVER", 2),
            security_spec("DE"),
            FixedBytes("DESSH", header_len - security_len - 29),
        ],
        data=[
            FixedBytes("DESDATA", data_len),
        ],
    )


def read_des(fd: BinaryIO, header_len: int, data_len: int, ctx: ParseContext) -> DES:

    start_pos = fd.tell()

    # Length of "DE", "DESID", and "DESVER" fields.
    peek_len = 29

    first = fd.read(peek_len)
    if len(first) != peek_len:
        msg = ctx.format_error("Unexpected EOF while reading DES header.", start_pos)
        raise ParseError(msg)

    fd.seek(start_pos)

    if first[:2].decode() != "DE":
        msg = ctx.format_error(
            "Expected DES, but first characters were not 'DE'", start_pos
        )
        raise ParseError(msg)

    desid = first[2:27].decode().strip()
    desver = int(first[27:29].decode())

    if (desid, desver) in des_read_registry:
        # Add the size of the DES to the context so the spec can read it.
        ctx["_CURRENT_DES_DATA_LEN"] = data_len

        spec = des_read_registry[desid, desver]
        des = spec.parse(fd, ctx)
    else:
        unknown_spec = make_unknown_spec(header_len, data_len)
        des = unknown_spec.parse(fd, ctx)

    end_pos = fd.tell()
    n_bytes_read = end_pos - start_pos
    n_bytes_expected = header_len + data_len

    if n_bytes_read != n_bytes_expected:
        last_n = min(40, n_bytes_read)
        fd.seek(end_pos - last_n)
        last_bytes = fd.read(last_n)

        msg = (
            f"DES length mismatch for {desid} v{desver}: "
            f"Expected {header_len + data_len}, but consumed {n_bytes_read}."
            f"\n\nRecent fields:\n{ctx.format_fields()}"
            f"\n\nLast {last_n} bytes: {last_bytes!r}"
        )

        if n_bytes_read < n_bytes_expected:
            unread_n = n_bytes_expected - n_bytes_read
            unread_bytes = fd.read(unread_n)
            msg += f"\n\nUnread {unread_n} bytes: {unread_bytes!r}"
        else:
            extra_n = n_bytes_read - n_bytes_expected
            fd.seek(end_pos - extra_n)
            extra_bytes = fd.read(extra_n)
            msg += f"\n\nExtra {extra_n} bytes: {extra_bytes!r}"

        raise ParseError(msg)

    return des


def des_to_fields(des: DES, ctx: EmitContext) -> tuple[list[Item], list[Item]]:

    if isinstance(des, UnknownDES):
        header_len = len(des.DESSH) + security_len + 29
        data_len = len(des.DESDATA)
        unknown_spec = make_unknown_spec(header_len, data_len)
        return unknown_spec.emit_segment(des, ctx)

    des_type = type(des)
    if des_type not in des_write_registry:
        name = des_type.__name__
        msg = f"Class {name} does not have a registered specification."
        raise TypeError(msg)

    spec = des_write_registry[des_type]
    return spec.emit_segment(des, ctx)
