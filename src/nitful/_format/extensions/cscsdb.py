from collections.abc import Callable
from enum import IntEnum

from nitful._dsl.spec import (
    BcsFloat,
    BcsIntEnum,
    BcsString,
    Bool,
    Computed,
    Constant,
    Context,
    DataclassRecord,
    Fixed,
    HMSeconds,
    Int,
    IsoDate,
    Marker,
    Optional,
    Override,
    PrefixedArray,
    PrefixedList,
    ReservedExtensions,
    SizedBlock,
    SizedList,
    Switch,
    Uuid,
    VariantRecord,
    Vector,
)
from nitful._dsl.validator import Positive, Range
from nitful._format.des import register_des
from nitful._format.security import security_spec
from nitful.core.common import Security
from nitful.extensions.cscsdb import (
    CSCSDB,
    BasicPayloadSpdcf,
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


direct_cover: VariantRecord[int, DirectCovariance] = VariantRecord(
    tag_spec=Int("DC_TYPE", 1, Range(0, 9)),
    cases={
        0: DataclassRecord(
            DirectCovariance0,
            [
                PrefixedList(
                    name="adjustments",
                    count=Int("NUM_PARA", 4, Positive()),
                    body=BcsFloat("ADJ", 21, edigits=2),
                ),
                SizedList(
                    name="covariances",
                    count=num_covar_elems("adjustments"),
                    body=BcsFloat("ERRCOV_C4", 21, edigits=2),
                ),
            ],
        )
    },
)


csm_four_param = DataclassRecord(
    CsmFourParam,
    [
        Fixed("FP_A", 8, Range(0.000001, 1.0), ndigits=6),
        Fixed("FP_ALPHA", 8, Range(0.0, 1.0), ndigits=6),
        Fixed("FP_BETA", 9, Range(0.0, 10.0), ndigits=6),
        BcsFloat("FP_T", 21, Range(1e-06, 9.99999999999999e99), edigits=2),
    ],
)


piecewise_linear = DataclassRecord(
    PiecewiseLinear,
    [
        PrefixedList(
            name="segments",
            count=Int("NUM_SEGS", 2, Range(2, 10)),
            body=DataclassRecord(
                PlSegment,
                [
                    Fixed("PL_MAX_COR", 8, Range(0.0, 1.0), ndigits=6),
                    BcsFloat(
                        "PL_TAU_MAX_COR",
                        21,
                        Range(0, 9.99999999999999e99),
                        edigits=2,
                    ),
                ],
            ),
        )
    ],
)


damped_cosine = DataclassRecord(
    DampedCosine,
    [
        Fixed("DC_A", 8, Range(0.000001, 1.0), ndigits=6),
        BcsFloat("DC_T", 21, Range(1e-06, 9.99999999999999e99), edigits=2),
        BcsFloat("DC_P", 21, Range(1e-06, 9.99999999999999e99), edigits=2),
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


spdcf = DataclassRecord(
    Spdcf,
    [
        Int("SPDCF_ID", 2, Positive()),
        PrefixedList(
            name="constituents",
            count=Int("SPDCF_P", 2, Positive()),
            body=DataclassRecord(
                ConstituentSpdcf,
                [
                    Computed(
                        BcsIntEnum("SPDCF_FAM", 1, enum=SpdcfFamily),
                        get_spdcf_fam,
                    ),
                    Fixed("SPDCF_WEIGHT", 5, Range(0.0, 1.0), ndigits=3),
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


unmodeled_error = DataclassRecord(
    UnmodeledError,
    [
        PrefixedArray(
            name="covariances",
            rows_spec=Int("LINE_DIMENSION", 3, Range(1, 999)),
            cols_spec=Int("SAMPLE_DIMENSION", 2, Range(1, 99)),
            body=Vector([
                BcsFloat("URR", 21, edigits=2),
                BcsFloat("URC", 21, edigits=2),
                BcsFloat("UCC", 21, edigits=2),
            ]),
        ),
        Int("LINE_SPDCF", 2, Positive()),
        Int("SAMPLE_SPDCF", 2, Positive()),
    ],
)


ts_calibration: VariantRecord[int, TsCalibration] = VariantRecord(
    tag_spec=Int("NUM_TS_GRP", 1, Range(1, 5)),
    cases={
        1: DataclassRecord(
            TsGroup1,
            [
                IsoDate("CORR_REF_DATE_TS"),
                HMSeconds("CORR_REF_TIME_TS"),
                BcsFloat("TSRR", 21, edigits=2),
                BcsFloat("TSRC", 21, edigits=2),
                BcsFloat("TSCC", 21, edigits=2),
                Int("TS_SPDCF", 2, Positive()),
            ],
        ),
        2: DataclassRecord(
            TsGroup2,
            [
                IsoDate("CORR_REF_DATE_TSP"),
                HMSeconds("CORR_REF_TIME_TSP"),
                BcsFloat("TS_POS_COV", 21, edigits=2),
                Int("TS_POS_SPDCF", 2, Positive()),
                IsoDate("CORR_REF_DATE_TSA"),
                HMSeconds("CORR_REF_TIME_TSA"),
                BcsFloat("TS_ATT_COV", 21, edigits=2),
                Int("TS_ATT_SPDCF", 2, Positive()),
            ],
        ),
        3: DataclassRecord(
            TsGroup3,
            [
                IsoDate("CORR_REF_DATE_TS"),
                HMSeconds("CORR_REF_TIME_TS"),
                BcsFloat("TS_POS_COV", 21, edigits=2),
                BcsFloat("TS_POS_ATT_COV", 21, edigits=2),
                BcsFloat("TS_POS_FL_COV", 21, edigits=2),
                BcsFloat("TS_ATT_COV", 21, edigits=2),
                BcsFloat("TS_ATT_FL_COV", 21, edigits=2),
                BcsFloat("TS_FL_COV", 21, edigits=2),
                Int("TS_SPDCF", 2, Positive()),
            ],
        ),
        4: DataclassRecord(
            TsGroup4,
            [
                IsoDate("CORR_REF_DATE_TSPA"),
                HMSeconds("CORR_REF_TIME_TSPA"),
                BcsFloat("TS_POS_COV", 21, edigits=2),
                BcsFloat("TS_POS_ATT_COV", 21, edigits=2),
                BcsFloat("TS_ATT_COV", 21, edigits=2),
                Int("TS_PA_SPDCF", 2, Positive()),
                IsoDate("CORR_REF_DATE_TSFL"),
                HMSeconds("CORR_REF_TIME_TSFL"),
                BcsFloat("TS_FL_COV", 21, edigits=2),
                Int("TS_FL_SPDCF", 2, Positive()),
            ],
        ),
        5: DataclassRecord(
            TsGroup5,
            [
                IsoDate("CORR_REF_DATE_TSP"),
                HMSeconds("CORR_REF_TIME_TSP"),
                BcsFloat("TS_POS_COV", 21, edigits=2),
                Int("TS_POS_SPDCF", 2, Positive()),
                IsoDate("CORR_REF_DATE_TSA"),
                HMSeconds("CORR_REF_TIME_TSA"),
                BcsFloat("TS_ATT_COV", 21, edigits=2),
                Int("TS_ATT_SPDCF", 2, Positive()),
                IsoDate("CORR_REF_DATE_TSFL"),
                HMSeconds("CORR_REF_TIME_TSFL"),
                BcsFloat("TS_FL_COV", 21, edigits=2),
                Int("TS_FL_SPDCF", 2, Positive()),
            ],
        ),
    },
)


io_calibration = DataclassRecord(
    IoCalibration,
    [
        PrefixedList(
            name="focal_lengths",
            count=Int("NUM_SETS_CAL_AP", 2, Positive()),
            body=Fixed("FOCAL_LENGTH_CAL", 11, Range(0.0, 99.99999999), ndigits=8),
        ),
        PrefixedList(
            name="groups",
            count=Int("NCAL_CPG", 2, Positive()),
            body=DataclassRecord(
                IoCpg,
                [
                    IsoDate("CORR_REF_DATE_IO"),
                    HMSeconds("CORR_REF_TIME_IO"),
                    PrefixedList(
                        name="parameters",
                        count=Int("N1CAL", 2, Range(1, 11)),
                        body=BcsIntEnum("CAL_AP_ID", 2, enum=CalApId),
                    ),
                    SizedList(
                        name="covariances",
                        count=lambda ctx: len(ctx["focal_lengths"]),
                        body=SizedList(
                            num_covar_elems("parameters"),
                            BcsFloat("ERRCOV_C3", 21, edigits=2),
                        ),
                    ),
                    BcsIntEnum("CAL_INTERP", 1, enum=InterpType),
                    Int("SPDCF_ID_TIME", 2, Positive()),
                    Int("SPDCF_ID_FL", 2, Positive()),
                ],
            ),
        ),
    ],
)


def post_covar_count(ctx: Context) -> int:
    """For how many posts do we have covariance?"""
    if ctx.is_emitting:
        return len(ctx["covar"])

    return 1 if ctx["COMMON_POSTS_COV"] else ctx["NUM_POSTS"]


post_sub = DataclassRecord(
    PostSub,
    [
        IsoDate("POST_START_DATE"),
        Fixed("POST_START_TIME", 15, Range(0, 86399.999999999), ndigits=9),
        Fixed("POST_DT", 13, Range(0, 999.999999999), ndigits=9),
        Int("NUM_POSTS", 3, Range(2, 999)),
        Computed(Bool("COMMON_POSTS_COV"), lambda ctx: len(ctx["covar"]) == 1),
        SizedList(
            name="covar",
            count=post_covar_count,
            body=SizedList(
                num_covar_elems("parameters"),
                BcsFloat("ERRCOV_C2", 21, edigits=2),
            ),
        ),
        BcsIntEnum("POST_INTERP", 1, enum=InterpType),
        Optional(
            name="platform_spdcfs",
            condition=Bool("POST_PF_FLAG"),
            body=PrefixedList(
                Int("NUM_POST_PF", 2, Positive()),
                DataclassRecord(
                    BasicPayloadSpdcf,
                    [
                        Int("POST_PF_SPDCF", 2, Positive()),
                        PrefixedList(
                            name="pairings",
                            count=Int("NUM_PAIRINGS_POST_PF", 2, Positive()),
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
                Int("NUM_POST_PL", 2, Positive()),
                DataclassRecord(
                    BasicPayloadSpdcf,
                    [
                        Int("POST_PL_SPDCF", 2, Positive()),
                        PrefixedList(
                            name="pairings",
                            count=Int("NUM_PAIRINGS_POST_PL", 2, Positive()),
                            body=BcsString("POST_PL_SPDCF_SENSOR", 6),
                        ),
                    ],
                ),
            ),
        ),
        Optional(
            name="sensor_spdcf",
            condition=Bool("POST_SR_FLAG"),
            body=DataclassRecord(
                PostSensorSpdcf,
                [
                    Int("POST_SR_SPDCF", 2, Positive()),
                    Bool("POST_CORR"),
                ],
            ),
        ),
    ],
)


basic_sub = DataclassRecord(
    BasicSub,
    [
        SizedList(
            name="covar",
            count=num_covar_elems("parameters"),
            body=BcsFloat("ERRCOV_C1", 21, edigits=2),
        ),
        Optional(
            name="platform_spdcfs",
            condition=Bool("BASIC_PF_FLAG"),
            body=PrefixedList(
                Int("NUM_BASIC_PF", 2, Positive()),
                DataclassRecord(
                    BasicPayloadSpdcf,
                    [
                        Int("BASIC_PF_SPDCF", 2, Positive()),
                        PrefixedList(
                            name="pairings",
                            count=Int("NUM_PAIRINGS_BASIC_PF", 2, Positive()),
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
                Int("NUM_BASIC_PL", 2, Positive()),
                DataclassRecord(
                    BasicPayloadSpdcf,
                    [
                        Int("BASIC_PL_SPDCF", 2, Positive()),
                        PrefixedList(
                            name="pairings",
                            count=Int("NUM_PAIRINGS_BASIC_PL", 2, Positive()),
                            body=BcsString("BASIC_PL_SPDCF_SENSOR", 6),
                        ),
                    ],
                ),
            ),
        ),
        Optional(
            name="sensor_spdcf",
            condition=Bool("BASIC_SR_FLAG"),
            body=Int("BASIC_SR_SPDCF", 2, Positive()),
        ),
    ],
)


core_set = DataclassRecord(
    CoreSet,
    [
        BcsIntEnum("REF_FRAME_POSITION", 1, enum=ReferenceFrame),
        BcsIntEnum("REF_FRAME_ATTITUDE", 1, enum=ReferenceFrame),
        PrefixedList(
            name="groups",
            count=Int("NUM_GROUPS", 1, Range(1, 7)),
            body=DataclassRecord(
                CPGroup,
                [
                    IsoDate("CORR_REF_DATE"),
                    HMSeconds("CORR_REF_TIME"),
                    PrefixedList(
                        name="parameters",
                        count=Int("NUM_ADJ_PARM", 1, Range(1, 7)),
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


cscsdb = DataclassRecord(
    CSCSDB,
    name="CSCSDB",
    specs=[
        Marker("DES START CSCSDB"),
        Constant(BcsString("DE", 2), "DE"),
        Constant(BcsString("DESID", 25), "CSCSDB"),
        Constant(Int("DESVER", 2), 1),
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
        IsoDate("COV_VERSION_DATE"),
        PrefixedList(
            name="core_sets",
            count=Int("CORE_SETS", 1, Range(0, 6)),
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
                Int("NUM_SPDCF", 2, Positive()),
                spdcf,
            ),
        ),
        Optional(
            name="direct_covar",
            condition=Bool("DIRECT_COVARIANCE_FLAG"),
            body=direct_cover,
        ),
        ReservedExtensions({
            1: SizedList(
                name="adj_param_spdcfs",
                # Because the spec references NUM_PARA here, I assume that this
                # extension only appears when direct covariance is supplied.
                count=lambda ctx: len(ctx["direct_covar"].adjustments),
                body=Int("SPDCF_ID_ADJ", 2, Positive()),
            ),
        }),
    ],
)

register_des("CSCSDB", 1, cscsdb)
