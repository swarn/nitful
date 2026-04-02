from enum import IntEnum

from nitful._dsl.rules import (
    BcsIntEnum,
    BcsString,
    Constant,
    Fixed,
    HMSeconds,
    Int,
    IsoDate,
    Override,
    PrefixedList,
    ReservedExtensions,
    Segment,
    SizedBlock,
    Struct,
    Switch,
    Uuid,
    Variant,
    Vector,
)
from nitful._dsl.validator import Literals, NonNegative, Positive, Range
from nitful._format.des import register_des
from nitful._format.eci import eci_spec
from nitful._format.security import security_spec
from nitful.core.eci import ECI, ECIv1
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
        Int("DESVER", 2, Literals([1, 2])),
        security_spec,
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
    ],
    data=[
        BcsIntEnum("QUAL_FLAG_ATT", 1, enum=Quality),
        Variant(
            name="interpolation",
            tag_rule=BcsIntEnum("INTERP_TYPE_ATT", 1, enum=InterpolationType),
            cases={
                InterpolationType.NEAREST: Struct(NearestNeighbor, []),
                InterpolationType.LINEAR: Struct(Linear, []),
                InterpolationType.LAGRANGIAN: Struct(
                    Lagrangian, [Int("INTERP_ORDER_ATT", 1, Literals([3, 5, 7]))]
                ),
                InterpolationType.SPHERICAL: Struct(
                    Spherical, [Int("INTERP_ORDER_ATT", 1, Literals([1, 3]))]
                ),
            },
        ),
        BcsIntEnum("ATT_TYPE", 1, enum=AttitudeType),
        Variant(
            name="frame",
            tag_rule=BcsIntEnum("ECI_ECF_ATT", 1, enum=Frame),
            cases={
                Frame.ECF: Struct(ECF, []),
                Frame.ECI: Switch(
                    get_tag=lambda ctx: ctx["DESVER"],
                    cases={
                        1: Struct(ECIv1, []),
                        2: Struct(ECI, eci_spec),
                    },
                ),
            },
        ),
        Fixed("DT_ATT", 13, Range(1e-9, 1000 - 1e-9), ndigits=9),
        IsoDate("DATE_ATT"),
        HMSeconds("T0_ATT"),
        PrefixedList(
            name="quaternions",
            count=Int("NUM_ATT", 5, Positive()),
            body=Vector([
                Fixed("Q1", 18, Range(-1, 1), ndigits=15, sign=True),
                Fixed("Q2", 18, Range(-1, 1), ndigits=15, sign=True),
                Fixed("Q3", 18, Range(-1, 1), ndigits=15, sign=True),
                Fixed("Q4", 18, Range(-1, 1), ndigits=15, sign=True),
            ]),
        ),
        ReservedExtensions(
            Int("RESERVED_LEN", 9, NonNegative()),
            Int("MASK_LEN", 2, Positive()),
            cases={},
        ),
    ],
)


register_des("CSATTB", 1, csattb)
register_des("CSATTB", 2, csattb)
