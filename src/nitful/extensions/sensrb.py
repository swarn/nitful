from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any, Literal

from nitful.core.common import TRE


@dataclass(kw_only=True)
class SENSRB(TRE):
    """SENSRB Tagged Record Extension"""

    general_data: GeneralData | None = None
    sensor_array: SensorArrayData | None = None
    calibration: CalibrationData | None = None
    image_formation: ImageFormationData | None = None
    reference: ReferenceData
    position: PositionData
    euler_angles: EulerAngles | None = None
    unit_vectors: UnitVectors | None = None
    quaternion: Quaternion | None = None
    velocity: SensorVelocity | None = None

    point_sets: list[PointSet] = field(default_factory=list)
    time_stamped_data: list[TimeStampedDataSet] = field(default_factory=list)
    pixel_referenced_data: list[PixelReferencedDataSet] = field(default_factory=list)
    uncertainty_data: list[Uncertainty] = field(default_factory=list)
    additional_parameters: list[AdditionalParameter] = field(default_factory=list)


@dataclass(kw_only=True)
class GeneralData:
    """Module 1: General Data"""

    SENSOR: str
    SENSOR_URI: str | None = None
    PLATFORM: str
    PLATFORM_URI: str | None = None

    # Note that currently-approved values are "Airborne", "Spaceborne",
    # "Waterborne", and "Ground".
    OPERATION_DOMAIN: str

    CONTENT_LEVEL: int
    GEODETIC_SYSTEM: str = "WGS84"
    GEODETIC_TYPE: GeodeticType
    ELEVATION_DATUM: ElevationDatum
    LENGTH_UNIT: LengthUnit
    ANGULAR_UNIT: AngularUnit

    START_DATE: date
    START_TIME: float
    END_DATE: date
    END_TIME: float
    GENERATION_COUNT: int

    GENERATION_DATE: date | None = None
    GENERATION_TIME: float | None = None


class GeodeticType(StrEnum):
    GEOGRAPHIC = "G"
    CARTESIAN = "C"

    # The standard requires one of the two above options, but vendors will
    # sometimes leave this blank.
    NONCOMPLIANT_UNDEFINED = " "


class ElevationDatum(StrEnum):
    HAE = "HAE"
    MSL = "MSL"
    AGL = "AGL"

    # The standard requires one of the above options, but vendors will
    # sometimes leave this blank.
    NONCOMPLIANT_UNDEFINED = "   "


class LengthUnit(StrEnum):
    SI = "SI"
    EE = "EE"


class AngularUnit(StrEnum):
    DEG = "DEG"
    RAD = "RAD"
    SMC = "SMC"


@dataclass(kw_only=True)
class SensorArrayData:
    """Module 2: Sensor Array Data"""

    DETECTION: str
    ROW_DETECTORS: int
    COLUMN_DETECTORS: int
    ROW_METRIC: float | None
    COLUMN_METRIC: float | None
    FOCAL_LENGTH: float | None
    ROW_FOV: float | None
    COLUMN_FOV: float | None
    CALIBRATED: bool


@dataclass(kw_only=True)
class CalibrationData:
    """Module 3: Sensor Calibration Data"""

    CALIBRATION_UNIT: CalibrationUnit

    PRINCIPAL_POINT_OFFSET_X: float | None = None
    PRINCIPAL_POINT_OFFSET_Y: float | None = None

    RADIAL_DISTORT_1: float | None = None
    RADIAL_DISTORT_2: float | None = None
    RADIAL_DISTORT_3: float | None = None
    RADIAL_DISTORT_LIMIT: float | None = None

    DECENT_DISTORT_1: float | None = None
    DECENT_DISTORT_2: float | None = None

    AFFINITY_DISTORT_1: float | None = None
    AFFINITY_DISTORT_2: float | None = None

    CALIBRATION_DATE: date | None = None


class CalibrationUnit(StrEnum):
    MILLIMETERS = "mm"
    PIXELS = "px"


@dataclass(kw_only=True)
class ImageFormationData:
    """Module 4: Image Formation Data"""

    METHOD: str
    MODE: str
    ROW_COUNT: int
    COLUMN_COUNT: int
    ROW_SET: int
    COLUMN_SET: int
    ROW_RATE: float
    COLUMN_RATE: float
    FIRST_PIXEL_ROW: int
    FIRST_PIXEL_COLUMN: int
    transform_params: list[float] = field(default_factory=list)


