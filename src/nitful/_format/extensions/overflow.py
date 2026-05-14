from dataclasses import dataclass
from typing import BinaryIO, override

from nitful._format.des import register_des
from nitful._format.shared import Segment, security_spec
from nitful._format.tre import read_tre, tre_to_fields
from nitful.core.common import TRE
from nitful.dsl.rules import (
    BcsString,
    BcsStringEnum,
    Combinator,
    Constant,
    EmitContext,
    Int,
    Item,
    ParseContext,
)
from nitful.dsl.validators import nonnegative
from nitful.extensions.overflow import OverflowSource, TreOverflow


@dataclass
class ContextBoundedTreList(Combinator[list[TRE]]):
    """Read TREs until a byte length defined in the context is reached."""

    length_key: str

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> list[TRE]:
        target_length = ctx[self.length_key]
        end_pos = fd.tell() + target_length
        tres: list[TRE] = []

        while fd.tell() < end_pos:
            tres.append(read_tre(fd, ctx))

        return tres

    @override
    def _emit(self, value: list[TRE], *, ctx: EmitContext) -> list[Item]:
        fields: list[Item] = []
        for tre in value:
            fields.extend(tre_to_fields(tre, ctx))
        return fields


tre_overflow = Segment(
    TreOverflow,
    subheader=[
        Constant(BcsString("DE", 2), "DE"),
        Constant(BcsString("DESID", 25), "TRE_OVERFLOW"),
        Constant(Int("DESVER", 2), 1),
        security_spec("DE"),
        BcsStringEnum("DESOFLW", 6, enum=OverflowSource),
        Int("DESITEM", 3, nonnegative),
        Constant(Int("DESSHL", 4), 0),
    ],
    data=[
        ContextBoundedTreList(name="DESDATA", length_key="_CURRENT_DES_DATA_LEN"),
    ],
)

register_des("TRE_OVERFLOW", 1, tre_overflow)
