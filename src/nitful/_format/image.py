from __future__ import annotations

from dataclasses import dataclass, fields
from io import SEEK_CUR
from pathlib import Path
from typing import Any, BinaryIO, ClassVar, override

from nitful._dsl.spec import (
    BcsIntEnum,
    BcsString,
    BcsStringEnum,
    BinaryInt,
    Constant,
    DataclassRecord,
    DictRecord,
    EcsString,
    EmitContext,
    Field,
    Int,
    Marker,
    ParseContext,
    PrefixedList,
    Spec,
)
from nitful._dsl.validator import Literals, NonNegative, Positive, Range
from nitful.core.common import EncryptionLevel, Security
from nitful.core.image import (
    BandInfo,
    Compression,
    Coords,
    DeferredImageData,
    ImageSegment,
    PixelJustification,
    PixelType,
)

from .security import security_spec
from .tre import read_tre_list, tre_list_to_fields


@dataclass
class NumBands(Spec[int]):

    name: str = ""

    MAX_NBANDS: ClassVar[int] = 9

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> int:
        nbands = Int("NBANDS", 1).parse(fd, ctx)
        if nbands == 0:
            nbands = Int("XBANDS", 4).parse(fd, ctx)
        return nbands

    @override
    def _emit(self, value: int, *, ctx: EmitContext) -> list[Field]:
        if value <= self.MAX_NBANDS:
            return Int("NBANDS", 1).to_fields(value, ctx)

        nbands = Int("NBANDS", 1).to_fields(0, ctx)
        xbands = Int("XBANDS", 4).to_fields(value, ctx)
        return nbands + xbands


@dataclass
class CompressionSpec(Spec[Compression]):

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> Compression:
        ic = BcsString("IC", 2).parse(fd, ctx)
        kwargs = {"IC": ic}

        if ic not in {"NC", "NM"}:
            kwargs["COMRAT"] = BcsString("COMRAT", 4).parse(fd, ctx)

        return Compression(**kwargs)

    @override
    def _emit(self, value: Compression, *, ctx: EmitContext) -> list[Field]:
        out_fields = BcsString("IC", 2).to_fields(value.IC, ctx)

        if Compression.IC not in {"NC", "NM"}:
            out_fields += BcsString("COMRAT", 4).to_fields(value.COMRAT, ctx)

        return out_fields


@dataclass
class IcordsSpec(Spec[Coords | None]):

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> Coords | None:
        ic_rep = BcsString("ICORDS", 1).parse(fd, ctx)

        if ic_rep == "":
            return None

        args = [ic_rep]
        args.extend(BcsString("", 15).parse(fd, ctx) for _ in range(4))

        return Coords(*args)

    @override
    def _emit(self, value: Coords | None, *, ctx: EmitContext) -> list[Field]:
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

        return [*icords_fields, Field("IGEOLO", igeolo_bytes)]


@dataclass
class LutsSpec(Spec[list[list[int]]]):

    name: str

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> list[list[int]]:
        nluts = Int("NLUTS", 1).parse(fd, ctx)
        if nluts == 0:
            return []

        nelut = Int("NELUT", 5).parse(fd, ctx)

        lut_spec = BinaryInt("LUTD", 1)
        return [[lut_spec.parse(fd, ctx) for _ in range(nelut)] for _ in range(nluts)]

    @override
    def _emit(self, value: list[list[int]], *, ctx: EmitContext) -> list[Field]:
        nluts = len(value)
        out = Int("NLUTS", 1).to_fields(nluts, ctx)

        if nluts == 0:
            return out

        nelut = len(value[0])
        out += Int("NELUT", 5).to_fields(nelut, ctx)

        if not all(len(lut) == nelut for lut in value):
            raise ValueError

        for lut in value:
            for entry in lut:
                out += BinaryInt("LUTD", 1).to_fields(entry, ctx)

        return out


image_head_spec: list[Spec[Any]] = [
    Marker("IMAGE START"),
    Constant(BcsString("IM", 2), "IM"),
    BcsString("IID1", 10),
    BcsString("IDATIM", 14),
    BcsString("TGTID", 17),
    BcsString("IID2", 80),
    DataclassRecord(Security, security_spec, name="security"),
    BcsIntEnum("ENCRYP", 1, enum=EncryptionLevel),
    BcsString("ISORCE", 42),
    Int("NROWS", 8),
    Int("NCOLS", 8),
    BcsStringEnum("PVTYPE", 3, enum=PixelType),
    BcsString("IREP", 8),
    BcsString("ICAT", 8),
    Int("ABPP", 2),
    BcsStringEnum("PJUST", 1, enum=PixelJustification),
    IcordsSpec("location"),
    PrefixedList(
        name="comments",
        count=Int("NICOM", 1, NonNegative()),
        body=EcsString("ICOM", 80),
    ),
    CompressionSpec("compression"),
    PrefixedList(
        name="bands",
        count=NumBands(),
        body=DataclassRecord(
            BandInfo,
            [
                BcsString("IREPBAND", 2),
                BcsString("ISUBCAT", 6),
                BcsString("IFC", 1),
                BcsString("IMFLT", 3),
                LutsSpec("luts"),
            ],
        ),
    ),
    Constant(Int("ISYNC", 1), 0),
    BcsString("IMODE", 1, Literals(["B", "P", "R", "S"])),
    Int("NBPR", 4, Positive()),
    Int("NBPC", 4, Positive()),
    Int("NPPBH", 4, Range(0, 8192)),
    Int("NPPBV", 4, Range(0, 8192)),
    Int("NBPP", 2, Range(1, 64)),
    Int("IDLVL", 3, Positive()),
    Int("IALVL", 3, Range(0, 998)),
    Int("ILOCROW", 5, Range(-9999, 99999)),
    Int("ILOCCOL", 5, Range(-9999, 99999)),
    BcsString("IMAG", 4),
]


def read_image_segment(fd: BinaryIO, lish: int, li: int) -> ImageSegment:
    start_pos = fd.tell()

    header = DictRecord(image_head_spec).parse(fd, ParseContext())

    udid = read_tre_list(fd, "UDIDL", "UDOFL")
    ixshd = read_tre_list(fd, "IXSHDL", "IXSOFL")

    if fd.tell() != start_pos + lish:
        msg = "Image segment header has wrong length"
        raise RuntimeError(msg)

    path = None
    if hasattr(fd, "name") and isinstance(fd.name, str) and Path(fd.name).exists():
        path = fd.name

    data_proxy = DeferredImageData(path=path, offset=fd.tell(), length=li)
    fd.seek(li, SEEK_CUR)

    valid_fields = {f.name for f in fields(ImageSegment)}
    valid_keys = header.keys() & valid_fields
    kwargs = {k: header[k] for k in valid_keys}
    kwargs["UDID"] = udid
    kwargs["IXSHD"] = ixshd

    return ImageSegment(**kwargs, data=data_proxy)


def image_to_fields(image: ImageSegment) -> list[Field]:
    ctx = EmitContext(vars(image))
    out_fields = DictRecord(image_head_spec).to_fields(vars(image), ctx)

    udid_fields = tre_list_to_fields(image.UDID, "UDIDL", "UDOFL")
    out_fields.extend(udid_fields)

    ixshd_fields = tre_list_to_fields(image.IXSHD, "IXSHDL", "IXSOFL")
    out_fields.extend(ixshd_fields)

    out_fields.append(Field(name="IMAGE DATA START", value=b""))
    out_fields.append(Field(name="IMAGE DATA", value=image.data))

    return out_fields
