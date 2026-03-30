"""CSEPHB DES"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import IntEnum
from uuid import UUID as UUID_T

from nitful.core.common import DES, Security
from nitful.core.eci import ECI

type Array2D = list[list[float]]


@dataclass(kw_only=True)
class CSEPHB(DES):

    security: Security

    # An ID for this DES.
    UUID: UUID_T

    # A list of image segments associated with this DES, identified by display
    # level. If empty, this DES applies to all image segments.
    images: list[int] = field(default_factory=list)

    # A list of associated elements, primarily the IMAGE_UUID from the
    # associated CSEXRB TRE.
    elements: list[UUID_T] = field(default_factory=list)

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

    # Velocity and accleration data.
    kinematics: Kinematics | None = None

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
    INTERP_ORDER_EPH: int


@dataclass
class ECF:
    pass


class EphemerisSource(IntEnum):
    PREDICTED = 0
    ACTUAL = 1
    REFINED = 2


@dataclass
class Kinematics:
    velocities: Array2D
    accelerations: Array2D | None = None
