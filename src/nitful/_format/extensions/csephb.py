"""CSEPHB DES

Notes
-----

T0_EPHEM is represented in NITF as HHMMSS.nnnnnnnnn. That is, it has nanosecond
precision. A double has 53 significand bits, approximately 9e15. There are
8.64e13 nanoseconds in a day, so we are safe to use the convenient `float` type
for this field.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import BinaryIO, ClassVar, override

from nitful._format.des import register_des
from nitful._format.shared import ReservedExtensions, Segment, eci_spec, security_spec
from nitful.core.common import ECI, ECIv1
from nitful.dsl.rules import (
    BcsIntEnum,
    BcsString,
    Bool,
    Case,
    Combinator,
    Constant,
    EmitContext,
    FixedFloat,
    HMSeconds,
    Int,
    IsoDate,
    Item,
    Override,
    ParseContext,
    PrefixedList,
    Rule,
    SizedBlock,
    Struct,
    Switch,
    Uuid,
    Variant,
    Vector,
)
from nitful.dsl.validators import (
    in_range,
    nonnegative,
    one_of,
    positive,
)
from nitful.extensions.csephb import (
    CSEPHB,
    ECF,
    EphemerisSource,
    Kinematics,
    Lagrangian,
    Linear,
    NearestNeighbor,
    Quality,
)

type Array2D = list[list[float]]


@dataclass
class RFA1(Combinator[Kinematics]):
    """Handle the interleaved velocity/acceleration loop of CSEPHB RFA 1."""

    name: str = field(default="RFA1", init=False)

    b_spec: ClassVar[Rule[bool]] = Bool("ACCEL_PROVIDED", true=b"Y", false=b"N")

    v_spec: ClassVar[Rule[list[float]]] = Vector([
        FixedFloat("VEL_X", 12, ndigits=2, sign=True),
        FixedFloat("VEL_Y", 12, ndigits=2, sign=True),
        FixedFloat("VEL_Z", 12, ndigits=2, sign=True),
    ])

    a_spec: ClassVar[Rule[list[float]]] = Vector([
        FixedFloat("ACCEL_X", 12, ndigits=2, sign=True),
        FixedFloat("ACCEL_Y", 12, ndigits=2, sign=True),
        FixedFloat("ACCEL_Z", 12, ndigits=2, sign=True),
    ])

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> Kinematics:
        accel_provided = self.b_spec.parse(fd, ctx)
        num_ephem = ctx["NUM_EPHEM"]

        velocities: list[list[float]] = []
        accelerations: list[list[float]] = []

        for _ in ctx.iterate(range(num_ephem)):
            velocities.append(self.v_spec.parse(fd, ctx))
            if accel_provided:
                accelerations.append(self.a_spec.parse(fd, ctx))

        return Kinematics(velocities, accelerations if accel_provided else None)

    @override
    def _emit(self, value: Kinematics, *, ctx: EmitContext) -> list[Item]:
        accel_provided = value.accelerations is not None
        fields = self.b_spec.to_fields(accel_provided, ctx)

        for i in ctx.iterate(range(len(value.velocities))):
            fields.extend(self.v_spec.to_fields(value.velocities[i], ctx))
            if value.accelerations:
                fields.extend(self.a_spec.to_fields(value.accelerations[i], ctx))

        return fields


class Frame(IntEnum):
    ECI = 0
    ECF = 1


class InterpolationType(IntEnum):
    NEAREST = 0
    LINEAR = 1
    LAGRANGIAN = 2


csephb = Segment(
    CSEPHB,
    subheader=[
        Constant(BcsString("DE", 2), "DE"),
        Constant(BcsString("DESID", 25), "CSEPHB"),
        Int("DESVER", 2),
        security_spec,
        SizedBlock(
            Int("DESSHL", 4),
            [
                Uuid("UUID"),
                PrefixedList(
                    name="images",
                    count=Override(Int("NUMAIS", 3, in_range(0, 998)), {b"ALL": 0}),
                    body=Int("AISDLVL", 3, positive),
                ),
                PrefixedList(
                    name="elements",
                    count=Int("NUM_ASSOC_ELEM", 3, in_range(0, 276)),
                    body=Uuid("ASSOC_ELEM_UUID"),
                ),
                Constant(Int("RESERVEDSUBH_LEN", 4), 0),
            ],
        ),
    ],
    data=[
        BcsIntEnum("QUAL_FLAG_EPH", 1, enum=Quality),
        Variant(
            name="interpolation",
            tag_rule=BcsIntEnum("INTERP_TYPE_EPH", 1, enum=InterpolationType),
            cases=[
                Case(
                    InterpolationType.NEAREST,
                    NearestNeighbor,
                    Struct(NearestNeighbor, []),
                ),
                Case(
                    InterpolationType.LINEAR,
                    Linear,
                    Struct(Linear, []),
                ),
                Case(
                    InterpolationType.LAGRANGIAN,
                    Lagrangian,
                    Struct(Lagrangian, [Int("INTERP_ORDER_EPH", 1, one_of(3, 5, 7))]),
                ),
            ],
        ),
        BcsIntEnum("EPHEM_FLAG", 1, enum=EphemerisSource),
        Variant(
            name="frame",
            tag_rule=BcsIntEnum("ECI_ECF_EPHEM", 1, enum=Frame),
            cases=[
                Case(Frame.ECF, ECF, Struct(ECF, [])),
                Case(
                    Frame.ECI,
                    (ECI, ECIv1),
                    Switch(
                        get_tag=lambda ctx: ctx["DESVER"],
                        cases={1: Struct(ECIv1, []), 2: eci_spec},
                    ),
                ),
            ],
        ),
        FixedFloat("DT_EPHEM", 13, in_range(1e-9, 1000 - 1e-9), ndigits=9),
        IsoDate("DATE_EPHEM"),
        HMSeconds("T0_EPHEM", 16),
        PrefixedList(
            name="ephemerides",
            count=Int("NUM_EPHEM", 5, positive),
            body=Vector([
                FixedFloat("EPHEM_X", 12, ndigits=2, sign=True),
                FixedFloat("EPHEM_Y", 12, ndigits=2, sign=True),
                FixedFloat("EPHEM_Z", 12, ndigits=2, sign=True),
            ]),
        ),
        ReservedExtensions(
            Int("RESERVED_LEN", 9, nonnegative),
            Int("MASK_LEN", 2, positive),
            cases={
                1: RFA1(),
            },
        ),
    ],
)


register_des("CSEPHB", 1, csephb)
register_des("CSEPHB", 2, csephb)
