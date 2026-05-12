from __future__ import annotations

from typing import BinaryIO

from nitful.core.common import EncryptionLevel, PixelCoord
from nitful.core.errors import ParseError
from nitful.core.graphic import GraphicColor, GraphicFormat, GraphicSegment
from nitful.dsl.rules import (
    BcsIntEnum,
    BcsString,
    BcsStringEnum,
    Constant,
    EcsString,
    EmitContext,
    FixedBytes,
    Int,
    Item,
    Packed,
    ParseContext,
    Struct,
)
from nitful.dsl.validators import in_range, positive

from .shared import Segment, security_spec
from .tre import TreBlock


def make_graphic_spec(ls: int) -> Segment[GraphicSegment]:
    return Segment(
        GraphicSegment,
        subheader=[
            Constant(BcsString("SY", 2), "SY"),
            BcsString("SID", 10),
            EcsString("SNAME", 20),
            security_spec,
            BcsIntEnum("ENCRYP", 1, enum=EncryptionLevel),
            BcsStringEnum("SFMT", 1, enum=GraphicFormat),
            Constant(Int("SSTRUCT", 13), 0),
            Int("SDLVL", 3, positive),
            Int("SALVL", 3, in_range(0, 998)),
            Packed(
                FixedBytes("SLOC", 10),
                Struct(PixelCoord, [Int("row", 5), Int("col", 5)]),
            ),
            Packed(
                FixedBytes("SBND1", 10),
                Struct(PixelCoord, [Int("row", 5), Int("col", 5)]),
            ),
            BcsStringEnum("SCOLOR", 1, enum=GraphicColor),
            Packed(
                FixedBytes("SBND2", 10),
                Struct(PixelCoord, [Int("row", 5), Int("col", 5)]),
            ),
            Constant(Int("SRES2", 2), 0),
            TreBlock(len_name="SXSHDL", ofl_name="SXSOFL", data_name="SXSHD"),
        ],
        data=[
            FixedBytes("raw_data", ls),
        ],
    )


def read_graphic_segment(
    fd: BinaryIO, lssh: int, ls: int, ctx: ParseContext
) -> GraphicSegment:
    start_pos = fd.tell()

    segment = make_graphic_spec(ls).parse(fd, ctx)

    nbytes_exp = lssh + ls
    nbytes_read = fd.tell() - start_pos
    if nbytes_read != nbytes_exp:
        msg = ctx.format_error(
            "parsing",
            f"Graphic segment: expected {nbytes_exp} bytes, read {nbytes_read}.",
            start_pos,
        )
        raise ParseError(msg)

    return segment


def graphic_to_fields(
    graphic: GraphicSegment, ctx: EmitContext
) -> tuple[list[Item], list[Item]]:
    ls = len(graphic.raw_data)
    return make_graphic_spec(ls).emit_segment(graphic, ctx)
