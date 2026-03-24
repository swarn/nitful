from __future__ import annotations

from dataclasses import dataclass, fields
from os import SEEK_CUR
from typing import BinaryIO

from biif._dsl.spec import (
    BcsIntEnum,
    BcsString,
    Block,
    ConcatDatetime,
    Constant,
    DataclassRecord,
    EcsString,
    Field,
    HexColor,
    Int,
    Spec,
    VariableLengthList,
)
from biif._dsl.validator import Literals, NonNegative, NotBlank
from biif._format.des import des_to_fields, read_des
from biif._format.image import image_to_fields, read_image_segment
from biif._format.security import security_spec
from biif._format.tre import read_tre, tre_to_fields
from biif.models.core import BIIF, EncryptionLevel, Security


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


header_spec: list[Spec] = [
    BcsString("FHDR", 4, Literals(["NITF", "NSIF"])),
    BcsString("FVER", 5, Literals(["01.01", "02.10"])),
    Int("CLEVEL", 2, Literals([3, 5, 6, 7, 9, 51, 54, 57])),
    BcsString("STYPE", 4, Literals(["BF01"])),
    BcsString("OSTAID", 10, NotBlank()),
    ConcatDatetime("FDT"),
    EcsString("FTITLE", 80),
    DataclassRecord("security", Security, security_spec),
    Int("FSCOP", 5, NonNegative()),
    Int("FSCPYS", 5, NonNegative()),
    BcsIntEnum("ENCRYP", 1, enum=EncryptionLevel),
    HexColor("FBKGC"),
    EcsString("ONAME", 24),
    EcsString("OPHONE", 18),
    Int("FL", 12),
    Int("HL", 6),
    VariableLengthList(
        "image_segment_info",
        Int("NUMI", 3),
        DataclassRecord("", ImageSegmentInfo, [Int("LISH", 6), Int("LI", 10)]),
    ),
    VariableLengthList(
        "graphic_segment_info",
        Int("NUMS", 3),
        DataclassRecord("", GraphicSegmentInfo, [Int("LSSH", 4), Int("LS", 6)]),
    ),
    Constant(Int("NUMX", 3), 0),
    VariableLengthList(
        "text_segment_info",
        Int("NUMT", 3),
        DataclassRecord("", TextSegmentInfo, [Int("LTSH", 4), Int("LT", 5)]),
    ),
    VariableLengthList(
        "data_segment_info",
        Int("NUMDES", 3),
        DataclassRecord("", DataSegmentInfo, [Int("LDSH", 4), Int("LD", 9)]),
    ),
    VariableLengthList(
        "reserved_segment_info",
        Int("NUMRES", 3),
        DataclassRecord("", ReservedSegmentInfo, [Int("LRESH", 4), Int("LRE", 7)]),
    ),
]


def read_file(fd: BinaryIO) -> BIIF:
    header = Block(header_spec).read(fd)

    # Read any TREs in the User Defined Header Data.
    udhd = []
    udhdl = Int("UDHDL", 5).read(fd)
    if udhdl > 0:
        udhofl = Int("UDHOFL", 3).read(fd)
        if udhofl > 0:
            raise NotImplementedError()

        udhd_end = fd.tell() + (udhdl - 3)
        while fd.tell() < udhd_end:
            udhd.append(read_tre(fd))

    # Read any TREs in the Extended Header Data
    xhd = []
    xhdl = Int("XHDL", 5).read(fd)
    if xhdl > 0:
        xhdlofl = Int("XHDLOFL", 3).read(fd)
        if xhdlofl > 0:
            raise NotImplementedError()

        xhd_end = fd.tell() + (xhdl - 3)
        while fd.tell() < xhd_end:
            xhd.append(read_tre(fd))

    # Read the image segments. Each segment includes all relevant size
    # information, so the sizes in the file header are mostly useful for
    # skipping past segments, or for verifying correct reads.
    image_segments = []
    for info in header["image_segment_info"]:
        image_segments.append(read_image_segment(fd, lish=info.LISH, li=info.LI))

    # Not supporting graphics yet, so simply skip those bytes.
    for info in header["graphic_segment_info"]:
        graphic_size = info.LSSH + info.LS
        fd.seek(graphic_size, SEEK_CUR)

    # Not supporting text segments yet.
    for info in header["text_segment_info"]:
        text_size = info.LTSH + info.LT
        fd.seek(text_size, SEEK_CUR)

    # Read the data segments. Again, each segment includes size info. The
    # factory function generates the correct DES type.
    data_segments = []
    for info in header["data_segment_info"]:
        des = read_des(fd, info.LDSH, info.LD)
        data_segments.append(des)

    for info in header["reserved_segment_info"]:
        segment_size = info.LRESH + info.LRE
        fd.seek(segment_size, SEEK_CUR)

    # TODO: fd should be empty at this point, check that.

    valid_fields = {f.name for f in fields(BIIF)}
    valid_keys = header.keys() & valid_fields

    kwargs = {k: header[k] for k in valid_keys}
    kwargs["UDHD"] = udhd
    kwargs["XHD"] = xhd
    kwargs["image_segments"] = image_segments
    kwargs["data_segments"] = data_segments

    return BIIF(**kwargs)


