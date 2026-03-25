from __future__ import annotations

from dataclasses import dataclass, fields
from io import SEEK_CUR
from typing import Any, BinaryIO, ClassVar, override

from biif._dsl.spec import (
    BcsIntEnum,
    BcsString,
    BcsStringEnum,
    BinaryInt,
    Block,
    Constant,
    DataclassRecord,
    EcsString,
    Field,
    Int,
    Marker,
    Spec,
    VariableLengthList,
)
from biif._dsl.validator import Literals, NonNegative, Positive, Range
from biif._format.security import security_spec
from biif._format.tre import read_tre_list, tre_list_to_fields
from biif.models.common import EncryptionLevel, Security
from biif.models.image import (
    BandInfo,
    Compression,
    Coords,
    ImageSegment,
    NoCoords,
    PixelJustification,
    PixelType,
)


@dataclass(frozen=True)
class DeferredImageData:
    source_fd: BinaryIO
    offset: int
    length: int

    def __len__(self) -> int:
        return self.length

    def write(self, out_fd: BinaryIO) -> None:
        current_pos = self.source_fd.tell()
        try:
            self.source_fd.seek(self.offset)
            bytes_left = self.length
            while bytes_left > 0:
                chunk = self.source_fd.read(min(bytes_left, 4096 * 1024))
                out_fd.write(chunk)
                bytes_left -= len(chunk)
        finally:
            self.source_fd.seek(current_pos)

    def read(self) -> bytes:
        current_pos = self.source_fd.tell()
        try:
            self.source_fd.seek(self.offset)
            return self.source_fd.read(self.length)
        finally:
            self.source_fd.seek(current_pos)


@dataclass
class NumBands(Spec[int]):

    MAX_NBANDS: ClassVar[int] = 9

    @override
    def read(self, fd: BinaryIO) -> int:
        nbands = Int("NBANDS", 1).read(fd)
        if nbands == 0:
            nbands = Int("XBANDS", 4).read(fd)
        return nbands

    @override
    def to_fields(self, value: int) -> list[Field]:
        if value <= self.MAX_NBANDS:
            return Int("NBANDS", 1).to_fields(value)

        return Int("NBANDS", 1).to_fields(0) + Int("XBANDS", 4).to_fields(value)


@dataclass
class CompressionSpec(Spec[Compression]):

    name: str

    @override
    def read(self, fd: BinaryIO) -> Compression:
        ic = BcsString("IC", 2).read(fd)
        kwargs = {"IC": ic}

        if ic not in {"NC", "NM"}:
            kwargs["COMRAT"] = BcsString("COMRAT", 4).read(fd)

        return Compression(**kwargs)

    @override
    def to_fields(self, value: Compression) -> list[Field]:
        out_fields = BcsString("IC", 2).to_fields(value.IC)

        if Compression.IC not in {"NC", "NM"}:
            out_fields += BcsString("COMRAT", 4).to_fields(value.COMRAT)

        return out_fields


@dataclass
class IcordsSpec(Spec[NoCoords | Coords]):

    name: str

    @override
    def read(self, fd: BinaryIO) -> NoCoords | Coords:
        ic_rep = BcsString("ICORDS", 1).read(fd)

        if ic_rep == "":
            return NoCoords()

        args = [ic_rep]
        args.extend(BcsString("", 15).read(fd) for _ in range(4))

        return Coords(*args)

    @override
    def to_fields(self, value: NoCoords | Coords) -> list[Field]:
        if isinstance(value, NoCoords):
            return BcsString("ICORDS", 1).to_fields(" ")

        icords_fields = BcsString("ICORDS", 1).to_fields(value.ICORDS)
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
    def read(self, fd: BinaryIO) -> list[list[int]]:
        nluts = Int("NLUTS", 1).read(fd)
        if nluts == 0:
            return []

        nelut = Int("NELUT", 5).read(fd)

        lut_spec = BinaryInt("LUTD", 1)
        return [[lut_spec.read(fd) for _ in range(nelut)] for _ in range(nluts)]

    @override
    def to_fields(self, value: list[list[int]]) -> list[Field]:
        nluts = len(value)
        out = Int("NLUTS", 1).to_fields(nluts)

        if nluts == 0:
            return out

        nelut = len(value[0])
        out += Int("NELUT", 5).to_fields(nelut)

        if not all(len(lut) == nelut for lut in value):
            raise ValueError

        for lut in value:
            for entry in lut:
                out += BinaryInt("LUTD", 1).to_fields(entry)

        return out


image_head_spec: list[Spec[Any]] = [
    Marker("IMAGE START"),
    Constant(BcsString("IM", 2), "IM"),
    BcsString("IID1", 10),
    BcsString("IDATIM", 14),
    BcsString("TGTID", 17),
    BcsString("IID2", 80),
    DataclassRecord("security", Security, security_spec),
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
    VariableLengthList(
        "comments",
        Int("NICOM", 1, NonNegative()),
        EcsString("ICOM", 80),
    ),
    CompressionSpec("compression"),
    VariableLengthList(
        "bands",
        NumBands(),
        DataclassRecord(
            "",
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

    header = Block(image_head_spec).read(fd)

    udid = read_tre_list(fd, "UDIDL", "UDOFL")
    ixshd = read_tre_list(fd, "IXSHDL", "IXSOFL")

    if fd.tell() != start_pos + lish:
        msg = "Image segment header has wrong length"
        raise RuntimeError(msg)

    data_proxy = DeferredImageData(source_fd=fd, offset=fd.tell(), length=li)
    fd.seek(li, SEEK_CUR)

    valid_fields = {f.name for f in fields(ImageSegment)}
    valid_keys = header.keys() & valid_fields
    kwargs = {k: header[k] for k in valid_keys}
    kwargs["UDID"] = udid
    kwargs["IXSHD"] = ixshd

    return ImageSegment(**kwargs, data=data_proxy)


def image_to_fields(image: ImageSegment) -> list[Field]:
    out_fields = Block(image_head_spec).fields_from(vars(image))

    udid_fields = tre_list_to_fields(image.UDID, "UDIDL", "UDOFL")
    out_fields.extend(udid_fields)

    ixshd_fields = tre_list_to_fields(image.IXSHD, "IXSHDL", "IXSOFL")
    out_fields.extend(ixshd_fields)

    out_fields.append(Field(name="IMAGE DATA START", value=b""))
    out_fields.append(Field(name="IMAGE DATA", value=image.data))

    return out_fields
