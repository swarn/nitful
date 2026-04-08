from pathlib import Path
from typing import BinaryIO

from ._format.file import read_file as _read_file
from ._format.file import to_fields as _to_fields
from .core.file import NitfFile
from .dsl.io import dump_fields as _dump_fields
from .dsl.io import write_fields as _write_fields
from .dsl.rules import ParseContext as _ParseContext


def read(fd: BinaryIO) -> NitfFile:
    """Reads a NitfFile object from an open binary stream."""
    return _read_file(fd, _ParseContext())


def load(filepath: str | Path) -> NitfFile:
    """Convenience function to open and read a nitf file from disk."""
    with open(filepath, "rb") as fd:
        return read(fd)


def write(nitf: NitfFile, fd: BinaryIO) -> None:
    """Serialize a NitfFile object and write it to an open binary stream."""
    fields = _to_fields(nitf)
    _write_fields(fields, fd)


def save(nitf: NitfFile, filepath: str | Path) -> None:
    """Convenience function to save a NitfFile object as a NITF file."""
    with open(filepath, "wb") as fd:
        write(nitf, fd)


def dump(
    source: str | Path | NitfFile,
    *,
    header: bool = False,
    image_nums: list[int] | None = None,
    tre_names: list[str] | None = None,
    des_names: list[str] | None = None,
) -> str:
    """Convert a NITF file or model into a human-readable string.

    If no filter arguments are provided, the entire file structure is dumped.
    If any filters are specified, the output is restricted strictly to the
    requested components. Filters are combined inclusively; a section or
    extension is printed if it matches any of the active filter criteria.

    Parameters
    ----------
    source : str, Path, or NitfFile
        If a str or Path, return fields read during parsing. If an NitfFile,
        return the fields that would be written during serialization.
    header : bool, optional
        Include the main file header in the output. Default is False.
    image_nums : list of int, optional
        A list of 1-based image segment indices to include.
    tre_names : list of str, optional
        A list of Tagged Record Extension (TRE) names to include (e.g., 'RPC00B').
    des_names : list of str, optional
        A list of Data Extension Segment (DES) names to include (e.g., 'CSEPHB').

    Returns
    -------
    str
        The formatted text representation of the parsed NITF fields.
    """
    if isinstance(source, NitfFile):
        fields = _to_fields(source)
    else:
        with open(source, "rb") as fd:
            ctx = _ParseContext()
            _read_file(fd, ctx)

        fields = [item for (item, _) in ctx.fields]

    return _dump_fields(
        fields,
        header=header,
        image_nums=image_nums,
        tre_names=tre_names,
        des_names=des_names,
    )
