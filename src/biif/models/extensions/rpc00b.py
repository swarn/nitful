from dataclasses import dataclass

from biif.models.common import TRE


@dataclass(kw_only=True)
class RPC00B(TRE):

    SUCCESS: bool = True

    ERR_BIAS: float = 0.0
    ERR_RAND: float = 0.0

    LINE_OFF: int
    SAMP_OFF: int
    LAT_OFF: float
    LONG_OFF: float
    HEIGHT_OFF: int

    LINE_SCALE: int
    SAMP_SCALE: int
    LAT_SCALE: float
    LONG_SCALE: float
    HEIGHT_SCALE: int

    LINE_NUM_COEFF: list[float]
    LINE_DEN_COEFF: list[float]
    SAMP_NUM_COEFF: list[float]
    SAMP_DEN_COEFF: list[float]
