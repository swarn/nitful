"""ECI definition used in CS* SDEs"""

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class ECI:
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
