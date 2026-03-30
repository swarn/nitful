from dataclasses import dataclass

from nitful.core.common import TRE


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

    line_num_coeffs: list[float]
    line_den_coeffs: list[float]
    samp_num_coeffs: list[float]
    samp_den_coeffs: list[float]
