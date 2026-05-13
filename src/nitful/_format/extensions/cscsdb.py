from collections.abc import Callable
from enum import IntEnum

from nitful._format.des import register_des
from nitful._format.shared import ReservedExtensions, Segment, security_spec
from nitful.dsl.rules import (
    BcsIntEnum,
    BcsString,
    Bool,
    Case,
    Computed,
    Constant,
    Context,
    EmitContext,
    ExpFloat,
    FixedFloat,
    HMSeconds,
    Int,
    IsoDate,
    Optional,
    Override,
    PrefixedArray,
    PrefixedList,
    SizedBlock,
    SizedList,
    Struct,
    Switch,
    Uuid,
    Variant,
    Vector,
)
from nitful.dsl.validators import in_range, nonnegative, positive
from nitful.extensions.cscsdb import (
    CSCSDB,
    BasicPayloadSpdcf,
    BasicPlatformSpdcf,
    BasicSub,
    CalApId,
    ConstituentSpdcf,
    CoreSet,
    CPGroup,
    CsmFourParam,
    DampedCosine,
    DirectCovariance,
    DirectCovariance0,
    InterpType,
    IoCalibration,
    IoCpg,
    ParameterId,
    PiecewiseLinear,
    PlSegment,
    PostPayloadSpdcf,
    PostPlatformSpdcf,
    PostSensorSpdcf,
    PostSub,
    ReferenceFrame,
    Spdcf,
    TsCalibration,
    TsGroup1,
    TsGroup2,
    TsGroup3,
    TsGroup4,
    TsGroup5,
    UnmodeledError,
)


def num_covar_elems(name: str) -> Callable[[Context], int]:
    """Get the number of elements in an upper triangular covariance matrix.

    Where `name` is the name of the object in contex with parameters.
    """

    def _covar_len(ctx: Context) -> int:
        n = len(ctx[name])
        return (n * (n + 1)) // 2

    return _covar_len


direct_cover: Variant[int, DirectCovariance] = Variant(
    tag_rule=Int("DC_TYPE", 1, in_range(0, 9)),
    cases=[
        Case(
            0,
            DirectCovariance0,
            Struct(
                DirectCovariance0,
                [
                    PrefixedList(
                        name="adjustments",
                        count=Int("NUM_PARA", 4, positive),
                        body=ExpFloat("ADJ", 21, edigits=2),
                    ),
                    SizedList(
                        name="covariances",
                        count=num_covar_elems("adjustments"),
                        body=ExpFloat("ERRCOV_C4", 21, edigits=2),
                    ),
                ],
            ),
        )
    ],
)


csm_four_param = Struct(
    CsmFourParam,
    [
        FixedFloat("FP_A", 8, in_range(0.000001, 1.0), ndigits=6),
        FixedFloat("FP_ALPHA", 8, in_range(0.0, 1.0), ndigits=6),
        FixedFloat("FP_BETA", 9, in_range(0.0, 10.0), ndigits=6),
        ExpFloat("FP_T", 21, in_range(1e-06, 9.99999999999999e99), edigits=2),
    ],
)


piecewise_linear = Struct(
    PiecewiseLinear,
    [
        PrefixedList(
            name="segments",
            count=Int("NUM_SEGS", 2, in_range(2, 10)),
            body=Struct(
                PlSegment,
                [
                    FixedFloat("PL_MAX_COR", 8, in_range(0.0, 1.0), ndigits=6),
                    ExpFloat("PL_TAU_MAX_COR", 21, nonnegative, edigits=2),
                ],
            ),
        )
    ],
)


damped_cosine = Struct(
    DampedCosine,
    [
        FixedFloat("DC_A", 8, in_range(0.000001, 1.0), ndigits=6),
        ExpFloat("DC_T", 21, in_range(1e-06, 9.99999999999999e99), edigits=2),
        ExpFloat("DC_P", 21, in_range(1e-06, 9.99999999999999e99), edigits=2),
    ],
)


class SpdcfFamily(IntEnum):
    CSM_FOUR_PARAM = 0
    PIECEWISE_LINEAR = 1
    DAMPED_COSINE = 2


def get_spdcf_fam(ctx: Context) -> SpdcfFamily:
    mapping = {
        CsmFourParam: SpdcfFamily.CSM_FOUR_PARAM,
        PiecewiseLinear: SpdcfFamily.PIECEWISE_LINEAR,
        DampedCosine: SpdcfFamily.DAMPED_COSINE,
    }

    details = ctx["details"]
    return mapping[type(details)]


