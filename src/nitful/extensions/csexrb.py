from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import IntEnum, StrEnum
from uuid import UUID as UUID_T

from nitful.core.common import TRE


@dataclass(kw_only=True)
class CSEXRB(TRE):

    IMAGE_UUID: UUID_T

    # A list of associated GLAS/GFM DESs
    associated_elements: list[UUID_T] = field(default_factory=list)

    PLATFORM_ID: str = ""
    PAYLOAD_ID: str = ""
    SENSOR_ID: str = ""

    SENSOR_TYPE: SensorType

    GROUND_REF_POINT_X: float | None = None
    GROUND_REF_POINT_Y: float | None = None
    GROUND_REF_POINT_Z: float | None = None

    timing: ScannerTiming | FramerTiming | None

    MAX_GSD: float | None = None
    ALONG_SCAN_GSD: float | None = None
    cross_scan_gsd: float | None = None
    geo_mean_gsd: float | None = None
    A_S_VERT_GSD: float | None = None
    C_S_VERT_GSD: float | None = None
    GEO_MEAN_VERT_GSD: float | None = None
    GSD_BETA_ANGLE: float | None = None
    DYNAMIC_RANGE: float | None = None

    NUM_LINES: int
    NUM_SAMPLES: int

    ANGLE_TO_NORTH: float | None = None
    OBLIQUITY_ANGLE: float | None = None
    AZ_OF_OBLIQUITY: float | None = None
    ATM_REFR_FLAG: bool = False
    VEL_ABER_FLAG: bool = False

    GRD_COVER: GroundCover = field(default_factory=lambda: GroundCover.UNAVAIL)
    SNOW_DEPTH_CATEGORY: SnowDepth = field(default_factory=lambda: SnowDepth.UNAVAIL)
    SUN_AZIMUTH: float | None = None
    SUN_ELEVATION: float | None = None


class SensorType(StrEnum):
    SCANNER = "S"
    FRAMER = "F"
    NONE = " "


@dataclass(kw_only=True)
class ScannerTiming:
    DAY_FIRST_LINE_IMAGE: date
    TIME_FIRST_IMAGE_LINE: float
    TIME_IMAGE_DURATION: float


@dataclass(kw_only=True)
class FramerTiming:
    time: MtimsaTiming | DesFramerTiming


@dataclass(kw_only=True)
class MtimsaTiming:
    """Dummy class indicating framer timing is in MTIMSA TRE"""


@dataclass(kw_only=True)
class DesFramerTiming:
    REFERENCE_FRAME_NUM: int | None

    # CCYYMMDDhhmmss.nnnnnnnnn exceeds Python datetime precision.
    BASE_TIMESTAMP: str

    DT_MULTIPLIER: int
    DT_SIZE: int
    NUMBER_FRAMES: int

    time_deltas: list[int]


class GroundCover(IntEnum):
    SNOW = 1
    NOSNOW = 0
    UNAVAIL = 9


class SnowDepth(IntEnum):
    NONE = 0
    IN_1_TO_8 = 1
    IN_9_TO_17 = 2
    IN_GT_17 = 3
    UNAVAIL = 9
