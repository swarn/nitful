from nitful._dsl.rules import (
    BcsIntEnum,
    BcsString,
    Constant,
    Fixed,
    Int,
    Struct,
)
from nitful._dsl.validator import NonNegative
from nitful._format.tre import register_tre
from nitful.extensions.ichipb import ICHIPB, AnamorphicCorrection, TransformFlag

ichipb_spec = Struct(
    ICHIPB,
    [
        Constant(BcsString("CETAG", 6), "ICHIPB"),
        Constant(Int("CEL", 5), 224),
        BcsIntEnum("XFRM_FLAG", 2, enum=TransformFlag),
        Fixed("SCALE_FACTOR", 10, ndigits=5),
        BcsIntEnum("ANAMRPH_CORR", 2, enum=AnamorphicCorrection),
        Int("SCANBLK_NUM", 2, NonNegative()),
        Fixed("OP_ROW_11", 12, NonNegative(), ndigits=3),
        Fixed("OP_COL_11", 12, NonNegative(), ndigits=3),
        Fixed("OP_ROW_12", 12, NonNegative(), ndigits=3),
        Fixed("OP_COL_12", 12, NonNegative(), ndigits=3),
        Fixed("OP_ROW_21", 12, NonNegative(), ndigits=3),
        Fixed("OP_COL_21", 12, NonNegative(), ndigits=3),
        Fixed("OP_ROW_22", 12, NonNegative(), ndigits=3),
        Fixed("OP_COL_22", 12, NonNegative(), ndigits=3),
        Fixed("FI_ROW_11", 12, NonNegative(), ndigits=3),
        Fixed("FI_COL_11", 12, NonNegative(), ndigits=3),
        Fixed("FI_ROW_12", 12, NonNegative(), ndigits=3),
        Fixed("FI_COL_12", 12, NonNegative(), ndigits=3),
        Fixed("FI_ROW_21", 12, NonNegative(), ndigits=3),
        Fixed("FI_COL_21", 12, NonNegative(), ndigits=3),
        Fixed("FI_ROW_22", 12, NonNegative(), ndigits=3),
        Fixed("FI_COL_22", 12, NonNegative(), ndigits=3),
        Int("FI_ROW", 8, NonNegative()),
        Int("FI_COL", 8, NonNegative()),
    ],
)

register_tre("ICHIPB", ichipb_spec)
