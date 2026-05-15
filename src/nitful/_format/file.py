from __future__ import annotations

from dataclasses import dataclass, fields
from os import SEEK_CUR
from typing import BinaryIO

from nitful.core.common import EncryptionLevel
from nitful.core.file import RGB, NitfFile
from nitful.dsl.rules import (
    BcsIntEnum,
    BcsString,
    BinaryInt,
    Check,
    ConcatDatetime,
    Constant,
    EcsString,
    EmitContext,
    FixedBytes,
    Group,
    Int,
    Item,
    Packed,
    ParseContext,
    PrefixedList,
    Struct,
    item_size,
)
from nitful.dsl.validators import nonnegative, notblank, one_of

from .des import des_to_fields, read_des
from .graphic import graphic_to_fields, read_graphic_segment
from .image import image_to_fields, read_image_segment
from .shared import security_spec
from .text import read_text_segment, text_to_fields
from .tre import TreBlock


@dataclass
class ImageSegmentInfo:
    LISH: int
    LI: int


@dataclass
class GraphicSegmentInfo:
    LSSH: int
    LS: int


@dataclass
class TextSegmentInfo:
    LTSH: int
    LT: int


@dataclass
class DataSegmentInfo:
    LDSH: int
    LD: int


@dataclass
class ReservedSegmentInfo:
    LRESH: int
    LRE: int


header_spec = Group([
    Check(BcsString("FHDR", 4, one_of("NITF", "NSIF"))),
    Check(BcsString("FVER", 5, one_of("01.00", "01.01", "02.10"))),
    Int("CLEVEL", 2, one_of(3, 5, 6, 7, 9, 51, 54, 57)),
    BcsString("STYPE", 4, one_of("BF01")),
    BcsString("OSTAID", 10, notblank),
    ConcatDatetime("FDT"),
    EcsString("FTITLE", 80),
    security_spec("F"),
    Int("FSCOP", 5, nonnegative),
    Int("FSCPYS", 5, nonnegative),
    BcsIntEnum("ENCRYP", 1, enum=EncryptionLevel),
    Packed(
        FixedBytes("FBKGC", 3),
        Struct(RGB, [BinaryInt("r", 1), BinaryInt("g", 1), BinaryInt("b", 1)]),
    ),
    EcsString("ONAME", 24),
    EcsString("OPHONE", 18),
    Int("FL", 12),
    Int("HL", 6),
    PrefixedList(
        name="image_segment_info",
        count=Int("NUMI", 3),
        body=Struct(ImageSegmentInfo, [Int("LISH", 6), Int("LI", 10)]),
    ),
    PrefixedList(
        name="graphic_segment_info",
        count=Int("NUMS", 3),
        body=Struct(GraphicSegmentInfo, [Int("LSSH", 4), Int("LS", 6)]),
    ),
    Constant(Int("NUMX", 3), 0),
    PrefixedList(
        name="text_segment_info",
        count=Int("NUMT", 3),
        body=Struct(TextSegmentInfo, [Int("LTSH", 4), Int("LT", 5)]),
    ),
    PrefixedList(
        name="data_segment_info",
        count=Int("NUMDES", 3),
        body=Struct(DataSegmentInfo, [Int("LDSH", 4), Int("LD", 9)]),
    ),
    PrefixedList(
        name="reserved_segment_info",
        count=Int("NUMRES", 3),
        body=Struct(ReservedSegmentInfo, [Int("LRESH", 4), Int("LRE", 7)]),
    ),
    TreBlock("UDHDL", "UDHOFL", "UDHD"),
    TreBlock("XHDL", "XHDLOFL", "XHD"),
])


