"""CSEPHB DES"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from uuid import UUID

from biif.models.core import Security
from biif.models.des import DES
from biif.models.eci import ECI

type Array2D = list[list[float]]


@dataclass(kw_only=True)
class CSEPHB(DES):

    security: Security

    # An ID for this DES.
    UUID: UUID

    # A list of image segments associated with this DES, identified by display
    # level. If empty, this DES applies to all image segments.
    associated_images: list[int] = field(default_factory=list)

    # A list of associated elements, primarily the IMAGE_UUID from the
    # associated CSEXRB TRE.
    associated_elements: list[UUID]

    # True if good, false if suspect.
    QUAL_FLAG_EPH: Quality

    # The interpolation to be used with the provided ephemerides.
    interpolation: NearestNeighbor | Linear | Lagrangian

    EPHEM_FLAG: EphemerisSource

    # The reference frame of the provided ephemerides.
    frame: ECF | ECI

    # The time between ephemerides.
    DT_EPHEM: float

    # The date of the first ephemeris vector.
    DATE_EPHEM: date

    # UTC seconds since midnight of the first ephemeris vector.
    T0_EPHEM: float

    ephemerides: Array2D

    velocity: Array2D | None = None
    acceleration: Array2D | None = None


class Quality(Enum):
    SUSPECT = 0
    GOOD = 1


class InterpolationType(Enum):
    NEAREST = 0
    LINEAR = 1
    LAGRANGIAN = 2


@dataclass
class NearestNeighbor:
    pass


@dataclass
class Linear:
    pass


@dataclass
class Lagrangian:
    INTERP_ORDER_EPH: int


class Frame(Enum):
    ECI = 0
    ECF = 1


@dataclass
class ECF:
    pass


class EphemerisSource(Enum):
    PREDICTED = 0
    ACTUAL = 1
    REFINED = 2
