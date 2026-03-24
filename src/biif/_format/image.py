from __future__ import annotations

from dataclasses import dataclass, fields
from io import SEEK_CUR
from typing import BinaryIO, override

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
from biif._format.tre import read_tre, tre_to_fields
from biif.models.core import EncryptionLevel, Security
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

    @override
    def read(self, fd: BinaryIO) -> int:
        nbands = Int("NBANDS", 1).read(fd)
        if nbands == 0:
            nbands = Int("XBANDS", 4).read(fd)
        return nbands

    @override
    def to_fields(self, value: int) -> list[Field]:
        if value < 9:
            return Int("NBANDS", 1).to_fields(value)

        return Int("NBANDS", 1).to_fields(0) + Int("XBANDS", 4).to_fields(value)


@dataclass
class CompressionSpec(Spec[Compression]):

    name: str

    @override
    def read(self, fd: BinaryIO) -> Compression:
        ic = BcsString("IC", 2).read(fd)
        kwargs = {"IC": ic}

        if ic not in ["NC", "NM"]:
            kwargs["COMRAT"] = BcsString("COMRAT", 4).read(fd)

        return Compression(**kwargs)

    @override
    def to_fields(self, value: Compression) -> list[Field]:
        out_fields = BcsString("IC", 2).to_fields(value.IC)

        if Compression.IC not in ["NC", "NM"]:
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

        for _ in range(4):
            args.append(BcsString("", 15).read(fd))

        return Coords(*args)

    @override
    def to_fields(self, value: NoCoords | Coords) -> list[Field]:
        if isinstance(value, NoCoords):
            return BcsString("ICORDS", 1).to_fields(" ")

        icords_fields = BcsString("ICORDS", 1).to_fields(value.ICORDS)

        igeolo_bytes = []
        for c in value.upperleft, value.upperright, value.lowerright, value.lowerleft:
            igeolo_bytes.append(BcsString("", 15).encode(c))

        return icords_fields + [Field("IGEOLO", b"".join(igeolo_bytes))]


@dataclass
class LutsSpec(Spec[list[list[int]]]):

    name: str

    @override
    def read(self, fd: BinaryIO) -> list[list[int]]:
        nluts = Int("NLUTS", 1).read(fd)
        if nluts == 0:
            return []

        nelut = Int("NELUT", 5).read(fd)

        luts = []
        for _ in range(nluts):
            luts.append([BinaryInt("LUTD", 1).read(fd) for _ in range(nelut)])

        return luts

    @override
    def to_fields(self, value: list[list[int]]) -> list[Field]:
        nluts = len(value)
        out = Int("NLUTS", 1).to_fields(nluts)

        if nluts == 0:
            return out

        nelut = len(value[0])
        out += Int("NELUT", 5).to_fields(nelut)

        if not all(len(lut) == nelut for lut in value):
            raise ValueError()

        for lut in value:
            for entry in lut:
                out += BinaryInt("LUTD", 1).to_fields(entry)

        return out


image_head_spec = [
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

    # Read any TREs in the User Defined Image Data.
    udid = []
    udidl = Int("UDIDL", 5).read(fd)
    if udidl > 0:
        udofl = Int("UDOFL", 3).read(fd)
        if udofl > 0:
            raise NotImplementedError()

        udid_end = fd.tell() + (udidl - 3)
        while fd.tell() < udid_end:
            udid.append(read_tre(fd))

    # Read any TREs in the Extended Header Data
    ixshd = []
    ixshdl = Int("IXSHDL", 5).read(fd)
    if ixshdl > 0:
        ixsofl = Int("IXSOFL", 3).read(fd)
        if ixsofl > 0:
            raise NotImplementedError()

        ixshd_end = fd.tell() + (ixshdl - 3)
        while fd.tell() < ixshd_end:
            ixshd.append(read_tre(fd))

    if fd.tell() != start_pos + lish:
        raise RuntimeError("Image segment header has wrong length")

    data_proxy = DeferredImageData(source_fd=fd, offset=fd.tell(), length=li)
    fd.seek(li, SEEK_CUR)

    valid_fields = {f.name for f in fields(ImageSegment)}
    valid_keys = header.keys() & valid_fields
    kwargs = {k: header[k] for k in valid_keys}
    kwargs["UDID"] = udid
    kwargs["IXSHD"] = ixshd

    return ImageSegment(**kwargs, data=data_proxy)


def field_size(fields: list[Field]) -> int:
    return sum(len(f.value) for f in fields)


def image_to_fields(image: ImageSegment) -> list[Field]:

    out_fields = Block(image_head_spec).fields_from(vars(image))

    udid_fields = []
    for tre in image.UDID:
        udid_fields.extend(tre_to_fields(tre))

    if udid_fields:
        udidl = field_size(udid_fields) + 3
        out_fields.extend(Int("UDIDL", 5).to_fields(udidl))
        out_fields.extend(Int("UDOFL", 3).to_fields(0))
        out_fields.extend(udid_fields)
    else:
        out_fields.extend(Int("UDIDL", 5).to_fields(0))

    ixshd_fields = []
    for tre in image.IXSHD:
        ixshd_fields.extend(tre_to_fields(tre))

    if ixshd_fields:
        ixshdl = field_size(ixshd_fields) + 3
        out_fields.extend(Int("IXSHDL", 5).to_fields(ixshdl))
        out_fields.extend(Int("IXSOFL", 3).to_fields(0))
        out_fields.extend(ixshd_fields)
    else:
        out_fields.extend(Int("IXSHDL", 5).to_fields(0))

    out_fields.append(Field(name="IMAGE DATA START", value=b""))
    out_fields.append(Field(name="IMAGE DATA", value=image.data))

    return out_fields
