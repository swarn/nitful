"""CSSFAB DES"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import IntEnum, StrEnum
from uuid import UUID as UUID_T

from nitful.core.common import DES


@dataclass(kw_only=True)
class CSSFAB(DES):

    DESID: str = "CSSFAB"
    DESVER: int = 2

    UUID: UUID_T
    images: list[int] = field(default_factory=list)
    elements: list[UUID_T] = field(default_factory=list)

    BAND_TYPE: BandCategory
    BAND_WAVELENGTH: float
    bands: list[BandInfo]

    FL_INTERP: FocalLengthInterpolation
    FOC_LENGTH_DATE: date
    focal_lengths: list[FocalLengthPoint]

    # (X, Y, Z) offset from center of mass to mirror vertex.
    position_offset: list[float]

    # (X, Y, Z) angular offset from attitude reference frame to sensor frame.
    angle_offset: list[float]

    alignment: ScannerAlignment | FramerAlignment

    # Unknown Reserved Field Areas are placed here during parsing
    unknown_extensions: dict[int, bytes] = field(default_factory=dict)


class BandCategory(StrEnum):
    MONO = "M"
    RED = "R"
    GREEN = "G"
    BLUE = "B"
    NIR = "N"
    SIR = "S"
    MIR = "I"
    LIR = "L"
    NONE = " "


@dataclass
class BandInfo:
    BAND_INDEX: int
    IREPBAND: str
    ISUBCAT: str


class FocalLengthInterpolation(IntEnum):
    NEAREST = 0
    LINEAR = 1


@dataclass
class FocalLengthPoint:
    FOC_LENGTH_TIME: float
    FOC_LENGTH: float


@dataclass
class ScannerAlignment:
    SMPL_NUM_FIRST: float
    DELTA_SMPL_PAIRS: float
    fa_pairs: list[FieldAlignmentPair]


@dataclass
class FieldAlignmentPair:
    START_FALIGN_X: float
    START_FALIGN_Y: float
    END_FALIGN_X: float
    END_FALIGN_Y: float


@dataclass
class FramerAlignment:
    FA_INTERP: FocalLengthInterpolation
    field_angle_data: DirectFieldAngleData | CalibrationFieldAngleData
    telescope_optics: TelescopeOpticsFrameBased | TelescopeOpticsTimeBased | None


@dataclass
class DirectFieldAngleData:
    sets: list[FrameFieldAngleSetDirect]


@dataclass
class FrameFieldAngleSetDirect:
    FL_CAL: float
    NUM_FIR_LINE: float
    DELTA_LINE: float
    NUM_FIR_SAMP: float
    DELTA_SAMP: float

    # 2D array: [Rows (line axis)][Cols (sample axis)]
    blocks: list[list[FrameFieldAlignmentBlock]]


@dataclass
class FrameFieldAlignmentBlock:
    FA_X1: float
    FA_Y1: float
    FA_X2: float
    FA_Y2: float
    FA_X3: float
    FA_Y3: float
    FA_X4: float
    FA_Y4: float


@dataclass
class CalibrationFieldAngleData:
    # An array with shape (nrows, ncols, 8).
    fp_arrays: list[list[list[float]]]
    sets: list[FrameFieldAngleSetCalibration]


@dataclass
class FrameFieldAngleSetCalibration:
    FL_CAL_IOP: float
    PPO_XO: float
    PPO_YO: float
    RLD_KO: float
    RLD_K1: float
    RLD_K2: float
    RLD_K3: float
    DCD_P1: float
    DCD_P2: float
    DCD_P3: float
    AD_A1: float
    AD_A2: float
    RADIUS_OF_VALIDITY: float


@dataclass
class TelescopeOpticsFrameBased:
    # Array has shape (nframes, 8).
    frames: list[list[float]]
    datasets: list[TelescopeOpticsDataSet]


@dataclass
class TelescopeOpticsDataSet:
    FL_CAL_IOP_TELE: float
    PPO_XO_TELE: float
    PPO_YO_TELE: float
    RLD_KO_TELE: float
    RLD_K1_TELE: float
    RLD_K2_TELE: float
    RLD_K3_TELE: float
    DCD_P1_TELE: float
    DCD_P2_TELE: float
    DCD_P3_TELE: float
    AD_A1_TELE: float
    AD_A2_TELE: float
    RADIUS_OF_VALIDITY_TELE: float


@dataclass
class TelescopeOpticsTimeBased:
    varying_io_parm_ids: list[TimeVaryingIoParmId]
    TELE_DATE: date
    times: list[TelescopeOpticsTimeTransform]
    datasets: list[TelescopeOpticsDataSet]


class TimeVaryingIoParmId(IntEnum):
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


@dataclass
class TelescopeOpticsTimeTransform:
    TELE_TIME: float
    transform: list[float]
    varying_io_m: list[float]
