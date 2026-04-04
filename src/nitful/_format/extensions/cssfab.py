from enum import IntEnum, StrEnum

from nitful._format.des import register_des
from nitful._format.shared import ReservedExtensions, Segment, security_spec
from nitful.dsl.rules import (
    Alias,
    BcsFloat,
    BcsIntEnum,
    BcsString,
    BcsStringEnum,
    BinaryInt,
    Blankable,
    Case,
    Computed,
    Constant,
    Fixed,
    Int,
    IsoDate,
    Nothing,
    Override,
    PrefixedList,
    SizedBlock,
    SizedList,
    Struct,
    Switch,
    Uuid,
    Variant,
    Vector,
)
from nitful.dsl.validators import in_range, nonnegative, one_of, positive
from nitful.extensions.cssfab import (
    CSSFAB,
    BandCategory,
    BandInfo,
    CalibrationFieldAngleData,
    DirectFieldAngleData,
    FieldAlignmentPair,
    FocalLengthInterpolation,
    FocalLengthPoint,
    FrameFieldAlignmentBlock,
    FrameFieldAngleSetCalibration,
    FrameFieldAngleSetDirect,
    FramerAlignment,
    ScannerAlignment,
    TelescopeOpticsDataSet,
    TelescopeOpticsFrameBased,
    TelescopeOpticsTimeBased,
    TelescopeOpticsTimeTransform,
    TimeVaryingIoParmId,
)


class SensorType(StrEnum):
    SCANNER = "S"
    FRAMER = "F"


class FieldAngleType(IntEnum):
    DIRECT = 0
    CALIBRATION = 1


class TelescopeOpticsFlag(IntEnum):
    NONE = 0
    FRAME_BASED = 1
    TIME_BASED = 2


field_alignment_block = Struct(
    FrameFieldAlignmentBlock,
    [
        Fixed("FA_X1", 11, ndigits=7, sign=True),
        Fixed("FA_Y1", 11, ndigits=7, sign=True),
        Fixed("FA_X2", 11, ndigits=7, sign=True),
        Fixed("FA_Y2", 11, ndigits=7, sign=True),
        Fixed("FA_X3", 11, ndigits=7, sign=True),
        Fixed("FA_Y3", 11, ndigits=7, sign=True),
        Fixed("FA_X4", 11, ndigits=7, sign=True),
        Fixed("FA_Y4", 11, ndigits=7, sign=True),
    ],
)

fpa_transform = Vector([
    BcsFloat("LS_FID_TRANS_T0", 21, edigits=2),
    BcsFloat("LS_FID_TRANS_T1", 21, edigits=2),
    BcsFloat("LS_FID_TRANS_T2", 21, edigits=2),
    BcsFloat("LS_FID_TRANS_T3", 21, edigits=2),
    BcsFloat("LS_FID_TRANS_T4", 21, edigits=2),
    BcsFloat("LS_FID_TRANS_T5", 21, edigits=2),
    BcsFloat("LS_FID_TRANS_T6", 21, edigits=2),
    BcsFloat("LS_FID_TRANS_T7", 21, edigits=2),
])

telescope_dataset = Struct(
    TelescopeOpticsDataSet,
    [
        Fixed("FL_CAL_IOP_TELE", 11, nonnegative, ndigits=8),
        BcsFloat("PPO_XO_TELE", 21, edigits=2),
        BcsFloat("PPO_YO_TELE", 21, edigits=2),
        BcsFloat("RLD_KO_TELE", 21, edigits=2),
        BcsFloat("RLD_K1_TELE", 21, edigits=2),
        BcsFloat("RLD_K2_TELE", 21, edigits=2),
        BcsFloat("RLD_K3_TELE", 21, edigits=2),
        BcsFloat("DCD_P1_TELE", 21, edigits=2),
        BcsFloat("DCD_P2_TELE", 21, edigits=2),
        BcsFloat("DCD_P3_TELE", 21, edigits=2),
        BcsFloat("AD_A1_TELE", 21, edigits=2),
        BcsFloat("AD_A2_TELE", 21, edigits=2),
        BcsFloat("RADIUS_OF_VALIDITY_TELE", 21, nonnegative, edigits=2),
    ],
)

telescope_transform = Vector([
    BcsFloat("TELE_TRANS_T0", 21, edigits=2),
    BcsFloat("TELE_TRANS_T1", 21, edigits=2),
    BcsFloat("TELE_TRANS_T2", 21, edigits=2),
    BcsFloat("TELE_TRANS_T3", 21, edigits=2),
    BcsFloat("TELE_TRANS_T4", 21, edigits=2),
    BcsFloat("TELE_TRANS_T5", 21, edigits=2),
    BcsFloat("TELE_TRANS_T6", 21, edigits=2),
    BcsFloat("TELE_TRANS_T7", 21, edigits=2),
])