@dataclass(kw_only=True)
class ReferenceData:
    """Module 5: Reference time/pixel

    # Note that the spec requires _at least_ one of (REFERENCE_TIME) or
    # (REFERENCE_ROW + REFERENCE_COLUMN) must be present, but does not force
    # them to be exclusive.
    """

    REFERENCE_TIME: float | None = None
    REFERENCE_ROW: float | None = None
    REFERENCE_COLUMN: float | None = None


@dataclass(kw_only=True)
class PositionData:
    """Moduel 6: Sensor Position"""

    LATITUDE_OR_X: float
    LONGITUDE_OR_Y: float | None
    ALTITUDE_OR_Z: float | None
    SENSOR_X_OFFSET: float
    SENSOR_Y_OFFSET: float
    SENSOR_Z_OFFSET: float


@dataclass(kw_only=True)
class EulerAngles:
    """Module 7: Attitude Euler Angles

    See §Z.5.3.1 for a full description of the sensor angle models 1, 2, and 3.
    """

    SENSOR_ANGLE_MODEL: Literal[1, 2, 3]
    SENSOR_ANGLE_1: float
    SENSOR_ANGLE_2: float
    SENSOR_ANGLE_3: float
    PLATFORM_RELATIVE: bool
    PLATFORM_HEADING: float | None = None
    PLATFORM_PITCH: float | None = None
    PLATFORM_ROLL: float | None = None


@dataclass(kw_only=True)
class UnitVectors:
    """Module 8: Attitude Unit Vectors"""

    ICX_NORTH_OR_X: float
    ICX_EAST_OR_Y: float
    ICX_DOWN_OR_Z: float
    ICY_NORTH_OR_X: float
    ICY_EAST_OR_Y: float
    ICY_DOWN_OR_Z: float
    ICZ_NORTH_OR_X: float
    ICZ_EAST_OR_Y: float
    ICZ_DOWN_OR_Z: float


@dataclass(kw_only=True)
class Quaternion:
    """Module 9: Attitude Quaternion"""

    ATTITUDE_Q1: float
    ATTITUDE_Q2: float
    ATTITUDE_Q3: float
    ATTITUDE_Q4: float


@dataclass(kw_only=True)
class SensorVelocity:
    """Module 10: Sensor Velocity Data"""

    VELOCITY_NORTH_OR_X: float
    VELOCITY_EAST_OR_Y: float
    VELOCITY_DOWN_OR_Z: float


@dataclass(kw_only=True)
class PointSet:
    """Module 11: Point Set Data"""

    POINT_SET_TYPE: str
    points: list[Point]


@dataclass(kw_only=True)
class Point:
    """A single point in a Point Set (Module 11)"""

    P_ROW: float
    P_COLUMN: float
    P_LATITUDE: float | None = None
    P_LONGITUDE: float | None = None
    P_ELEVATION: float | None = None
    P_RANGE: float | None = None


@dataclass(kw_only=True)
class TimeStampedDataSet:
    """Module 12: Time-Stamped Data Sets"""

    TIME_STAMP_TYPE: str
    instances: list[TimeStampInstance]


@dataclass(kw_only=True)
class TimeStampInstance:
    """An instance of a time-stamped dynamic parameter (Module 12)"""

    TIME_STAMP_TIME: float

    # Type will depend on the TIME_STAMP_TYPE.
    TIME_STAMP_VALUE: Any


@dataclass(kw_only=True)
class PixelReferencedDataSet:
    """Module 13: Pixel Referenced Data Sets"""

    PIXEL_REFERENCE_TYPE: str
    instances: list[PixelReferenceInstance]


@dataclass(kw_only=True)
class PixelReferenceInstance:
    """An instance of a pixel-referenced dynamic parameter (Module 13)"""

    PIXEL_REFERENCE_ROW: float
    PIXEL_REFERENCE_COLUMN: float

    # Type will depend on the PIXEL_REFERENCE_TYPE.
    PIXEL_REFERENCE_VALUE: Any


@dataclass(kw_only=True)
class Uncertainty:
    """Module 14: Uncertainty Data"""

    UNCERTAINTY_FIRST_TYPE: str
    UNCERTAINTY_SECOND_TYPE: str | None = None
    UNCERTAINTY_VALUE: float


@dataclass(kw_only=True)
class AdditionalParameter:
    """Module 15: Additional Parameter Data"""

    PARAMETER_NAME: str
    values: list[bytes]
