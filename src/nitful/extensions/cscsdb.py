from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import IntEnum
from uuid import UUID as UUID_T

from nitful.core.common import DES

# The spec advises that alternative forms of direct covariance may be added in
# the future.
type DirectCovariance = DirectCovariance0

type TsCalibration = TsGroup1 | TsGroup2 | TsGroup3 | TsGroup4 | TsGroup5


@dataclass(kw_only=True)
class CSCSDB(DES):

    # An ID for this DES.
    UUID: UUID_T

    # A list of image segments associated with this DES, identified by display
    # level. If empty, this DES applies to all image segments.
    images: list[int] = field(default_factory=list)

    # A list of associated elements, primarily the IMAGE_UUID from the
    # associated CSEXRB TRE.
    elements: list[UUID_T] = field(default_factory=list)

    COV_VERSION_DATE: date

    core_sets: list[CoreSet] = field(default_factory=list)

    io_calibration: IoCalibration | None = None
    ts_calibration: TsCalibration | None = None
    unmodeled: UnmodeledError | None = None
    spdcfs: list[Spdcf] | None = None
    direct_covar: DirectCovariance | None = None

    adj_param_spdcfs: list[int] | None = None

    # Unknown Reserved Field Areas are placed here during parsing as raw bytes,
    # allowing them to be written later.
    unknown_extensions: dict[int, bytes] = field(default_factory=dict)


@dataclass(kw_only=True)
class CoreSet:
    REF_FRAME_POSITION: ReferenceFrame
    REF_FRAME_ATTITUDE: ReferenceFrame
    groups: list[CPGroup]


@dataclass(kw_only=True)
class CPGroup:
    CORR_REF_DATE: date
    CORR_REF_TIME: float
    parameters: list[ParameterId]
    basic: BasicSub | None
    post: PostSub | None


@dataclass(kw_only=True)
class BasicSub:
    covar: list[float]
    platform_spdcfs: list[BasicPlatformSpdcf]
    payload_spdcfs: list[BasicPayloadSpdcf]
    sensor_spdcf: int | None


@dataclass(kw_only=True)
class PostSub:
    POST_START_DATE: date
    POST_START_TIME: float
    POST_DT: float
    NUM_POSTS: int

    # If len(covar) == 1, this covariance matrix is shared among all posts.
    # Otherwise, len(covar) should be NUM_POSTS.
    covar: list[list[float]]

    POST_INTERP: InterpType
    platform_spdcfs: list[PostPlatformSpdcf]
    payload_spdcfs: list[PostPayloadSpdcf]
    sensor_spdcf: PostSensorSpdcf | None


class InterpType(IntEnum):
    NEAREST = 0
    LINEAR = 1


@dataclass(kw_only=True)
class BasicPlatformSpdcf:
    BASIC_PF_SPDCF: int
    pairings: list[str]


@dataclass(kw_only=True)
class BasicPayloadSpdcf:
    BASIC_PL_SPDCF: int
    pairings: list[str]


@dataclass(kw_only=True)
class PostPlatformSpdcf:
    POST_PF_SPDCF: int
    pairings: list[str]


@dataclass(kw_only=True)
class PostPayloadSpdcf:
    POST_PL_SPDCF: int
    pairings: list[str]


@dataclass(kw_only=True)
class PostSensorSpdcf:
    POST_SR_SPDCF: int
    POST_CORR: bool


class ReferenceFrame(IntEnum):
    ECF = 1
    SENSOR = 2
    ICR = 3
    TCEF = 4
    ECI = 5
    SCEF = 6


class ParameterId(IntEnum):
    X = 1
    Y = 2
    Z = 3
    W = 4
    P = 5
    K = 6
    F = 7


@dataclass(kw_only=True)
class IoCalibration:
    focal_lengths: list[float]
    groups: list[IoCpg]