telescope_optics_frame = Struct(
    TelescopeOpticsFrameBased,
    [
        Computed(
            Int("NUM_TELE_SETS_FA_DATA", 1, nonnegative),
            lambda ctx: len(ctx["datasets"]),
        ),
        PrefixedList(
            name="frames",
            count=BinaryInt("N_FRAMES", 4),
            body=telescope_transform,
        ),
        SizedList(
            name="datasets",
            count=lambda ctx: ctx["NUM_TELE_SETS_FA_DATA"],
            body=telescope_dataset,
        ),
    ],
)

telescope_optics_time = Struct(
    TelescopeOpticsTimeBased,
    [
        Computed(
            Int("NUM_TELE_SETS_FA_DATA", 1, nonnegative),
            lambda ctx: len(ctx["datasets"]),
        ),
        Computed(
            BinaryInt("N_FRAME_TIMES", 4),
            lambda ctx: len(ctx["times"]),
        ),
        PrefixedList(
            name="varying_io_parm_ids",
            count=Int("N_VARYING_IO", 2, in_range(1, 11)),
            body=BcsIntEnum("TIME_VARYING_IO_PARM_ID", 2, enum=TimeVaryingIoParmId),
        ),
        IsoDate("TELE_DATE"),
        SizedList(
            name="times",
            count=lambda ctx: ctx["N_FRAME_TIMES"],
            body=Struct(
                TelescopeOpticsTimeTransform,
                [
                    Fixed("TELE_TIME", 15, ndigits=9),
                    Alias("transform", telescope_transform),
                    SizedList(
                        name="varying_io_m",
                        count=lambda ctx: ctx["N_VARYING_IO"],
                        body=BcsFloat("TIME_VARYING_IO_M", 21, edigits=2),
                    ),
                ],
            ),
        ),
        SizedList(
            name="datasets",
            count=lambda ctx: ctx["NUM_TELE_SETS_FA_DATA"],
            body=telescope_dataset,
        ),
    ],
)

direct_field_angle_data = Struct(
    DirectFieldAngleData,
    [
        SizedList(
            name="sets",
            count=lambda ctx: ctx["NUM_SETS_FA_DATA"],
            body=Struct(
                FrameFieldAngleSetDirect,
                [
                    Fixed("FL_CAL", 11, ndigits=8),
                    Fixed("NUM_FIR_LINE", 12, ndigits=5, sign=True),
                    Fixed("DELTA_LINE", 11, ndigits=5),
                    Computed(
                        Int("NUM_FA_BLOCKS_LINE", 3, positive),
                        lambda ctx: len(ctx["blocks"]),
                    ),
                    Fixed("NUM_FIR_SAMP", 12, ndigits=5, sign=True),
                    Fixed("DELTA_SAMP", 11, ndigits=5),
                    Computed(
                        Int("NUM_FA_BLOCKS_SAMP", 3, positive),
                        lambda ctx: len(ctx["blocks"][0]),
                    ),
                    SizedList(
                        name="blocks",
                        count=lambda ctx: ctx["NUM_FA_BLOCKS_LINE"],
                        body=SizedList(
                            count=lambda ctx: ctx["NUM_FA_BLOCKS_SAMP"],
                            body=field_alignment_block,
                        ),
                    ),
                ],
            ),
        ),
    ],
)

calibration_field_angle_data = Struct(
    CalibrationFieldAngleData,
    [
        BcsIntEnum("FA_INTERP", 1, enum=FocalLengthInterpolation),
        Computed(
            Int("NUM_FP_ARRAYS_LINE", 3, positive),
            lambda ctx: len(ctx["fp_arrays"]),
        ),
        Computed(
            Int("NUM_FP_ARRAYS_SAMP", 3, positive),
            lambda ctx: len(ctx["fp_arrays"][0]),
        ),
        SizedList(
            name="fp_arrays",
            count=lambda ctx: ctx["NUM_FP_ARRAYS_LINE"],
            body=SizedList(
                count=lambda ctx: ctx["NUM_FP_ARRAYS_SAMP"],
                body=fpa_transform,
            ),
        ),
        SizedList(
            name="sets",
            count=lambda ctx: ctx["NUM_SETS_FA_DATA"],
            body=Struct(
                FrameFieldAngleSetCalibration,
                [
                    Fixed("FL_CAL_IOP", 11, ndigits=8),
                    BcsFloat("PPO_XO", 21, edigits=2),
                    BcsFloat("PPO_YO", 21, edigits=2),
                    BcsFloat("RLD_KO", 21, edigits=2),
                    BcsFloat("RLD_K1", 21, edigits=2),
                    BcsFloat("RLD_K2", 21, edigits=2),
                    BcsFloat("RLD_K3", 21, edigits=2),
                    BcsFloat("DCD_P1", 21, edigits=2),
                    BcsFloat("DCD_P2", 21, edigits=2),
                    BcsFloat("DCD_P3", 21, edigits=2),
                    BcsFloat("AD_A1", 21, edigits=2),
                    BcsFloat("AD_A2", 21, edigits=2),
                    BcsFloat("RADIUS_OF_VALIDITY", 21, edigits=2),
                ],
            ),
        ),
    ],
)

