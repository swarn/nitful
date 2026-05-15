from __future__ import annotations

from typing import BinaryIO

from nitful.core.common import EncryptionLevel
from nitful.core.errors import ParseError
from nitful.core.text import TextFormat, TextSegment
from nitful.dsl.rules import (
    BcsIntEnum,
    BcsString,
    BcsStringEnum,
    ConcatDatetime,
    Constant,
    EcsString,
    EmitContext,
    FixedBytes,
    Int,
    Item,
    ParseContext,
)
from nitful.dsl.validators import in_range

from .shared import Segment, security_spec
from .tre import TreBlock


def make_text_spec(lt: int) -> Segment[TextSegment]:
    return Segment(
        TextSegment,
        subheader=[
            Constant(BcsString("TE", 2), "TE"),
            BcsString("TEXTID", 7),
            Int("TXTALVL", 3, in_range(0, 998)),
            ConcatDatetime("TXTDT"),
            EcsString("TXTITL", 80),
            security_spec("T"),
            BcsIntEnum("ENCRYP", 1, enum=EncryptionLevel),
            BcsStringEnum("TXTFMT", 3, enum=TextFormat),
            TreBlock(len_name="TXSHDL", ofl_name="TXSOFL", data_name="TXSHD"),
        ],
        data=[
            FixedBytes("raw_data", lt),
        ],
    )


def read_text_segment(
    fd: BinaryIO, ltsh: int, lt: int, ctx: ParseContext
) -> TextSegment:
    start_pos = fd.tell()

    segment = make_text_spec(lt).parse(fd, ctx)

    nbytes_exp = ltsh + lt
    nbytes_read = fd.tell() - start_pos
    if nbytes_read != nbytes_exp:
        cause = f"Text segment: expected {nbytes_exp} bytes, read {nbytes_read}."
        msg = ctx.format_error(cause, start_pos)
        raise ParseError(msg)

    return segment


def text_to_fields(
    text: TextSegment, ctx: EmitContext
) -> tuple[list[Item], list[Item]]:
    lt = len(text.raw_data)
    return make_text_spec(lt).emit_segment(text, ctx)
