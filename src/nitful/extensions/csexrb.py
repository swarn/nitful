from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
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
    CROSS_SCAN_GSD: float | None = None
    GEO_MEAN_GSD: float | None = None
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

    PREDICTED_NIIRS: float | None = None
    CIRCL_ERR: float | None = None
    LINEAR_ERR: float | None = None
    CLOUD_COVER: int | None = None

    ROLLING_SHUTTER_FLAG: RollingShutter | None = None
    UE_TIME_FLAG: bool | None = None

    rfa1: TargetAndCollectionData | None = None

    # Unknown Reserved Field Areas are placed here during parsing
    unknown_extensions: dict[int, bytes] = field(default_factory=dict)


class SensorType(StrEnum):
    SCANNER = "S"
    FRAMER = "F"
    NONE = " "


@dataclass(kw_only=True)
class ScannerTiming:
    DAY_FIRST_LINE_IMAGE: date
    TIME_FIRST_LINE_IMAGE: float
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


class RollingShutter(IntEnum):
    SAME = 0
    CHANGING = 1


class QualityType(StrEnum):
    PREDICTED = "P"
    TASKED = "T"
    MEASURED = "M"


@dataclass(kw_only=True)
class CollectionCriteria:
    COLLECT_CRITERIA_NAME: str
    COLLECT_CRITERIA_UNIT: str | None = None
    COLLECT_CRITERIA_VALUE: str


@dataclass(kw_only=True)
class QualityMetric:
    QUALITY_METRIC_NAME: str
    QUALITY_METRIC_UNIT: str | None = None
    QUALITY_METRIC_TYPE: QualityType
    QUALITY_METRIC_VALUE: str


@dataclass(kw_only=True)
class ImagingOperation:
    CM_ID: str = ""
    SENSOR_CONFIG: str = ""
    IMG_OP_ID: str = ""
    indices: list[int] = field(default_factory=list)
    quality_metrics: list[QualityMetric] = field(default_factory=list)


@dataclass(kw_only=True)
class TargetAndCollectionData:
    """Data representing CSEXRB Reserved Field Area 1."""

    NUM_IMG_OPS: int

    # Target Data
    TGT_ID: str | None = None
    TGT_NAME: str | None = None
    TGT_TYPE: str | None = None
    TGT_LAT: float | None = None
    TGT_LON: float | None = None
    TGT_HT: float | None = None
    TGT_DATE_TIME: datetime | None = None
    TGT_AZ: float | None = None
    TGT_ELEV_ANG: float | None = None
    TGT_BIDEC_ANG: float | None = None

    # Collection Data
    COLL_REQ_ID: str | None = None
    COLLECT_STRAT: str | None = None
    COLLECT_TYPE: str | None = None
    COLL_CODE: str | None = None

    collection_criteria: list[CollectionCriteria] = field(default_factory=list)
    imaging_operations: list[ImagingOperation] = field(default_factory=list)
