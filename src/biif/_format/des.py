from io import SEEK_CUR
from typing import BinaryIO

from biif._dsl.spec import DataclassRecord, Field
from biif.models.des import DES, UnknownDES

des_read_registry: dict[tuple[str, int], DataclassRecord] = {}
des_write_registry: dict[type[DES], DataclassRecord] = {}


def register_des(desid: str, desver: int, spec: DataclassRecord):
    """Register a specification for a DES."""
    des_read_registry[desid, desver] = spec
    des_write_registry[spec.model_cls] = spec


def read_des(fd: BinaryIO, header_len: int, data_len: int) -> DES:

    start_pos = fd.tell()

    first = fd.read(29)
    if len(first) != 29:
        raise RuntimeError("Unexpected EOF while reading DES header.")

    fd.seek(-29, SEEK_CUR)

    if first[:2].decode() != "DE":
        raise RuntimeError("Invalid DES segment")

    desid = first[2:27].decode().strip()
    desver = int(first[27:29].decode())

    if (desid, desver) in des_read_registry:
        spec = des_read_registry[desid, desver]
        des = spec.read(fd)
    else:
        des = UnknownDES(
            desid=desid,
            desver=desver,
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
            Field(name=f"DES START {des.desid}", value=b""),
            Field(name=f"DES {des.desid} HEADER", value=des.raw_header),
            Field(name="DES DATA START", value=b""),
            Field(name=f"DES {des.desid} DATA", value=des.raw_data),
        ]

    des_type = type(des)
    if des_type not in des_write_registry:
        raise TypeError(
            f"Cannot serialize {des_type.__name__}: "
            "Class is not registered in des_write_registry."
        )

    spec = des_write_registry[des_type]
    return spec.to_fields(des)