def find_field(fields: list[Field], name: str):
    for i, field in enumerate(fields):
        if field.name == name:
            return i
    raise ValueError(f"Field {name} not found.")


def field_size(fields: list[Field]) -> int:
    return sum(len(f.value) for f in fields)


def to_fields(biif: BIIF) -> list[Field]:

    all_image_fields: list[Field] = []
    image_infos: list[ImageSegmentInfo] = []

    for img in biif.image_segments:
        image_fields = image_to_fields(img)
        data_idx = find_field(image_fields, "IMAGE DATA START")
        len_hdr = field_size(image_fields[:data_idx])
        len_data = field_size(image_fields[data_idx:])
        info = ImageSegmentInfo(LISH=len_hdr, LI=len_data)
        image_infos.append(info)
        all_image_fields.extend(image_fields)

    all_data_fields: list[Field] = []
    data_infos: list[DataSegmentInfo] = []

    for des in biif.data_segments:
        # The des_to_fields function looks up the spec for the
        # DES type and uses it to create the fields.
        data_fields = des_to_fields(des)
        data_idx = find_field(data_fields, "DES DATA START")
        len_hdr = field_size(data_fields[:data_idx])
        len_data = field_size(data_fields[data_idx:])
        info = DataSegmentInfo(LDSH=len_hdr, LD=len_data)
        data_infos.append(info)
        all_data_fields.extend(data_fields)

    # Generate the header fields with dummy values for lengths.
    header_kwargs = vars(biif).copy()
    header_kwargs["image_segment_info"] = image_infos
    header_kwargs["data_segment_info"] = data_infos
    header_kwargs["graphic_segment_info"] = []
    header_kwargs["text_segment_info"] = []
    header_kwargs["reserved_segment_info"] = []
    header_kwargs["FL"] = 0
    header_kwargs["HL"] = 0
    header_fields = Block(header_spec).fields_from(header_kwargs)

    # Add the UDHD TREs to the header.
    udhd_fields = []
    for tre in biif.UDHD:
        udhd_fields.extend(tre_to_fields(tre))

    if udhd_fields:
        udhd_len = field_size(udhd_fields) + 3
        header_fields.extend(Int("UDHDL", 5).to_fields(udhd_len))
        header_fields.extend(Constant(Int("UDHOFL", 3), 0).to_fields())
        header_fields.extend(udhd_fields)
    else:
        header_fields.extend(Int("UDHDL", 5).to_fields(0))

    # Add the XHD TREs to the header.
    xhd_fields = []
    for tre in biif.XHD:
        xhd_fields.extend(tre_to_fields(tre))

    if xhd_fields:
        xhdl_len = field_size(xhd_fields) + 3
        header_fields.extend(Int("XHDL", 5).to_fields(xhdl_len))
        header_fields.extend(Constant(Int("XHDLOFL", 3), 0).to_fields())
        header_fields.extend(xhd_fields)
    else:
        header_fields.extend(Int("XHDL", 5).to_fields(0))

    # Patch the header length.
    header_len = field_size(header_fields)
    hl_idx = find_field(header_fields, "HL")
    header_fields[hl_idx] = Int("HL", 6).to_fields(header_len)[0]

    all_fields = (
        header_fields
        + all_image_fields
        # + all_graphic_fields
        # + all_text_fields
        + all_data_fields
        # + all_reserved_fields
    )

    # Patch the file length.
    all_len = field_size(all_fields)
    fl_idx = find_field(all_fields, "FL")
    all_fields[fl_idx] = Int("FL", 12).to_fields(all_len)[0]

    return all_fields
