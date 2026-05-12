from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .common import TRE, EncryptionLevel, PixelCoord, Security


@dataclass(kw_only=True)
class GraphicSegment:
    SY: str
    SID: str
    SNAME: str
    security: Security = field(default_factory=Security)
    ENCRYP: EncryptionLevel = EncryptionLevel.NONE
    SFMT: GraphicFormat = field(default_factory=lambda: GraphicFormat.CGM)
    SSTRUCT = 0
    SDLVL: int
    SALVL: int
    SLOC: PixelCoord
    SBND1: PixelCoord
    SCOLOR: GraphicColor
    SBND2: PixelCoord
    SRES2: int = 0

    SXSOFL: int = 0
    SXSHD: list[TRE] = field(default_factory=list)

    # The actual graphic is in CGM, a largely outdated vector graphic format.
    raw_data: bytes


class GraphicFormat(StrEnum):
    CGM = "C"


class GraphicColor(StrEnum):
    COLOR = "C"
    MONO = "M"
