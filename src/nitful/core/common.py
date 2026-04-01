from dataclasses import dataclass
from enum import IntEnum, StrEnum


class EncryptionLevel(IntEnum):
    """Single-option enum for forward compatability."""

    NONE = 0


class SecurityClass(StrEnum):
    UNCLASSIFIED = "U"
    RESTRICTED = "R"
    CONFIDENTIAL = "C"
    SECRET = "S"  # noqa: S105
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


@dataclass
class TRE:
    """Base class for all Tagged Record Extensions."""

    CETAG: str


@dataclass(kw_only=True)
class UnknownTRE(TRE):
    """Fallback class for unrecognized TREs."""

    raw_data: bytes


@dataclass(kw_only=True)
class DES:
    """Base class for all Data Extensions Segments."""

    DESID: str
    DESVER: int

    security: Security


@dataclass(kw_only=True)
class UnknownDES(DES):
    """Fallback class for unrecognized DES types."""

    DESSH: bytes
    DESDATA: bytes
