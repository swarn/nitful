from os import SEEK_CUR
from typing import BinaryIO

from biif._dsl.spec import BcsString, DataclassRecord, Field, Int
from biif.models.tre import TRE, UnknownTRE

tre_read_registry: dict[str, DataclassRecord] = {}
tre_write_registry: dict[type[TRE], DataclassRecord] = {}


def register_tre(tag: str, spec: DataclassRecord):
    tre_read_registry[tag] = spec
    tre_write_registry[spec.model_cls] = spec


def read_tre(fd: BinaryIO) -> TRE:
    start_pos = fd.tell()

    header = fd.read(11)
    if len(header) != 11:
        raise RuntimeError("Unexpected EOF while reading TRE header.")

    tag = header[:6].decode().strip()
    try:
        length = int(header[6:].decode())
    except ValueError:
        raise RuntimeError(f"Invalid TRE length field in tag '{tag}': {header[6:]}")

    fd.seek(-11, SEEK_CUR)

    if tag in tre_read_registry:
        spec = tre_read_registry[tag]
        parsed_tre = spec.read(fd)
    else:
        fd.seek(11, SEEK_CUR)
        parsed_tre = UnknownTRE(tag=tag, raw_data=fd.read(length))

    expected_end = start_pos + 11 + length
    actual_end = fd.tell()

    if actual_end != expected_end:
        drift = actual_end - expected_end
        fd.seek(expected_end)
        raise RuntimeError(
            f"TRE Spec for '{tag}' drifted by {drift} bytes! "
            f"Expected length {length}, but spec consumed {actual_end - start_pos - 11}."
        )

    return parsed_tre


def tre_to_fields(tre: TRE) -> list[Field]:
    """Serializes a TRE, dynamically computing its 5-byte length."""

    if isinstance(tre, UnknownTRE):
        tag_field = BcsString("CETAG", 6).to_fields(tre.tag)[0]
        len_field = Int("CEL", 5).to_fields(len(tre.raw_data))[0]
        data_field = Field(name="CEDATA", value=tre.raw_data)
        return [tag_field, len_field, data_field]

    tre_type = type(tre)
    if tre_type not in tre_write_registry:
        raise TypeError(f"Unregistered TRE class: {tre_type.__name__}")

    spec = tre_write_registry[tre_type]
    return spec.to_fields(tre)
