from typing import BinaryIO, cast

from nitful._dsl.rules import (
    BcsString,
    Constant,
    EmitContext,
    FixedBytes,
    Int,
    Item,
    ParseContext,
    Segment,
)
from nitful._format.security import security_len, security_spec
from nitful.core.common import DES, UnknownDES

des_read_registry: dict[tuple[str, int], Segment[DES]] = {}
des_write_registry: dict[type[DES], Segment[DES]] = {}


def register_des[T: DES](desid: str, desver: int, spec: Segment[T]) -> None:
    """Register a specification for a DES."""
    des_read_registry[desid, desver] = cast(Segment[DES], spec)
    des_write_registry[spec.model_cls] = cast(Segment[DES], spec)


def make_unknown_spec(header_len: int, data_len: int) -> Segment[UnknownDES]:
    return Segment[UnknownDES](
        UnknownDES,
        subheader=[
            Constant(BcsString("DE", 2), "DE"),
            BcsString("DESID", 25),
            Int("DESVER", 2),
            security_spec,
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
        msg = "Unexpected EOF while reading DES header."
        raise RuntimeError(msg)

    fd.seek(start_pos)

    if first[:2].decode() != "DE":
        msg = "Expected DES, but first characters were not 'DE'"
        raise RuntimeError(msg)

    desid = first[2:27].decode().strip()
    desver = int(first[27:29].decode())

    if (desid, desver) in des_read_registry:
        spec = des_read_registry[desid, desver]
        des = spec.parse(fd, ctx)
    else:
        unknown_spec = make_unknown_spec(header_len, data_len)
        des = unknown_spec.parse(fd, ctx)

    end_pos = fd.tell()
    net_bytes = end_pos - start_pos
    if net_bytes != header_len + data_len:
        msg = (
            f"DES byte mismatch for {desid} v{desver}. "
            f"Expected {header_len + data_len}, but consumed {net_bytes}."
        )
        raise RuntimeError(msg)

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