@dataclass(kw_only=True)
class IoCpg:
    CORR_REF_DATE_IO: date
    CORR_REF_TIME_IO: float
    parameters: list[CalApId]

    # One upper-triangular covariance matrix per focal length set
    covariances: list[list[float]]

    CAL_INTERP: InterpType
    SPDCF_ID_TIME: int
    SPDCF_ID_FL: int


class CalApId(IntEnum):
    XO = 1
    YO = 2
    KO = 3
    K1 = 4
    K2 = 5
    K3 = 6
    P1 = 7
    P2 = 8
    P3 = 9
    A1 = 10
    A2 = 11


@dataclass(kw_only=True)
class TsGroup1:
    """One group of both position and attitude delta time parameters."""

    CORR_REF_DATE_TS: date
    CORR_REF_TIME_TS: float
    TSRR: float
    TSRC: float
    TSCC: float
    TS_SPDCF: int


@dataclass(kw_only=True)
class TsGroup2:
    """Two groups, one for each position and attitude."""

    CORR_REF_DATE_TSP: date
    CORR_REF_TIME_TSP: float
    TS_POS_COV: float
    TS_POS_SPDCF: int
    CORR_REF_DATE_TSA: date
    CORR_REF_TIME_TSA: float
    TS_ATT_COV: float
    TS_ATT_SPDCF: int


@dataclass(kw_only=True)
class TsGroup3:
    """One group of position, attitude, and focal length delta time parameters."""

    CORR_REF_DATE_TS: date
    CORR_REF_TIME_TS: float
    TS_POS_COV: float
    TS_POS_ATT_COV: float
    TS_POS_FL_COV: float
    TS_ATT_COV: float
    TS_ATT_FL_COV: float
    TS_FL_COV: float
    TS_SPDCF: int


@dataclass(kw_only=True)
class TsGroup4:
    """Two groups: one containing position and attitude; one containing focal length."""

    CORR_REF_DATE_TSPA: date
    CORR_REF_TIME_TSPA: float
    TS_POS_COV: float
    TS_POS_ATT_COV: float
    TS_ATT_COV: float
    TS_PA_SPDCF: int
    CORR_REF_DATE_TSFL: date
    CORR_REF_TIME_TSFL: float
    TS_FL_COV: float
    TS_FL_SPDCF: int


@dataclass(kw_only=True)
class TsGroup5:
    """Three groups: one for position, one for attitude, and one for focal length."""

    CORR_REF_DATE_TSP: date
    CORR_REF_TIME_TSP: float
    TS_POS_COV: float
    TS_POS_SPDCF: int
    CORR_REF_DATE_TSA: date
    CORR_REF_TIME_TSA: float
    TS_ATT_COV: float
    TS_ATT_SPDCF: int
    CORR_REF_DATE_TSFL: date
    CORR_REF_TIME_TSFL: float
    TS_FL_COV: float
    TS_FL_SPDCF: int


@dataclass(kw_only=True)
class UnmodeledError:
    covariances: list[list[list[float]]]
    LINE_SPDCF: int
    SAMPLE_SPDCF: int


@dataclass(kw_only=True)
class Spdcf:
    SPDCF_ID: int
    constituents: list[ConstituentSpdcf]


@dataclass(kw_only=True)
class ConstituentSpdcf:
    SPDCF_WEIGHT: float
    details: CsmFourParam | PiecewiseLinear | DampedCosine


@dataclass(kw_only=True)
class CsmFourParam:
    FP_A: float
    FP_ALPHA: float
    FP_BETA: float
    FP_T: float


@dataclass(kw_only=True)
class PlSegment:
    PL_MAX_COR: float
    PL_TAU_MAX_COR: float


@dataclass(kw_only=True)
class PiecewiseLinear:
    segments: list[PlSegment]


@dataclass(kw_only=True)
class DampedCosine:
    DC_A: float
    DC_T: float
    DC_P: float


@dataclass(kw_only=True)
class DirectCovariance0:
    """A posteriori adjustments and covariance matrix (DC_TYPE = 0)."""

    adjustments: list[float]
    covariances: list[float]
