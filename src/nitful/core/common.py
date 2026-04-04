from dataclasses import dataclass
from decimal import Decimal
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


@dataclass
class ECI:
    """ECI definition used in CSEPHB and CSATTB."""

    TA_POLE: Decimal
    A_POLE: float
    B_POLE: float
    CJ1_POLE: float
    CJ2_POLE: float
    DJ1_POLE: float
    DJ2_POLE: float
    PJ1_POLE: float
    PJ2_POLE: float
    E_POLE: float
    F_POLE: float
    GK1_POLE: float
    GK2_POLE: float
    HK1_POLE: float
    HK2_POLE: float
    PK1_POLE: float
    PK2_POLE: float
    TB_UT: Decimal
    I_UT: float
    J_UT: float
    KN1_UT: float
    KN2_UT: float
    KN3_UT: float
    KN4_UT: float
    LN1_UT: float
    LN2_UT: float
    LN3_UT: float
    LN4_UT: float
    PN1_UT: float
    PN2_UT: float
    PN3_UT: float
    PN4_UT: float


@dataclass
class ECIv1:
    """Version 1 of CSEPHB and CSATTB defined ECI without parameters."""
