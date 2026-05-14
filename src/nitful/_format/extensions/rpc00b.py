from nitful._format.tre import register_tre
from nitful.dsl.rules import (
    BcsString,
    Constant,
    ExpFloat,
    FixedFloat,
    Int,
    SizedList,
    Struct,
)
from nitful.dsl.validators import nonnegative, nonzero, positive
from nitful.extensions.rpc00b import RPC00B

rpc00b_spec = Struct(
    model_cls=RPC00B,
    rules=[
        Constant(BcsString("CETAG", 6), "RPC00B"),
        Constant(Int("CEL", 5), 1041),
        Constant(Int("SUCCESS", 1), 1),
        FixedFloat("ERR_BIAS", 7, nonnegative, ndigits=2),
        FixedFloat("ERR_RAND", 7, nonnegative, ndigits=2),
        Int("LINE_OFF", 6, nonnegative),
        Int("SAMP_OFF", 5, nonnegative),
        FixedFloat("LAT_OFF", 8, ndigits=4, sign=True),
        FixedFloat("LONG_OFF", 9, ndigits=4, sign=True),
        Int("HEIGHT_OFF", 5, sign=True),
        Int("LINE_SCALE", 6, positive),
        Int("SAMP_SCALE", 5, positive),
        FixedFloat("LAT_SCALE", 8, nonzero, sign=True, ndigits=4),
        FixedFloat("LONG_SCALE", 9, nonzero, sign=True, ndigits=4),
        Int("HEIGHT_SCALE", 5, nonzero, sign=True),
        SizedList(
            name="line_num_coeffs",
            count=20,
            body=ExpFloat("LINE_NUM_COEFF", 12, edigits=1),
        ),
        SizedList(
            name="line_den_coeffs",
            count=20,
            body=ExpFloat("LINE_DEN_COEFF", 12, edigits=1),
        ),
        SizedList(
            name="samp_num_coeffs",
            count=20,
            body=ExpFloat("SAMP_NUM_COEFF", 12, edigits=1),
        ),
        SizedList(
            name="samp_den_coeffs",
            count=20,
            body=ExpFloat("SAMP_DEN_COEFF", 12, edigits=1),
        ),
    ],
)

register_tre("RPC00B", rpc00b_spec)
