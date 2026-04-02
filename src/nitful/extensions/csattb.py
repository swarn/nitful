"""CSATTB DES"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import IntEnum
from uuid import UUID as UUID_T

from nitful.core.common import DES
from nitful.core.eci import ECI, ECIv1

type Array2D = list[list[float]]


class AttitudeType(IntEnum):
    PREDICTED = 0
    ACTUAL = 1
    REFINED = 2


@dataclass(kw_only=True)
class CSATTB(DES):

    DESID: str = "CSATTB"
    DESVER: int = 2

    # An ID for this DES.
    UUID: UUID_T

    # A list of image segments associated with this DES.
    # If empty, this DES applies to all image segments.
    images: list[int] = field(default_factory=list)

    # A list of associated elements.
    elements: list[UUID_T] = field(default_factory=list)

    # SUSPECT quality disables error propagation.
    QUAL_FLAG_ATT: Quality

    # The interpolation to be used.
    interpolation: NearestNeighbor | Linear | Lagrangian | Spherical

    ATT_TYPE: AttitudeType

    # The reference frame. ECI should only be used with DESVER=2, ECIv1 should
    # only be used with DESVER=1.
    frame: ECF | ECI | ECIv1

    # The time between quaternions.
    DT_ATT: float

    # The date of the first quaternion.
    DATE_ATT: date

    # UTC seconds since midnight of the first quaternion.
    T0_ATT: float

    # NOTE: these are JPL-convention quaternions!
    quaternions: Array2D

    # Unknown Reserved Field Areas are placed here during parsing as raw bytes,
    # allowing them to be written later.
    unknown_extensions: dict[int, bytes] = field(default_factory=dict)


class Quality(IntEnum):
    SUSPECT = 0
    GOOD = 1


@dataclass
class NearestNeighbor:
    pass


@dataclass
class Linear:
    pass


@dataclass
class Lagrangian:
    INTERP_ORDER_ATT: int


@dataclass
class Spherical:
    INTERP_ORDER_ATT: int


@dataclass
class ECF:
    pass
