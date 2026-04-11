from pathlib import Path
from typing import BinaryIO

from ._format.des import disable_des_parsing
from ._format.file import read_file, to_fields
from ._format.tre import disable_tre_parsing
from .core.file import NitfFile
from .dsl.io import dump_fields, write_fields
from .dsl.rules import Int, ParseContext, item_size

__all__ = [
    "NitfFile",
    "dump",
    "load",
    "read",
    "save",
    "strip",
    "write",
]


def read(fd: BinaryIO) -> NitfFile:
    """Reads a NitfFile object from an open binary stream."""
    return read_file(fd, ParseContext())


def load(filepath: str | Path) -> NitfFile:
    """Convenience function to open and read a nitf file from disk."""
    with open(filepath, "rb") as fd:
        return read(fd)


def write(nitf: NitfFile, fd: BinaryIO) -> None:
    """Serialize a NitfFile object and write it to an open binary stream."""
    fields = to_fields(nitf)
    write_fields(fields, fd)


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
        fields = to_fields(source)
    else:
        with open(source, "rb") as fd:
            ctx = ParseContext()
            read_file(fd, ctx)

        fields = [item for (item, _) in ctx.fields]

    return dump_fields(
        fields,
        header=header,
        image_nums=image_nums,
        tre_names=tre_names,
        des_names=des_names,
    )


def strip(fd_in: BinaryIO, fd_out: BinaryIO) -> None:
    """Create a copy of a NITF file that strips image pixels.

    Used to create a file when you only want to share the metadata. Modifies
    the image data and image sizes in the file header, so that the file can be
    parsed correctly.
    """
    fake_pixels = bytes.fromhex("DEADBEEF")
    li = len(fake_pixels)

    # Disable parsing of SDEs: it's not needed to simply copy the bytes, and
    # possibly an impediment: a user might strip a NITF to send _because_ it's
    # not parsing correctly.
    with disable_des_parsing(), disable_tre_parsing():
        ctx = ParseContext()
        read_file(fd_in, ctx)

    fields = [item for (item, _) in ctx.fields]
    field_map = {f.name: f for f in fields}

    data_fields = [f for f in fields if f.name == "IMAGE DATA"]

    for i, data in enumerate(data_fields):
        data.value = fake_pixels
        field_map[f"LI[{i}]"].value = Int("LI", 10).encode(li)

    fl = item_size(fields)
    field_map["FL"].value = Int("FL", 12).encode(fl)

    write_fields(fields, fd_out)