framer_alignment = Struct(
    FramerAlignment,
    [
        Computed(
            Int("NUM_SETS_FA_DATA", 1, positive),
            lambda ctx: len(ctx["field_angle_data"].sets),
        ),
        Computed(
            BcsIntEnum("FIELD_ANGLE_TYPE", 1, enum=FieldAngleType),
            lambda ctx: (
                FieldAngleType.DIRECT
                if isinstance(ctx["field_angle_data"], DirectFieldAngleData)
                else FieldAngleType.CALIBRATION
            ),
        ),
        BcsIntEnum("FA_INTERP", 1, enum=FocalLengthInterpolation),
        Switch(
            name="field_angle_data",
            get_tag=lambda ctx: ctx["FIELD_ANGLE_TYPE"],
            cases={
                FieldAngleType.DIRECT: direct_field_angle_data,
                FieldAngleType.CALIBRATION: calibration_field_angle_data,
            },
        ),
        Variant(
            name="telescope_optics",
            tag_rule=BcsIntEnum("TELESCOPE_OPTICS_FLAG", 1, enum=TelescopeOpticsFlag),
            cases=[
                Case(TelescopeOpticsFlag.NONE, type(None), Nothing()),
                Case(
                    TelescopeOpticsFlag.FRAME_BASED,
                    TelescopeOpticsFrameBased,
                    telescope_optics_frame,
                ),
                Case(
                    TelescopeOpticsFlag.TIME_BASED,
                    TelescopeOpticsTimeBased,
                    telescope_optics_time,
                ),
            ],
        ),
    ],
)

scanner_alignment = Struct(
    ScannerAlignment,
    [
        Fixed("SMPL_NUM_FIRST", 12, ndigits=5, sign=True),
        Fixed("DELTA_SMPL_PAIRS", 11, ndigits=5),
        PrefixedList(
            name="fa_pairs",
            count=Int("NUM_FA_PAIRS", 3, positive),
            body=Struct(
                FieldAlignmentPair,
                [
                    Fixed("START_FALIGN_X", 11, ndigits=7, sign=True),
                    Fixed("START_FALIGN_Y", 11, ndigits=7, sign=True),
                    Fixed("END_FALIGN_X", 11, ndigits=7, sign=True),
                    Fixed("END_FALIGN_Y", 11, ndigits=7, sign=True),
                ],
            ),
        ),
    ],
)

cssfab = Segment(
    CSSFAB,
    subheader=[
        Constant(BcsString("DE", 2), "DE"),
        Constant(BcsString("DESID", 25), "CSSFAB"),
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
        Computed(
            BcsStringEnum("SENSOR_TYPE", 1, enum=SensorType),
            lambda ctx: (
                SensorType.SCANNER
                if isinstance(ctx["alignment"], ScannerAlignment)
                else SensorType.FRAMER
            ),
        ),
        BcsStringEnum("BAND_TYPE", 1, enum=BandCategory),
        Fixed("BAND_WAVELENGTH", 11, ndigits=8),
        PrefixedList(
            name="bands",
            count=Int("N_BANDS", 5, nonnegative),
            body=Struct(
                BandInfo,
                [
                    Int("BAND_INDEX", 5, positive),
                    Blankable(BcsString("IREPBAND", 2)),
                    Blankable(BcsString("ISUBCAT", 6)),
                ],
            ),
        ),
        Computed(
            Int("NUM_FL_PTS", 3, positive),
            lambda ctx: len(ctx["focal_lengths"]),
        ),
        BcsIntEnum("FL_INTERP", 1, enum=FocalLengthInterpolation),
        IsoDate("FOC_LENGTH_DATE"),
        SizedList(
            name="focal_lengths",
            count=lambda ctx: ctx["NUM_FL_PTS"],
            body=Struct(
                FocalLengthPoint,
                [
                    Fixed("FOC_LENGTH_TIME", 15, ndigits=9),
                    Fixed("FOC_LENGTH", 11, ndigits=8),
                ],
            ),
        ),
        Vector(
            name="position_offset",
            rules=[
                Fixed("PPOFF_X", 10, ndigits=6, sign=True),
                Fixed("PPOFF_Y", 10, ndigits=6, sign=True),
                Fixed("PPOFF_Z", 10, ndigits=6, sign=True),
            ],
        ),
        Vector(
            name="angle_offset",
            rules=[
                Fixed("ANGOFF_X", 10, ndigits=7, sign=True),
                Fixed("ANGOFF_Y", 10, ndigits=7, sign=True),
                Fixed("ANGOFF_Z", 10, ndigits=7, sign=True),
            ],
        ),
        Switch(
            name="alignment",
            get_tag=lambda ctx: ctx["SENSOR_TYPE"],
            cases={
                SensorType.SCANNER: scanner_alignment,
                SensorType.FRAMER: framer_alignment,
            },
        ),
        ReservedExtensions(
            Int("RESERVED_LEN", 9, nonnegative),
            Int("MASK_LEN", 2, positive),
            cases={},
        ),
    ],
)

register_des("CSSFAB", 1, cssfab)
register_des("CSSFAB", 2, cssfab)