spdcf = Struct(
    Spdcf,
    [
        Int("SPDCF_ID", 2, positive),
        PrefixedList(
            name="constituents",
            count=Int("SPDCF_P", 2, positive),
            body=Struct(
                ConstituentSpdcf,
                [
                    Computed(
                        BcsIntEnum("SPDCF_FAM", 1, enum=SpdcfFamily),
                        get_spdcf_fam,
                    ),
                    FixedFloat("SPDCF_WEIGHT", 5, in_range(0.0, 1.0), ndigits=3),
                    Switch(
                        name="details",
                        get_tag=lambda ctx: ctx["SPDCF_FAM"],
                        cases={
                            SpdcfFamily.CSM_FOUR_PARAM: csm_four_param,
                            SpdcfFamily.PIECEWISE_LINEAR: piecewise_linear,
                            SpdcfFamily.DAMPED_COSINE: damped_cosine,
                        },
                    ),
                ],
            ),
        ),
    ],
)


unmodeled_error = Struct(
    UnmodeledError,
    [
        PrefixedArray(
            name="covariances",
            rows_rule=Int("LINE_DIMENSION", 3, in_range(1, 999)),
            cols_rule=Int("SAMPLE_DIMENSION", 2, in_range(1, 99)),
            body=Vector([
                ExpFloat("URR", 21, edigits=2),
                ExpFloat("URC", 21, edigits=2),
                ExpFloat("UCC", 21, edigits=2),
            ]),
        ),
        Int("LINE_SPDCF", 2, positive),
        Int("SAMPLE_SPDCF", 2, positive),
    ],
)

ts_group1 = Struct(
    TsGroup1,
    [
        IsoDate("CORR_REF_DATE_TS"),
        HMSeconds("CORR_REF_TIME_TS", 16),
        ExpFloat("TSRR", 21, edigits=2),
        ExpFloat("TSRC", 21, edigits=2),
        ExpFloat("TSCC", 21, edigits=2),
        Int("TS_SPDCF", 2, positive),
    ],
)

ts_group2 = Struct(
    TsGroup2,
    [
        IsoDate("CORR_REF_DATE_TSP"),
        HMSeconds("CORR_REF_TIME_TSP", 16),
        ExpFloat("TS_POS_COV", 21, edigits=2),
        Int("TS_POS_SPDCF", 2, positive),
        IsoDate("CORR_REF_DATE_TSA"),
        HMSeconds("CORR_REF_TIME_TSA", 16),
        ExpFloat("TS_ATT_COV", 21, edigits=2),
        Int("TS_ATT_SPDCF", 2, positive),
    ],
)

ts_group3 = Struct(
    TsGroup3,
    [
        IsoDate("CORR_REF_DATE_TS"),
        HMSeconds("CORR_REF_TIME_TS", 16),
        ExpFloat("TS_POS_COV", 21, edigits=2),
        ExpFloat("TS_POS_ATT_COV", 21, edigits=2),
        ExpFloat("TS_POS_FL_COV", 21, edigits=2),
        ExpFloat("TS_ATT_COV", 21, edigits=2),
        ExpFloat("TS_ATT_FL_COV", 21, edigits=2),
        ExpFloat("TS_FL_COV", 21, edigits=2),
        Int("TS_SPDCF", 2, positive),
    ],
)

ts_group4 = Struct(
    TsGroup4,
    [
        IsoDate("CORR_REF_DATE_TSPA"),
        HMSeconds("CORR_REF_TIME_TSPA", 16),
        ExpFloat("TS_POS_COV", 21, edigits=2),
        ExpFloat("TS_POS_ATT_COV", 21, edigits=2),
        ExpFloat("TS_ATT_COV", 21, edigits=2),
        Int("TS_PA_SPDCF", 2, positive),
        IsoDate("CORR_REF_DATE_TSFL"),
        HMSeconds("CORR_REF_TIME_TSFL", 16),
        ExpFloat("TS_FL_COV", 21, edigits=2),
        Int("TS_FL_SPDCF", 2, positive),
    ],
)

ts_group5 = Struct(
    TsGroup5,
    [
        IsoDate("CORR_REF_DATE_TSP"),
        HMSeconds("CORR_REF_TIME_TSP", 16),
        ExpFloat("TS_POS_COV", 21, edigits=2),
        Int("TS_POS_SPDCF", 2, positive),
        IsoDate("CORR_REF_DATE_TSA"),
        HMSeconds("CORR_REF_TIME_TSA", 16),
        ExpFloat("TS_ATT_COV", 21, edigits=2),
        Int("TS_ATT_SPDCF", 2, positive),
        IsoDate("CORR_REF_DATE_TSFL"),
        HMSeconds("CORR_REF_TIME_TSFL", 16),
        ExpFloat("TS_FL_COV", 21, edigits=2),
        Int("TS_FL_SPDCF", 2, positive),
    ],
)

