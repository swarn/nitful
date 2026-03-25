from dataclasses import dataclass, field
from typing import ClassVar, override

from biif._dsl.spec import (
    BcsString,
    Constant,
    DataclassRecord,
    FieldSpec,
    Fixed,
    FixedLengthList,
    Int,
)
from biif._dsl.validator import NonNegative, NonZero, Positive
from biif._format.tre import register_tre
from biif.models.extensions.rpc00b import RPC00B


@dataclass
class RpcFloat(FieldSpec[float]):
    """Format numbers for NITF RPC coefficients.

    The TRE standard wants the polynomial coefficients to be 12 characters,
    formatted ±9.999999E±9. AFAIK, there's no way to get this with Python's
    scientific formatting, which defaults to two exponent digits.
    """

    size: int = field(default=12, init=False)

    # There is only one digit for exponents.
    MAX_EXPONENT: ClassVar[int] = 9
    MIN_EXPONENT: ClassVar[int] = -9

    @override
    def encode(self, decoded: float) -> bytes:
        nrepr = format(decoded, "+13.6E")
        mantissa, exponent = nrepr.split("E")

        exp_val = int(exponent)

        if exp_val > self.MAX_EXPONENT:
            msg = (
                f"RPC coefficient exponents must be <= {self.MAX_EXPONENT}, "
                f"but got {exp_val}"
            )
            raise ValueError(msg)

        # If the number's too small to represent, round to the zero with the
        # same sign as the number. Otherwise, remove the leading zero from the
        # exponent.
        if exp_val < self.MIN_EXPONENT:
            msign = mantissa[0]
            retval = f"{msign}0.000000E+0"
        else:
            esign = exponent[0]
            exp = exponent[2]
            retval = f"{mantissa}E{esign}{exp}"

        return retval.encode()

    @override
    def decode(self, encoded: bytes) -> float:
        return float(encoded.decode())


rpc00b_spec = DataclassRecord(
    name="RPC00B_RECORD",
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
        FixedLengthList(20, RpcFloat("LINE_NUM_COEFF")),
        FixedLengthList(20, RpcFloat("LINE_DEN_COEFF")),
        FixedLengthList(20, RpcFloat("SAMP_NUM_COEFF")),
        FixedLengthList(20, RpcFloat("SAMP_DEN_COEFF")),
    ],
)

register_tre("RPC00B", rpc00b_spec)
