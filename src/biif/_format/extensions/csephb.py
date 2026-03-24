"""CSEPHB DES

Notes
-----

T0_EPHEM is represented in NITF as HHMMSS.nnnnnnnnn. That is, it has nanosecond
precision. A double has 53 significand bits, approximately 9e15. There are
8.64e13 nanoseconds in a day, so we are safe to use the convenient `float` type
for this field.
"""

from __future__ import annotations

from biif._dsl.spec import (
    BcsIntEnum,
    BcsString,
    Block,
    Constant,
    DataclassRecord,
    Fixed,
    HMSeconds,
    Int,
    IntWithStrSentinel,
    IsoDate,
    ListRecord,
    Marker,
    SizedBlock,
    Uuid,
    VariableLengthList,
    VariantRecord,
)
from biif._dsl.validator import Literals, Positive, Range
from biif._format.des import register_des
from biif._format.eci import eci_spec
from biif._format.security import security_spec
from biif.models.core import Security
from biif.models.eci import ECI
from biif.models.extensions.csephb import (
    CSEPHB,
    ECF,
    EphemerisSource,
    Frame,
    InterpolationType,
    Lagrangian,
    Linear,
    NearestNeighbor,
    Quality,
)

type Array2D = list[list[float]]


csephb_spec = DataclassRecord(
    name="CSEPHB_RECORD",
    model_cls=CSEPHB,
    specs=[
        Marker("DES START CSEPHB"),
        Constant(BcsString("DE", 2), "DE"),
        Constant(BcsString("DESID", 25), "CSEPHB"),
        Constant(Int("DESVER", 2), 2),
        DataclassRecord("security", Security, security_spec),
        SizedBlock(
            Int("DESSHL", 4),
            Block([
                Uuid("UUID"),
                VariableLengthList(
                    "associated_images",
                    IntWithStrSentinel(
                        "NUMAIS", 3, Range(0, 998), sentinels=["ALL"], values=[0]
                    ),
                    Int("AISDLVL", 3, Positive()),
                ),
                VariableLengthList(
                    "associated_elements",
                    Int("NUM_ASSOC_ELEM", 3, Range(0, 276)),
                    Uuid("ASSOC_ELEM_UUID"),
                ),
                Constant(Int("RESERVEDSUBH_LEN", 4), 0),
            ]),
        ),
        Marker("DES DATA START"),
        BcsIntEnum("QUAL_FLAG_EPH", 1, enum=Quality),
        VariantRecord(
            "interpolation",
            BcsIntEnum("INTERP_TYPE_EPH", 1, enum=InterpolationType),
            {
                InterpolationType.NEAREST: DataclassRecord("", NearestNeighbor, []),
                InterpolationType.LINEAR: DataclassRecord("", Linear, []),
                InterpolationType.LAGRANGIAN: DataclassRecord(
                    "", Lagrangian, [Int("INTERP_ORDER_EPH", 1, Literals([3, 5, 7]))]
                ),
            },
        ),
        BcsIntEnum("EPHEM_FLAG", 1, enum=EphemerisSource),
        VariantRecord(
            "frame",
            BcsIntEnum("ECI_ECF_EPHEM", 1, enum=Frame),
            {
                Frame.ECI: DataclassRecord("", ECI, eci_spec),
                Frame.ECF: DataclassRecord("", ECF, []),
            },
        ),
        Fixed("DT_EPHEM", 13, Range(1e-9, 1000 - 1e-9), ndigits=9),
        IsoDate("DATE_EPHEM"),
        HMSeconds("T0_EPHEM"),
        VariableLengthList(
            "ephemerides",
            Int("NUM_EPHEM", 5, Positive()),
            ListRecord([
                Fixed("EPHEM_X", 12, ndigits=2, sign=True),
                Fixed("EPHEM_Y", 12, ndigits=2, sign=True),
                Fixed("EPHEM_Z", 12, ndigits=2, sign=True),
            ]),
        ),
        # TODO: optional velocity and acceleration
        Constant(Int("RESERVED_LEN", 9), 0),
        Marker("DES CSEPHB END"),
    ],
)


register_des("CSEPHB", 2, csephb_spec)
