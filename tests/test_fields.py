import io
from decimal import Decimal
from enum import StrEnum

import pytest

from nitful import ParseError, SerializeError
from nitful.dsl.rules import (
    Accept,
    Blankable,
    Constant,
    DecimalFloat,
    EcsStringEnum,
    EmitContext,
    ExpFloat,
    FixedDecimal,
    FixedFloat,
    FlexFloat,
    Int,
    ParseContext,
)

# Table Format: (Rule, PyValue, ExpectedBytes (or Exception), ExpectedParseValue)
# fmt: off
FLOAT_TEST_CASES = [
    # Round up
    (FixedFloat("F", size=8, ndigits=2), 12.3456, b"00012.35", 12.35),

    # Pad right
    (FixedFloat("F", size=8, ndigits=2), 12.3, b"00012.30", 12.3),

    # Signs
    (FixedFloat("F", size=8, ndigits=2, sign=True), 12.3, b"+0012.30", 12.3),
    (FixedFloat("F", size=8, ndigits=2, sign=True), -12.3, b"-0012.30", -12.3),

    # Fails because 123456.7 encoded as "123456.70" is 9 bytes, exceeding size 8
    (FixedFloat("F", size=8, ndigits=2), 123456.7, SerializeError, None),

    # Remove trailing zeros and decimal
    (DecimalFloat("D", size=6), 123.0, b"000123", 123.0),

    # Exact right size
    (DecimalFloat("D", size=6), 12.345, b"12.345", 12.345),

    # Sign truncates precision
    (DecimalFloat("D", size=6), -12.345, b"-12.35", -12.35),

    # Pad with spaces
    (DecimalFloat("D", size=6, pad_char=" "), 12.3, b"  12.3", 12.3),
    (DecimalFloat("D", size=6, pad_char=" "), -12.3, b" -12.3", -12.3),

    # Rounding makes the resulting integer not fit
    (DecimalFloat("D", size=6), 999999.9, SerializeError, None),
    (DecimalFloat("D", size=6), -99999.9, SerializeError, None),

    # size=14, edigits=2 => precision = 14 - 2 - 5 = 7 digits
    (ExpFloat("E", size=14, edigits=2), 123.45, b"+1.2345000E+02", 123.45),
    (ExpFloat("E", size=14, edigits=2), -0.012345, b"-1.2345000E-02", -1.2345e-2),

    # Exponent too large
    (ExpFloat("E", size=14, edigits=2), 1e150, SerializeError, None),

    # Round to zero with correct sign for subnormals (exponent too small).
    (ExpFloat("E", size=14, edigits=2), 1e-105, b"+0.0000000E+00", 0.0),
    (ExpFloat("E", size=14, edigits=2), -1e-105, b"-0.0000000E+00", 0.0),

    (FlexFloat("FL", size=12), 12.345, b"00000012.345", 12.345),

    # Shed precision as needed
    (FlexFloat("FL", size=12), 1.23456789e13, b"1.234568e+13", 1.234568e+13),
    (FlexFloat("FL", size=12), -1.23456789e13, b"-1.23457e+13", -1.23457e+13),

    # Convert to scientific when needed
    (FlexFloat("FL", size=8), 123456789, b"1.23e+08", 1.23e8),

    # Doesn't fit as decimal or scientfic notation
    (FlexFloat("FL", size=4), 1234567.0, SerializeError, None),

    (
        FixedDecimal("FD", size=8, ndigits=2),
        Decimal("12.3456"),
        b"00012.35",
        Decimal("12.35"),
    ),
]
# fmt: on


@pytest.mark.parametrize("case", FLOAT_TEST_CASES)
def test_float_and_decimal_rules(case):
    rule, py_value, expected_bytes, expected_parsed = case

    emit_ctx = EmitContext()
    parse_ctx = ParseContext()

    if isinstance(expected_bytes, type) and issubclass(expected_bytes, Exception):
        with pytest.raises(SerializeError):
            rule.to_fields(py_value, emit_ctx)
        return

    items = rule.to_fields(py_value, emit_ctx)
    assert len(items) == 1
    assert items[0].value == expected_bytes

    fd = io.BytesIO(expected_bytes)
    parsed_val = rule.parse(fd, parse_ctx)

    if isinstance(parsed_val, float):
        assert parsed_val == pytest.approx(expected_parsed)
    else:
        assert parsed_val == expected_parsed


class MockEnum(StrEnum):
    DEFAULT = "A"
    OTHER = "B"


blankable_int = Blankable(Int("I", size=2))
accept_sec = Accept(
    EcsStringEnum("CLAS", size=1, enum=MockEnum),
    mapping={b" ": MockEnum.DEFAULT},
)

WRAPPER_TESTS = [
    (blankable_int, b"  ", None),
    (blankable_int, b"11", 11),
    (accept_sec, b" ", MockEnum.DEFAULT),
    (accept_sec, b"A", MockEnum.DEFAULT),
    (accept_sec, b"B", MockEnum.OTHER),
]


@pytest.mark.parametrize("case", WRAPPER_TESTS)
def test_wrapper_parse_interception(case):
    rule, raw_bytes, expected = case
    parsed = rule.parse(io.BytesIO(raw_bytes), ParseContext())
    assert parsed == expected


def test_constant():
    constant_int = Constant(Int("C", size=2), value=2)

    with pytest.raises(ParseError):
        constant_int.parse(io.BytesIO(b"03"), ParseContext())

    with pytest.raises(SerializeError):
        constant_int.to_fields(3, EmitContext())
