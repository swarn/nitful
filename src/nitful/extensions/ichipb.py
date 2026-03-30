from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from nitful.core.common import TRE


@dataclass(kw_only=True)
class ICHIPB(TRE):
    XFRM_FLAG: TransformFlag
    SCALE_FACTOR: float
    ANAMRPH_CORR: AnamorphicCorrection
    SCANBLK_NUM: int
    OP_ROW_11: float
    OP_COL_11: float
    OP_ROW_12: float
    OP_COL_12: float
    OP_ROW_21: float
    OP_COL_21: float
    OP_ROW_22: float
    OP_COL_22: float
    FI_ROW_11: float
    FI_COL_11: float
    FI_ROW_12: float
    FI_COL_12: float
    FI_ROW_21: float
    FI_COL_21: float
    FI_ROW_22: float
    FI_COL_22: float
    FI_ROW: int
    FI_COL: int


class TransformFlag(Enum):
    PROVIDED = 0
    NOT = 1


class AnamorphicCorrection(Enum):
    NONE = 0
    APPLIED = 1
