from pathlib import Path
from typing import BinaryIO

from ._dsl.io import dump_fields as _dump_fields
from ._dsl.io import write_fields as _write_fields
from ._format.file import read_file as _read_format
from ._format.file import to_fields as _to_fields
from .models.file import BIIF


def read(fd: BinaryIO) -> BIIF:
    """Reads a BIIF object from an open binary stream."""
    return _read_format(fd)


def load(filepath: str | Path) -> BIIF:
    """Convenience function to open and read a BIIF file from disk."""
    with open(filepath, "rb") as fd:
        return _read_format(fd)


def write(biif: BIIF, fd: BinaryIO) -> None:
    """Serialize a BIIF object and write it to an open binary stream."""
    fields = _to_fields(biif)
    _write_fields(fields, fd)


def save(biif: BIIF, filepath: str | Path) -> None:
    """Convenience function to save a BIIF object as a NITF file."""
    with open(filepath, "wb") as fd:
        write(biif, fd)


def dump(biif: BIIF) -> str:
    """Return a human-readable string representing the BIIF."""
    fields = _to_fields(biif)
    return _dump_fields(fields)
