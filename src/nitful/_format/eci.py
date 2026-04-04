"""ECI definition used in CS* SDEs.

The TA_POLE and TB_UT values _must_ use the Decimal module: they have more
significant digits than can be represented with a double-precision float.
"""

from decimal import Decimal
from typing import Any

from nitful._dsl.rules import Fixed, FixedDecimal, Rule
from nitful._dsl.validator import in_range

eci_spec: list[Rule[Any]] = [
    FixedDecimal("TA_POLE", 19, in_range(Decimal("2e6"), Decimal("3e6")), ndigits=11),
    Fixed("A_POLE", 11, in_range(-1.0, 1.0), sign=True, ndigits=8),
    Fixed("B_POLE", 11, in_range(-1.0, 1.0), sign=True, ndigits=8),
    Fixed("CJ1_POLE", 11, in_range(-1.0, 1.0), sign=True, ndigits=8),
    Fixed("CJ2_POLE", 11, in_range(-1.0, 1.0), sign=True, ndigits=8),
    Fixed("DJ1_POLE", 11, in_range(-1.0, 1.0), sign=True, ndigits=8),
    Fixed("DJ2_POLE", 11, in_range(-1.0, 1.0), sign=True, ndigits=8),
    Fixed("PJ1_POLE", 10, in_range(0.0, 500.0), ndigits=6),
    Fixed("PJ2_POLE", 10, in_range(0.0, 500.0), ndigits=6),
    Fixed("E_POLE", 11, in_range(-1.0, 1.0), sign=True, ndigits=8),
    Fixed("F_POLE", 11, in_range(-1.0, 1.0), sign=True, ndigits=8),
    Fixed("GK1_POLE", 11, in_range(-1.0, 1.0), sign=True, ndigits=8),
    Fixed("GK2_POLE", 11, in_range(-1.0, 1.0), sign=True, ndigits=8),
    Fixed("HK1_POLE", 11, in_range(-1.0, 1.0), sign=True, ndigits=8),
    Fixed("HK2_POLE", 11, in_range(-1.0, 1.0), sign=True, ndigits=8),
    Fixed("PK1_POLE", 10, in_range(0.0, 500.0), sign=True, ndigits=8),
    Fixed("PK2_POLE", 10, in_range(0.0, 500.0), sign=True, ndigits=8),
    FixedDecimal("TB_UT", 19, in_range(Decimal("2e6"), Decimal("3e6")), ndigits=11),
    Fixed("I_UT", 12, in_range(-1.0, 1.0), sign=True, ndigits=9),
    Fixed("J_UT", 12, in_range(-1.0, 1.0), sign=True, ndigits=9),
    Fixed("KN1_UT", 12, in_range(-1.0, 1.0), sign=True, ndigits=9),
    Fixed("KN2_UT", 12, in_range(-1.0, 1.0), sign=True, ndigits=9),
    Fixed("KN3_UT", 12, in_range(-1.0, 1.0), sign=True, ndigits=9),
    Fixed("KN4_UT", 12, in_range(-1.0, 1.0), sign=True, ndigits=9),
    Fixed("LN1_UT", 12, in_range(-1.0, 1.0), sign=True, ndigits=9),
    Fixed("LN2_UT", 12, in_range(-1.0, 1.0), sign=True, ndigits=9),
    Fixed("LN3_UT", 12, in_range(-1.0, 1.0), sign=True, ndigits=9),
    Fixed("LN4_UT", 12, in_range(-1.0, 1.0), sign=True, ndigits=9),
    Fixed("PN1_UT", 10, in_range(0.0, 500.0), sign=True, ndigits=6),
    Fixed("PN2_UT", 10, in_range(0.0, 500.0), sign=True, ndigits=6),
    Fixed("PN3_UT", 10, in_range(0.0, 500.0), sign=True, ndigits=6),
    Fixed("PN4_UT", 10, in_range(0.0, 500.0), sign=True, ndigits=6),
]
