from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from .common import TRE, EncryptionLevel, Security


@dataclass(kw_only=True)
class TextSegment:
    TEXTID: str
    TXTALVL: int
    TXTDT: datetime
    TXTITL: str
    security: Security = field(default_factory=Security)
    ENCRYP: EncryptionLevel = EncryptionLevel.NONE
    TXTFMT: TextFormat = field(default_factory=lambda: TextFormat.U8S)

    TXSOFL: int = 0
    TXSHD: list[TRE] = field(default_factory=list)

    # The encoding of the text is described by `TXTFMT`.
    raw_data: bytes


class TextFormat(StrEnum):
    """Encoding for the text data in `raw_data`.

    Note that the standard mandates CRLF line endings.

    1. BCS (STA): Standard
        - Unformatted text
        - Python encoding: `ascii`
    2. USMTF (MTF): Message Text Formatting
        - Text formatted according to MIL-STD-6040
        - Python encoding: `ascii`
    3. ECS (UT1):
        - Unformatted text
        - Python encoding: `latin1`
    4. U8S: Unicode
        - Unformatted text
        - Python encoding: `utf-8`
    """

    BCS = "STA"
    USMTF = "MTF"
    ECS = "UT1"
    U8S = "U8S"
