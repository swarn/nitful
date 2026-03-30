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
from typing import Any, BinaryIO, ClassVar, override

from nitful._dsl.spec import (
    BcsIntEnum,
    BcsString,
    Bool,
    Constant,
    DataclassRecord,
    EmitContext,
    Field,
    Fixed,
    HMSeconds,
    Int,
    IsoDate,
    Marker,
    Override,
    ParseContext,
    PrefixedList,
    ReservedExtensions,
    RuleSpec,
    SizedBlock,
    Spec,
    Uuid,
    VariantRecord,
    Vector,
)
from nitful._dsl.validator import Literals, Positive, Range
from nitful._format.des import register_des
from nitful._format.eci import eci_spec
from nitful._format.security import security_spec
from nitful.core.common import Security
from nitful.core.eci import ECI
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


def _csephb_spec() -> list[Spec[Any]]:
    return [
        Marker("DES START CSEPHB"),
        Constant(BcsString("DE", 2), "DE"),
        Constant(BcsString("DESID", 25), "CSEPHB"),
        Constant(Int("DESVER", 2), 2),
        DataclassRecord(Security, security_spec, name="security"),
        SizedBlock(
            Int("DESSHL", 4),
            [
                Uuid("UUID"),
                PrefixedList(
                    name="images",
                    count=Override(Int("NUMAIS", 3, Range(0, 998)), {b"ALL": 0}),
                    body=Int("AISDLVL", 3, Positive()),
                ),
                PrefixedList(
                    name="elements",
                    count=Int("NUM_ASSOC_ELEM", 3, Range(0, 276)),
                    body=Uuid("ASSOC_ELEM_UUID"),
                ),
                Constant(Int("RESERVEDSUBH_LEN", 4), 0),
            ],
        ),
        Marker("DES DATA START"),
        BcsIntEnum("QUAL_FLAG_EPH", 1, enum=Quality),
        VariantRecord(
            name="interpolation",
            tag_spec=BcsIntEnum("INTERP_TYPE_EPH", 1, enum=InterpolationType),
            cases={
                InterpolationType.NEAREST: DataclassRecord(NearestNeighbor, []),
                InterpolationType.LINEAR: DataclassRecord(Linear, []),
                InterpolationType.LAGRANGIAN: DataclassRecord(
                    Lagrangian, [Int("INTERP_ORDER_EPH", 1, Literals([3, 5, 7]))]
                ),
            },
        ),
        BcsIntEnum("EPHEM_FLAG", 1, enum=EphemerisSource),
        VariantRecord(
            name="frame",
            tag_spec=BcsIntEnum("ECI_ECF_EPHEM", 1, enum=Frame),
            cases={
                Frame.ECI: DataclassRecord(ECI, eci_spec),
                Frame.ECF: DataclassRecord(ECF, []),
            },
        ),
        Fixed("DT_EPHEM", 13, Range(1e-9, 1000 - 1e-9), ndigits=9),
        IsoDate("DATE_EPHEM"),
        HMSeconds("T0_EPHEM"),
        PrefixedList(
            name="ephemerides",
            count=Int("NUM_EPHEM", 5, Positive()),
            body=Vector([
                Fixed("EPHEM_X", 12, ndigits=2, sign=True),
                Fixed("EPHEM_Y", 12, ndigits=2, sign=True),
                Fixed("EPHEM_Z", 12, ndigits=2, sign=True),
            ]),
        ),
        ReservedExtensions(
            cases={
                1: RFA1(),
            },
        ),
        Marker("DES CSEPHB END"),
    ]


class Frame(IntEnum):
    ECI = 0
    ECF = 1


class InterpolationType(IntEnum):
    NEAREST = 0
    LINEAR = 1
    LAGRANGIAN = 2


@dataclass
class RFA1(RuleSpec[Kinematics]):
    """Handle the interleaved velocity/acceleration loop of CSEPHB RFA 1."""

    name: str = field(default="RFA1", init=False)

    b_spec: ClassVar[Spec[bool]] = Bool("ACCEL_PROVIDED", true=b"Y", false=b"N")

    v_spec: ClassVar[Spec[list[float]]] = Vector([
        Fixed("VEL_X", 12, ndigits=2, sign=True),
        Fixed("VEL_Y", 12, ndigits=2, sign=True),
        Fixed("VEL_Z", 12, ndigits=2, sign=True),
    ])

    a_spec: ClassVar[Spec[list[float]]] = Vector([
        Fixed("ACCEL_X", 12, ndigits=2, sign=True),
        Fixed("ACCEL_Y", 12, ndigits=2, sign=True),
        Fixed("ACCEL_Z", 12, ndigits=2, sign=True),
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
    def _emit(self, value: Kinematics, *, ctx: EmitContext) -> list[Field]:
        accel_provided = value.accelerations is not None
        fields = self.b_spec.to_fields(accel_provided, ctx)

        for i in ctx.iterate(range(len(value.velocities))):
            fields.extend(self.v_spec.to_fields(value.velocities[i], ctx))
            if value.accelerations:
                fields.extend(self.a_spec.to_fields(value.accelerations[i], ctx))

        return fields


register_des("CSEPHB", 2, DataclassRecord(CSEPHB, _csephb_spec()))
