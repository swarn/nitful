import io

import pytest

from nitful import ParseError
from nitful.dsl.rules import Int, ParseContext, SizedList


def test_error_path_tracking():
    rule = SizedList(3, SizedList(2, Int("val", 2)))

    bad_bytes = b"0001101120XX"
    fd = io.BytesIO(bad_bytes)
    ctx = ParseContext()

    with pytest.raises(ParseError) as exc_info:
        rule.parse(fd, ctx)

    error_msg = str(exc_info.value)

    assert "at byte 10" in error_msg
    assert "SizedList" in error_msg
    assert "Int[2][1]" in error_msg
