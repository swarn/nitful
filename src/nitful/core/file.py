from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .common import DES, TRE, EncryptionLevel, Security
from .graphic import GraphicSegment
from .image import ImageSegment


@dataclass(kw_only=True)
class NitfFile:

    FHDR: str = "NITF"
    FVER: str = "02.10"
    CLEVEL: int = 9
    STYPE: str = "BF01"
    OSTAID: str = ""
    FDT: datetime = field(default_factory=datetime.now)
    FTITLE: str = ""
    security: Security = field(default_factory=Security)
    FSCOP: int = 0
    FSCPYS: int = 0
    ENCRYP: EncryptionLevel = field(default_factory=lambda: EncryptionLevel.NONE)
    FBKGC: RGB = field(default_factory=lambda: RGB(0, 0, 0))
    ONAME: str = ""
    OPHONE: str = ""

    # User-defined header data.
    UDHD: list[TRE] = field(default_factory=list)

    # If non-zero, the one-based index of the DES containing UDHD overflow.
    UDHOFL: int = 0

    # Extended header data. If I understand STDI-0002 §2.2.1 correctly,
    # controlled extensions (CE), which are "standard" TREs, go here.
    XHD: list[TRE] = field(default_factory=list)

    # If non-zero, the one-based index of the DES containing XHD overflow.
    XHDLOFL: int = 0

    image_segments: list[ImageSegment] = field(default_factory=list)
    graphic_segments: list[GraphicSegment] = field(default_factory=list)
    data_segments: list[DES] = field(default_factory=list)


@dataclass
class RGB:
    r: int
    g: int
    b: int
