from io import SEEK_CUR
from typing import BinaryIO, cast

from biif._dsl.spec import DataclassRecord, Field
from biif.models.common import DES, UnknownDES

des_read_registry: dict[tuple[str, int], DataclassRecord[DES]] = {}
des_write_registry: dict[type[DES], DataclassRecord[DES]] = {}


def register_des[T: DES](desid: str, desver: int, spec: DataclassRecord[T]) -> None:
    """Register a specification for a DES."""
    des_read_registry[desid, desver] = cast(DataclassRecord[DES], spec)
    des_write_registry[spec.model_cls] = cast(DataclassRecord[DES], spec)


def read_des(fd: BinaryIO, header_len: int, data_len: int) -> DES:

    start_pos = fd.tell()

    # Length of "DE", "DESID", and "DESVER" fields.
    peek_len = 29

    first = fd.read(peek_len)
    if len(first) != peek_len:
        msg = "Unexpected EOF while reading DES header."
        raise RuntimeError(msg)

    fd.seek(-peek_len, SEEK_CUR)

    if first[:2].decode() != "DE":
        msg = "Expected DES, but first characters were not 'DE'"
        raise RuntimeError(msg)

    desid = first[2:27].decode().strip()
    desver = int(first[27:29].decode())

    if (desid, desver) in des_read_registry:
        spec = des_read_registry[desid, desver]
        des = spec.read(fd)
    else:
        des = UnknownDES(
            DESID=desid,
            DESVER=desver,
            raw_header=fd.read(header_len),
            raw_data=fd.read(data_len),
        )

    end_pos = fd.tell()
    net_bytes = end_pos - start_pos
    if net_bytes != header_len + data_len:
        msg = (
            f"DES byte mismatch for {desid} v{desver}. "
            f"Expected {header_len + data_len}, but consumed {net_bytes}."
        )
        raise RuntimeError(msg)

    return des


def des_to_fields(des: DES) -> list[Field]:

    # Without a spec, we can still round-trip correctly by inserting markers
    # for the header DES sizes.
    if isinstance(des, UnknownDES):
        return [
            Field(name=f"DES START {des.DESID}", value=b""),
            Field(name=f"DES {des.DESID} HEADER", value=des.raw_header),
            Field(name="DES DATA START", value=b""),
            Field(name=f"DES {des.DESID} DATA", value=des.raw_data),
        ]

    des_type = type(des)
    if des_type not in des_write_registry:
        name = des_type.__name__
        msg = f"Class {name} does not have a registered specification."
        raise TypeError(msg)

    spec = des_write_registry[des_type]
    return spec.to_fields(des)
