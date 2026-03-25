from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import BinaryIO, Protocol

from biif.models.common import TRE, EncryptionLevel, Security


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
    location: NoCoords | Coords = field(default_factory=lambda: NoCoords())
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
    ILOCROW: int = 0
    ILOCCOL: int = 0
    IMAG: str = "1.0 "

    UDID: list[TRE] = field(default_factory=list)
    IXSHD: list[TRE] = field(default_factory=list)

    data: ImageData = field(
        default_factory=lambda: BytesData(bytes.fromhex("DEADBEEF"))
    )


class PixelType(Enum):
    INTEGER = "INT"
    BOOLEAN = "B"
    SIGNED = "SI"
    REAL = "R"
    COMPLEX = "C"


class ImageType(Enum):
    NODISPLAY = "NODISPLY"
    MONO = "MONO"
    RGB = "RGB"
    RGBLUT = "RGB/LUT"
    BT601 = "YCbCr601"
    CARTESIAN = "NVECTOR"
    POLAR = "POLAR"
    PHASE = "VPH"
    MULTIBAND = "MULTI"


class PixelJustification(Enum):
    LEFT = "L"
    RIGHT = "R"


@dataclass
class NoCoords:
    pass


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
    COMRAT: str = ""


@dataclass
class BandInfo:
    IREPBAND: str = ""
    ISUBCAT: str = ""
    IFC: str = "N"
    IMFLT: str = ""
    luts: list[list[int]] = field(default_factory=list)


class ImageData(Protocol):
    """Wrapper for deferred or raw pixel data.

    NITF image segments can be massive. This protocol allows skipping loading
    the pixel data, defering it until needed, or streaming it directly to a new
    file during a round-trip operation.

    **Reading Pixel Data**
    To read the raw bytes, call `read()`. The original file descriptor must
    remain open while reading:

    ```python
    with open('file.nitf', 'rb') as fd:
        nitf = biif.read(fd)
        pixels = nitf.image_segments[0].data.read()
    ```

    **Round-Tripping (Modify and Save)**
    If you are modifying header data and writing to a new file, the source
    file descriptor must remain open so the data can be streamed:

    ```python
    with open('source.nitf', 'rb') as source_fd:
        nitf = biif.read(source_fd)
        nitf.FTITLE = "NEW TITLE"

        with open('destination.nitf', 'wb') as dest_fd:
            biif.write(nitf, dest_fd)
    ```

    **Modifying Pixel Data**
    If you want to set pixel data, wrap your raw bytes in the `BytesData`
    class:

    ```python
    pixels = b'1234'
    nitf.image_segments[0].data = BytesData(pixels)
    biif.save(nitf, 'new_file.ntf')
    ```
    """

    def __len__(self) -> int: ...
    def write(self, out_fd: BinaryIO) -> None: ...
    def read(self) -> bytes: ...


@dataclass(frozen=True)
class BytesData:
    """In-memory implemenation of the ImageData protocol."""

    data: bytes

    def __len__(self) -> int:
        return len(self.data)

    def write(self, out_fd: BinaryIO) -> None:
        out_fd.write(self.data)

    def read(self) -> bytes:
        return self.data
