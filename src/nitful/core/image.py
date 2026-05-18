from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import BinaryIO

from nitful.core.common import PixelCoord

from .common import TRE, EncryptionLevel, Security


@dataclass(kw_only=True)
class ImageSegment:
    IID1: str = ""

    # This a date and time formatted CCYYMMDDhhmmss. However, the spec allows
    # any/all of the characters to be replaced with "-" characters.
    IDATIM: str = "--------------"

    TGTID: str = ""
    IID2: str = ""
    security: Security = field(default_factory=Security)
    ENCRYP: EncryptionLevel = EncryptionLevel.NONE
    ISORCE: str = ""
    NROWS: int = 0
    NCOLS: int = 0
    PVTYPE: PixelType = field(default_factory=lambda: PixelType.INTEGER)
    IREP: ImageType = field(default_factory=lambda: ImageType.MONO)
    ICAT: str = "VIS"
    ABPP: int = 8
    PJUST: PixelJustification = field(default_factory=lambda: PixelJustification.RIGHT)
    location: Coords | None = None
    comments: list[str] = field(default_factory=list)
    compression: Compression = field(default_factory=lambda: Compression())
    bands: list[BandInfo] = field(default_factory=list)
    ISYNC: int = 0
    IMODE: str = "B"
    NBPR: int = 1
    NBPC: int = 1
    NPPBH: int = 0
    NPPBV: int = 0
    NBPP: int = 8
    IDLVL: int = 1
    IALVL: int = 0
    ILOC: PixelCoord = field(default_factory=lambda: PixelCoord(0, 0))
    IMAG: str = "1.0 "

    UDID: list[TRE] = field(default_factory=list)

    # If non-zero, the one-based index of the DES containing UDID overflow.
    UDOFL: int = 0

    IXSHD: list[TRE] = field(default_factory=list)

    # If non-zero, the one-based index of the DES containing IXSHD overflow.
    IXSOFL: int = 0

    data: DeferredImageData | bytes = field(
        default_factory=lambda: bytes.fromhex("DEADBEEF")
    )


class PixelType(StrEnum):
    INTEGER = "INT"
    BOOLEAN = "B"
    SIGNED = "SI"
    REAL = "R"
    COMPLEX = "C"


class ImageType(StrEnum):
    NODISPLAY = "NODISPLY"
    MONO = "MONO"
    RGB = "RGB"
    RGBLUT = "RGB/LUT"
    BT601 = "YCbCr601"
    CARTESIAN = "NVECTOR"
    POLAR = "POLAR"
    PHASE = "VPH"
    MULTIBAND = "MULTI"


class PixelJustification(StrEnum):
    LEFT = "L"
    RIGHT = "R"


@dataclass
class Coords:
    """Corner coordinates for an image (IGEOLO).

    IGEOLO is an entire specification itself, including rules for representing
    significant digits with formatting.
    """

    ICORDS: str
    upperleft: str
    upperright: str
    lowerright: str
    lowerleft: str


@dataclass
class Compression:
    IC: str = "NC"
    COMRAT: str | None = None


@dataclass
class BandInfo:
    IREPBAND: str = ""
    ISUBCAT: str = ""
    IFC: str = "N"
    IMFLT: str = ""
    luts: list[list[int]] = field(default_factory=list)


@dataclass(frozen=True)
class DeferredImageData:
    """A reference to pixel data in a file.

    NITF image segments can be massive. Rather than storing pixel data, nitful
    saves files and offsets within the files which can be read later.
    """

    path: Path | str | None = field(compare=False)
    offset: int
    length: int

    def __len__(self) -> int:
        return self.length

    def write(self, out_fd: BinaryIO) -> None:
        if not self.path:
            msg = "Cannot write deferred payload: original stream was not a named file."
            raise RuntimeError(msg)

        with open(self.path, "rb") as source_fd:
            source_fd.seek(self.offset)
            bytes_left = self.length

            while bytes_left > 0:
                chunk = source_fd.read(min(bytes_left, 4096 * 1024))
                if not chunk:
                    break
                out_fd.write(chunk)
                bytes_left -= len(chunk)

    def read(self) -> bytes:
        if not self.path:
            msg = "Cannot read deferred payload: original stream was not a named file."
            raise RuntimeError(msg)

        with open(self.path, "rb") as source_fd:
            source_fd.seek(self.offset)
            return source_fd.read(self.length)
