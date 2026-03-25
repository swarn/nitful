from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from biif.models.common import DES, TRE, EncryptionLevel, Security
from biif.models.image import ImageSegment


@dataclass(kw_only=True)
class BIIF:

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
    FBKGC: tuple[int, int, int] = (0, 0, 0)
    ONAME: str = ""
    OPHONE: str = ""

    # User-defined header data.
    UDHD: list[TRE] = field(default_factory=list)

    # Extended header data. If I understand STDI-0002 §2.2.1 correctly,
    # controlled extensions (CE), which are "standard" TREs, go here.
    XHD: list[TRE] = field(default_factory=list)

    image_segments: list[ImageSegment] = field(default_factory=list)
    data_segments: list[DES] = field(default_factory=list)
