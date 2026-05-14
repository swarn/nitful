from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from nitful.core.common import DES, TRE


@dataclass(kw_only=True)
class TreOverflow(DES):
    """A DES holding TREs too large to fit in their header."""

    DESID: str = "TRE_OVERFLOW"
    DESVER: int = 1

    DESOFLW: OverflowSource
    DESITEM: int

    DESDATA: list[TRE] = field(default_factory=list)


class OverflowSource(StrEnum):
    USER_DEFINED_HEADER = "UDHD"
    EXTENDED_HEADER = "XHD"

    USER_DEFINED_IMAGE = "UDID"
    EXTENDED_IMAGE = "IXSHD"

    EXTENDED_GRAPHIC = "SXSHD"
    EXTENDED_TEXT = "TXSHD"
