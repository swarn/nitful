from __future__ import annotations

from dataclasses import dataclass, fields
from io import SEEK_CUR
from pathlib import Path
from typing import Any, BinaryIO, ClassVar, override

from nitful.core.common import EncryptionLevel, PixelCoord
from nitful.core.errors import ParseError
from nitful.core.image import (
    BandInfo,
    Compression,
    Coords,
    DeferredImageData,
    ImageSegment,
    PixelJustification,
    PixelType,
)
from nitful.dsl.rules import (
    BcsIntEnum,
    BcsString,
    BcsStringEnum,
    BinaryInt,
    Combinator,
    Conditional,
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
    Rule,
    Struct,
)
from nitful.dsl.validators import in_range, nonnegative, one_of, positive

from .shared import security_spec
from .tre import TreBlock


@dataclass
class NumBands(Combinator[int]):

    MAX_NBANDS: ClassVar[int] = 9

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> int:
        nbands = Int("NBANDS", 1).parse(fd, ctx)
        if nbands == 0:
            nbands = Int("XBANDS", 5).parse(fd, ctx)
        return nbands

    @override
    def _emit(self, value: int, *, ctx: EmitContext) -> list[Item]:
        if value <= self.MAX_NBANDS:
            return Int("NBANDS", 1).to_fields(value, ctx)

        nbands = Int("NBANDS", 1).to_fields(0, ctx)
        xbands = Int("XBANDS", 4).to_fields(value, ctx)
        return nbands + xbands


@dataclass
class IcordsSpec(Combinator[Coords | None]):

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> Coords | None:
        ic_rep = BcsString("ICORDS", 1).parse(fd, ctx)

        if ic_rep == "":
            return None

        args = [ic_rep]
        args.extend(BcsString("", 15).parse(fd, ctx) for _ in range(4))

        return Coords(*args)

    @override
    def _emit(self, value: Coords | None, *, ctx: EmitContext) -> list[Item]:
        if value is None:
            return BcsString("ICORDS", 1).to_fields(" ", ctx)

        icords_fields = BcsString("ICORDS", 1).to_fields(value.ICORDS, ctx)
        igeolo_bytes = b"".join(
            BcsString("", 15).encode(c)
            for c in [
                value.upperleft,
                value.upperright,
                value.lowerright,
                value.lowerleft,
            ]
        )

        return [*icords_fields, Item("IGEOLO", igeolo_bytes)]


@dataclass
class LutsSpec(Combinator[list[list[int]]]):

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> list[list[int]]:
        nluts = Int("NLUTS", 1).parse(fd, ctx)
        if nluts == 0:
            return []

        nelut = Int("NELUT", 5).parse(fd, ctx)

        lut_spec = BinaryInt("LUTD", 1)
        return [
            [lut_spec.parse(fd, ctx) for _ in ctx.iterate(range(nelut))]
            for _ in ctx.iterate(range(nluts))
        ]

    @override
    def _emit(self, value: list[list[int]], *, ctx: EmitContext) -> list[Item]:
        nluts = len(value)
        out = Int("NLUTS", 1).to_fields(nluts, ctx)

        if nluts == 0:
            return out

        nelut = len(value[0])
        out += Int("NELUT", 5).to_fields(nelut, ctx)

        if not all(len(lut) == nelut for lut in value):
            msg = "All LUTs must have the same length."
            raise ValueError(msg)

        for lut in ctx.iterate(value):
            for entry in ctx.iterate(lut):
                out += BinaryInt("LUTD", 1).to_fields(entry, ctx)

        return out


compression = Struct(
    name="compression",
    model_cls=Compression,
    rules=[
        BcsString("IC", 2),
        Conditional(
            name="COMRAT",
            condition=lambda ctx: ctx["IC"] not in {"NC", "NM"},
            body=BcsString("COMRAT", 4),
        ),
    ],
)

image_head_spec: list[Rule[Any]] = [
    Constant(BcsString("IM", 2), "IM"),
    BcsString("IID1", 10),
    BcsString("IDATIM", 14),
    BcsString("TGTID", 17),
    BcsString("IID2", 80),
    security_spec,
    BcsIntEnum("ENCRYP", 1, enum=EncryptionLevel),
    BcsString("ISORCE", 42),
    Int("NROWS", 8),
    Int("NCOLS", 8),
    BcsStringEnum("PVTYPE", 3, enum=PixelType),
    BcsString("IREP", 8),
    BcsString("ICAT", 8),
    Int("ABPP", 2),
    BcsStringEnum("PJUST", 1, enum=PixelJustification),
    IcordsSpec(name="location"),
    PrefixedList(
        name="comments",
        count=Int("NICOM", 1, nonnegative),
        body=EcsString("ICOM", 80),
    ),
    compression,
    PrefixedList(
        name="bands",
        count=NumBands(),
        body=Struct(
            BandInfo,
            [
                BcsString("IREPBAND", 2),
                BcsString("ISUBCAT", 6),
                BcsString("IFC", 1),
                BcsString("IMFLT", 3),
                LutsSpec(name="luts"),
            ],
        ),
    ),
    Constant(Int("ISYNC", 1), 0),
    BcsString("IMODE", 1, one_of("B", "P", "R", "S")),
    Int("NBPR", 4, positive),
    Int("NBPC", 4, positive),
    Int("NPPBH", 4, in_range(0, 8192)),
    Int("NPPBV", 4, in_range(0, 8192)),
    Int("NBPP", 2, in_range(1, 64)),
    Int("IDLVL", 3, positive),
    Int("IALVL", 3, in_range(0, 998)),
    Packed(
        FixedBytes("ILOC", 10),
        Struct(PixelCoord, [Int("row", 5), Int("col", 5)]),
    ),
    BcsString("IMAG", 4),
    TreBlock("UDIDL", "UDOFL", "UDID"),
    TreBlock("IXSHDL", "IXSOFL", "IXSHD"),
]


def read_image_segment(
    fd: BinaryIO, lish: int, li: int, ctx: ParseContext
) -> ImageSegment:
    start_pos = fd.tell()

    header = Group(image_head_spec).parse(fd, ctx)

    nbytes_read = fd.tell() - start_pos
    if nbytes_read != lish:
        cause = f"Image segment header expected {lish} bytes, read {nbytes_read}."
        msg = ctx.format_error(cause, start_pos)
        raise ParseError(msg)

    path = None
    if hasattr(fd, "name") and isinstance(fd.name, str) and Path(fd.name).exists():
        path = fd.name

    data_proxy = DeferredImageData(path=path, offset=fd.tell(), length=li)

    # Add a field entry to the context parsing history to represent the image data.
    ctx.fields.append((Item("IMAGE DATA", data_proxy), fd.tell()))

    fd.seek(li, SEEK_CUR)

    valid_fields = {f.name for f in fields(ImageSegment)}
    valid_keys = header.keys() & valid_fields
    kwargs = {k: header[k] for k in valid_keys}

    return ImageSegment(**kwargs, data=data_proxy)


def image_to_fields(
    image: ImageSegment, ctx: EmitContext
) -> tuple[list[Item], list[Item]]:
    out_fields = Group(image_head_spec).to_fields(vars(image), ctx)
    data_field = Item(name="IMAGE DATA", value=image.data)

    return out_fields, [data_field]
