from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from biif.models.des import DES
    from biif.models.image import ImageSegment
    from biif.models.tre import TRE


@dataclass(kw_only=True)
class BIIF:

    FHDR: str = "NITF"
    FVER: str = "02.10"
    CLEVEL: int = 9
    STYPE: str = "BF01"
    OSTAID: str = ""
    FDT: datetime = field(default_factory=datetime.now)
    FTITLE: str = ""
    security: Security = field(default_factory=lambda: Security())
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


class SecurityClass(Enum):
    UNCLASSIFIED = "U"
    RESTRICTED = "R"
    CONFIDENTIAL = "C"
    SECRET = "S"
    TOPSECRET = "T"


@dataclass
class Security:
    SCLAS: SecurityClass = SecurityClass.UNCLASSIFIED
    SCLSY: str = ""
    SCODE: str = ""
    SCTLH: str = ""
    SREL: str = ""
    SDCTP: str = ""
    SDCDT: str = ""
    SDCXM: str = ""
    SDG: str = ""
    SDGDT: str = ""
    SCLTX: str = ""
    SCATP: str = ""
    SCAUT: str = ""
    SCRSN: str = ""
    SSRDT: str = ""
    SCTLN: str = ""


class EncryptionLevel(Enum):
    """Single-option enum for forward compatability."""

    NONE = 0
