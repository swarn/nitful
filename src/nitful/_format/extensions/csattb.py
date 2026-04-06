from enum import IntEnum

from nitful._format.des import register_des
from nitful._format.shared import ReservedExtensions, Segment, eci_spec, security_spec
from nitful.core.common import ECI, ECIv1
from nitful.dsl.rules import (
    BcsIntEnum,
    BcsString,
    Case,
    Constant,
    FixedFloat,
    HMSeconds,
    Int,
    IsoDate,
    Override,
    PrefixedList,
    SizedBlock,
    Struct,
    Switch,
    Uuid,
    Variant,
    Vector,
)
from nitful.dsl.validators import in_range, nonnegative, one_of, positive
from nitful.extensions.csattb import (
    CSATTB,
    ECF,
    AttitudeType,
    Lagrangian,
    Linear,
    NearestNeighbor,
    Quality,
    Spherical,
)


class InterpolationType(IntEnum):
    NEAREST = 0
    LINEAR = 1
    LAGRANGIAN = 2
    SPHERICAL = 3


class Frame(IntEnum):
    ECI = 0
    ECF = 1


csattb = Segment(
    CSATTB,
    subheader=[
        Constant(BcsString("DE", 2), "DE"),
        Constant(BcsString("DESID", 25), "CSATTB"),
        Int("DESVER", 2, one_of(1, 2)),
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
        BcsIntEnum("QUAL_FLAG_ATT", 1, enum=Quality),
        Variant(
            name="interpolation",
            tag_rule=BcsIntEnum("INTERP_TYPE_ATT", 1, enum=InterpolationType),
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
                    Struct(Lagrangian, [Int("INTERP_ORDER_ATT", 1, one_of(3, 5, 7))]),
                ),
                Case(
                    InterpolationType.SPHERICAL,
                    Spherical,
                    Struct(Spherical, [Int("INTERP_ORDER_ATT", 1, one_of(1, 3))]),
                ),
            ],
        ),
        BcsIntEnum("ATT_TYPE", 1, enum=AttitudeType),
        Variant(
            name="frame",
            tag_rule=BcsIntEnum("ECI_ECF_ATT", 1, enum=Frame),
            cases=[
                Case(Frame.ECF, ECF, Struct(ECF, [])),
                Case(
                    Frame.ECI,
                    (ECIv1, ECI),
                    Switch(
                        get_tag=lambda ctx: ctx["DESVER"],
                        cases={1: Struct(ECIv1, []), 2: eci_spec},
                    ),
                ),
            ],
        ),
        FixedFloat("DT_ATT", 13, in_range(1e-9, 1000 - 1e-9), ndigits=9),
        IsoDate("DATE_ATT"),
        HMSeconds("T0_ATT", 16),
        PrefixedList(
            name="quaternions",
            count=Int("NUM_ATT", 5, positive),
            body=Vector([
                FixedFloat("Q1", 18, in_range(-1.0, 1.0), ndigits=15, sign=True),
                FixedFloat("Q2", 18, in_range(-1.0, 1.0), ndigits=15, sign=True),
                FixedFloat("Q3", 18, in_range(-1.0, 1.0), ndigits=15, sign=True),
                FixedFloat("Q4", 18, in_range(-1.0, 1.0), ndigits=15, sign=True),
            ]),
        ),
        ReservedExtensions(
            Int("RESERVED_LEN", 9, nonnegative),
            Int("MASK_LEN", 2, nonnegative),
            cases={},
        ),
    ],
)


register_des("CSATTB", 1, csattb)
register_des("CSATTB", 2, csattb)