def read_file(fd: BinaryIO, ctx: ParseContext) -> NitfFile:
    header = header_spec.parse(fd, ctx)

    # Read the image segments. Each segment includes all relevant size
    # information, so the sizes in the file header are mostly useful for
    # skipping past segments, or for verifying correct reads.
    image_segments = [
        read_image_segment(fd, lish=info.LISH, li=info.LI, ctx=ctx)
        for info in header["image_segment_info"]
    ]

    # Read the graphic segments.
    graphic_segments = [
        read_graphic_segment(fd, lssh=info.LSSH, ls=info.LS, ctx=ctx)
        for info in header["graphic_segment_info"]
    ]

    # Read the text segments.
    text_segments = [
        read_text_segment(fd, ltsh=info.LTSH, lt=info.LT, ctx=ctx)
        for info in header["text_segment_info"]
    ]

    # Read the data segments. Again, each segment includes size info. The
    # factory function generates the correct DES type.
    data_segments = [
        read_des(fd, info.LDSH, info.LD, ctx) for info in header["data_segment_info"]
    ]

    # Not supporting reserved segments yet.
    for info in header["reserved_segment_info"]:
        segment_size = info.LRESH + info.LRE
        fd.seek(segment_size, SEEK_CUR)

    # TODO: fd should be empty at this point, check that.

    valid_fields = {f.name for f in fields(NitfFile)}
    valid_keys = header.keys() & valid_fields

    kwargs = {k: header[k] for k in valid_keys}
    kwargs["image_segments"] = image_segments
    kwargs["graphic_segments"] = graphic_segments
    kwargs["text_segments"] = text_segments
    kwargs["data_segments"] = data_segments

    return NitfFile(**kwargs)


def to_fields(nitf: NitfFile) -> list[Item]:
    ctx = EmitContext()

    # We know how many segments there are, but not their sizes.
    dummy_imgs = [ImageSegmentInfo(0, 0) for _ in nitf.image_segments]
    dummy_gss = [GraphicSegmentInfo(0, 0) for _ in nitf.graphic_segments]
    dummy_tss = [TextSegmentInfo(0, 0) for _ in nitf.text_segments]
    dummy_dess = [DataSegmentInfo(0, 0) for _ in nitf.data_segments]

    # Generate the header fields with dummy values for all lengths.
    header_kwargs = vars(nitf).copy()
    header_kwargs.update({
        "FL": 0,
        "HL": 0,
        "image_segment_info": dummy_imgs,
        "graphic_segment_info": dummy_gss,
        "text_segment_info": dummy_tss,
        "data_segment_info": dummy_dess,
        "reserved_segment_info": [],
    })
    header_fields = header_spec.to_fields(header_kwargs, ctx)

    # Map so that we can look up and patch the length fields later.
    field_map = {f.name: f for f in header_fields}

    # Fill in the length of the header.
    hl = item_size(header_fields)
    field_map["HL"].value = Int("HL", 6).encode(hl)

    segment_fields: list[Item] = []

    for i, img in enumerate(nitf.image_segments):
        img_subhead, img_data = image_to_fields(img, ctx)

        lish = item_size(img_subhead)
        field_map[f"LISH[{i}]"].value = Int("LISH", 6).encode(lish)
        li = item_size(img_data)
        field_map[f"LI[{i}]"].value = Int("LI", 10).encode(li)

        segment_fields.extend(img_subhead)
        segment_fields.extend(img_data)

    for i, gs in enumerate(nitf.graphic_segments):
        gs_subhead, gs_data = graphic_to_fields(gs, ctx)

        lssh = item_size(gs_subhead)
        field_map[f"LSSH[{i}]"].value = Int("LSSH", 4).encode(lssh)
        ls = item_size(gs_data)
        field_map[f"LS[{i}]"].value = Int("LS", 6).encode(ls)

        segment_fields.extend(gs_subhead)
        segment_fields.extend(gs_data)

    for i, ts in enumerate(nitf.text_segments):
        ts_subhead, ts_data = text_to_fields(ts, ctx)

        ltsh = item_size(ts_subhead)
        field_map[f"LTSH[{i}]"].value = Int("LTSH", 4).encode(ltsh)
        lt = item_size(ts_data)
        field_map[f"LT[{i}]"].value = Int("LT", 5).encode(lt)

        segment_fields.extend(ts_subhead)
        segment_fields.extend(ts_data)

    for i, des in enumerate(nitf.data_segments):
        des_subhead, des_data = des_to_fields(des, ctx)

        ldsh = item_size(des_subhead)
        field_map[f"LDSH[{i}]"].value = Int("LDSH", 4).encode(ldsh)
        ld = item_size(des_data)
        field_map[f"LD[{i}]"].value = Int("LD", 9).encode(ld)

        segment_fields.extend(des_subhead)
        segment_fields.extend(des_data)

    # Reserved segments will go here.

    # Patch the file length.
    fl = hl + item_size(segment_fields)
    field_map["FL"].value = Int("FL", 12).encode(fl)

    return header_fields + segment_fields