ts_calibration: Variant[int, TsCalibration] = Variant(
    tag_rule=Int("NUM_TS_GRP", 1, in_range(1, 5)),
    cases=[
        Case(1, TsGroup1, ts_group1),
        Case(2, TsGroup2, ts_group2),
        Case(3, TsGroup3, ts_group3),
        Case(4, TsGroup4, ts_group4),
        Case(5, TsGroup5, ts_group5),
    ],
)

io_calibration = Struct(
    IoCalibration,
    [
        PrefixedList(
            name="focal_lengths",
            count=Int("NUM_SETS_CAL_AP", 2, positive),
            body=FixedFloat(
                "FOCAL_LENGTH_CAL", 11, in_range(0.0, 99.99999999), ndigits=8
            ),
        ),
        PrefixedList(
            name="groups",
            count=Int("NCAL_CPG", 2, positive),
            body=Struct(
                IoCpg,
                [
                    IsoDate("CORR_REF_DATE_IO"),
                    HMSeconds("CORR_REF_TIME_IO", 16),
                    PrefixedList(
                        name="parameters",
                        count=Int("N1CAL", 2, in_range(1, 11)),
                        body=BcsIntEnum("CAL_AP_ID", 2, enum=CalApId),
                    ),
                    SizedList(
                        name="covariances",
                        count=lambda ctx: len(ctx["focal_lengths"]),
                        body=SizedList(
                            num_covar_elems("parameters"),
                            ExpFloat("ERRCOV_C3", 21, edigits=2),
                        ),
                    ),
                    BcsIntEnum("CAL_INTERP", 1, enum=InterpType),
                    Int("SPDCF_ID_TIME", 2, positive),
                    Int("SPDCF_ID_FL", 2, positive),
                ],
            ),
        ),
    ],
)


def post_covar_count(ctx: Context) -> int:
    """For how many posts do we have covariance?"""
    if isinstance(ctx, EmitContext):
        return len(ctx["covar"])

    return 1 if ctx["COMMON_POSTS_COV"] else ctx["NUM_POSTS"]


post_sub = Struct(
    PostSub,
    [
        IsoDate("POST_START_DATE"),
        FixedFloat("POST_START_TIME", 15, in_range(0, 86399.999999999), ndigits=9),
        FixedFloat("POST_DT", 13, in_range(0, 999.999999999), ndigits=9),
        Int("NUM_POSTS", 3, in_range(2, 999)),
        Computed(Bool("COMMON_POSTS_COV"), lambda ctx: len(ctx["covar"]) == 1),
        SizedList(
            name="covar",
            count=post_covar_count,
            body=SizedList(
                num_covar_elems("parameters"),
                ExpFloat("ERRCOV_C2", 21, edigits=2),
            ),
        ),
        BcsIntEnum("POST_INTERP", 1, enum=InterpType),
        Optional(
            name="platform_spdcfs",
            condition=Bool("POST_PF_FLAG"),
            body=PrefixedList(
                Int("NUM_POST_PF", 2, positive),
                Struct(
                    PostPlatformSpdcf,
                    [
                        Int("POST_PF_SPDCF", 2, positive),
                        PrefixedList(
                            name="pairings",
                            count=Int("NUM_PAIRINGS_POST_PF", 2, positive),
                            body=BcsString("POST_PF_SPDCF_SENSOR", 6),
                        ),
                    ],
                ),
            ),
        ),
        Optional(
            name="payload_spdcfs",
            condition=Bool("POST_PL_FLAG"),
            body=PrefixedList(
                Int("NUM_POST_PL", 2, positive),
                Struct(
                    PostPayloadSpdcf,
                    [
                        Int("POST_PL_SPDCF", 2, positive),
                        PrefixedList(
                            name="pairings",
                            count=Int("NUM_PAIRINGS_POST_PL", 2, positive),
                            body=BcsString("POST_PL_SPDCF_SENSOR", 6),
                        ),
                    ],
                ),
            ),
        ),
        Optional(
            name="sensor_spdcf",
            condition=Bool("POST_SR_FLAG"),
            body=Struct(
                PostSensorSpdcf,
                [
                    Int("POST_SR_SPDCF", 2, positive),
                    Bool("POST_CORR"),
                ],
            ),
        ),
    ],
)


