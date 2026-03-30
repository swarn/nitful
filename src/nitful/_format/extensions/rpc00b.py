from nitful._dsl.spec import (
    BcsFloat,
    BcsString,
    Constant,
    DataclassRecord,
    Fixed,
    Int,
    SizedList,
)
from nitful._dsl.validator import NonNegative, NonZero, Positive
from nitful._format.tre import register_tre
from nitful.extensions.rpc00b import RPC00B

rpc00b_spec = DataclassRecord(
    model_cls=RPC00B,
    specs=[
        Constant(BcsString("CETAG", 6), "RPC00B"),
        Constant(Int("CEL", 5), 1041),
        Constant(Int("SUCCESS", 1), 1),
        Fixed("ERR_BIAS", 7, NonNegative(), ndigits=2),
        Fixed("ERR_RAND", 7, NonNegative(), ndigits=2),
        Int("LINE_OFF", 6, NonNegative()),
        Int("SAMP_OFF", 5, NonNegative()),
        Fixed("LAT_OFF", 8, ndigits=4, sign=True),
        Fixed("LONG_OFF", 9, ndigits=4, sign=True),
        Int("HEIGHT_OFF", 5, sign=True),
        Int("LINE_SCALE", 6, Positive()),
        Int("SAMP_SCLE", 5, Positive()),
        Fixed("LAT_SCALE", 8, NonZero(), sign=True),
        Fixed("LONG_SCALE", 9, NonZero(), sign=True),
        Int("HEIGHT_SCALE", 5, NonZero(), sign=True),
        SizedList(
            name="line_num_coeffs",
            count=20,
            body=BcsFloat("LINE_NUM_COEFF", 12, edigits=1),
        ),
        SizedList(
            name="line_den_coeffs",
            count=20,
            body=BcsFloat("LINE_DEN_COEFF", 12, edigits=1),
        ),
        SizedList(
            name="samp_num_coeffs",
            count=20,
            body=BcsFloat("SAMP_NUM_COEFF", 12, edigits=1),
        ),
        SizedList(
            name="samp_den_coeffs",
            count=20,
            body=BcsFloat("SAMP_DEN_COEFF", 12, edigits=1),
        ),
    ],
)

register_tre("RPC00B", rpc00b_spec)