basic_sub = Struct(
    BasicSub,
    [
        SizedList(
            name="covar",
            count=num_covar_elems("parameters"),
            body=ExpFloat("ERRCOV_C1", 21, edigits=2),
        ),
        Optional(
            name="platform_spdcfs",
            condition=Bool("BASIC_PF_FLAG"),
            body=PrefixedList(
                Int("NUM_BASIC_PF", 2, positive),
                Struct(
                    BasicPlatformSpdcf,
                    [
                        Int("BASIC_PF_SPDCF", 2, positive),
                        PrefixedList(
                            name="pairings",
                            count=Int("NUM_PAIRINGS_BASIC_PF", 2, positive),
                            body=BcsString("BASIC_PF_SPDCF_SENSOR", 6),
                        ),
                    ],
                ),
            ),
        ),
        Optional(
            name="payload_spdcfs",
            condition=Bool("BASIC_PL_FLAG"),
            body=PrefixedList(
                Int("NUM_BASIC_PL", 2, positive),
                Struct(
                    BasicPayloadSpdcf,
                    [
                        Int("BASIC_PL_SPDCF", 2, positive),
                        PrefixedList(
                            name="pairings",
                            count=Int("NUM_PAIRINGS_BASIC_PL", 2, positive),
                            body=BcsString("BASIC_PL_SPDCF_SENSOR", 6),
                        ),
                    ],
                ),
            ),
        ),
        Optional(
            name="sensor_spdcf",
            condition=Bool("BASIC_SR_FLAG"),
            body=Int("BASIC_SR_SPDCF", 2, positive),
        ),
    ],
)


core_set = Struct(
    CoreSet,
    [
        BcsIntEnum("REF_FRAME_POSITION", 1, enum=ReferenceFrame),
        BcsIntEnum("REF_FRAME_ATTITUDE", 1, enum=ReferenceFrame),
        PrefixedList(
            name="groups",
            count=Int("NUM_GROUPS", 1, in_range(1, 7)),
            body=Struct(
                CPGroup,
                [
                    IsoDate("CORR_REF_DATE"),
                    HMSeconds("CORR_REF_TIME", 16),
                    PrefixedList(
                        name="parameters",
                        count=Int("NUM_ADJ_PARM", 1, in_range(1, 7)),
                        body=BcsIntEnum("ADJ_PARM_ID", 1, enum=ParameterId),
                    ),
                    Optional(
                        name="basic",
                        condition=Bool("BASIC_SUB_ALLOC"),
                        body=basic_sub,
                    ),
                    Optional(
                        name="post",
                        condition=Bool("POST_SUB_ALLOC"),
                        body=post_sub,
                    ),
                ],
            ),
        ),
    ],
)


cscsdb = Segment(
    CSCSDB,
    subheader=[
        Constant(BcsString("DE", 2), "DE"),
        Constant(BcsString("DESID", 25), "CSCSDB"),
        Constant(Int("DESVER", 2), 1),
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
        IsoDate("COV_VERSION_DATE"),
        PrefixedList(
            name="core_sets",
            count=Int("CORE_SETS", 1, in_range(0, 6)),
            body=core_set,
        ),
        Optional(
            name="io_calibration",
            condition=Bool("IO_CAL_AP"),
            body=io_calibration,
        ),
        Optional(
            name="ts_calibration",
            condition=Bool("TS_CAL_AP"),
            body=ts_calibration,
        ),
        Optional(
            name="unmodeled",
            condition=Bool("UE_FLAG"),
            body=unmodeled_error,
        ),
        Optional(
            name="spdcfs",
            condition=Bool("SPDCF_FLAG"),
            body=PrefixedList(
                Int("NUM_SPDCF", 2, positive),
                spdcf,
            ),
        ),
        Optional(
            name="direct_covar",
            condition=Bool("DIRECT_COVARIANCE_FLAG"),
            body=direct_cover,
        ),
        ReservedExtensions(
            Int("RESERVED_LEN", 9, nonnegative),
            Int("MASK_LEN", 2, positive),
            {
                1: SizedList(
                    name="adj_param_spdcfs",
                    # Because the spec references NUM_PARA here, I assume that this
                    # extension only appears when direct covariance is supplied.
                    count=lambda ctx: len(ctx["direct_covar"].adjustments),
                    body=Int("SPDCF_ID_ADJ", 2, positive),
                ),
            },
        ),
    ],
)

register_des("CSCSDB", 1, cscsdb)
