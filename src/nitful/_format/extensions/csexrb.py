"""CSEXRB TRE"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import BinaryIO, override

from nitful._dsl.spec import (
    BcsIntEnum,
    BcsString,
    BcsStringEnum,
    BinaryInt,
    Blankable,
    Bool,
    ConcatDatetime,
    Conditional,
    Constant,
    DataclassRecord,
    EmitContext,
    Field,
    Fixed,
    Int,
    IsoDate,
    Nothing,
    ParseContext,
    PrefixedList,
    ReservedExtensions,
    RuleSpec,
    SizedBlock,
    Spec,
    Switch,
    Uuid,
    VariantRecord,
    VarString,
)
from nitful._dsl.validator import Literals, NonNegative, Positive, Range
from nitful._format.tre import register_tre
from nitful.extensions.csexrb import (
    CSEXRB,
    CollectionCriteria,
    DesFramerTiming,
    FramerTiming,
    GroundCover,
    ImagingOperation,
    MtimsaTiming,
    QualityMetric,
    QualityType,
    RollingShutter,
    ScannerTiming,
    SensorType,
    SnowDepth,
    TargetAndCollectionData,
)


@dataclass
class TimeDeltas(Spec[list[int]]):
    """Handle the variable-size time deltas."""

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> list[int]:
        dt_size = ctx["DT_SIZE"]
        num_dt = BinaryInt("NUMBER_DT", 4).parse(fd, ctx)
        return [BinaryInt("DT", dt_size).parse(fd, ctx) for _ in range(num_dt)]

    @override
    def _emit(self, value: list[int], *, ctx: EmitContext) -> list[Field]:
        dt_size = ctx["DT_SIZE"]

        fields = BinaryInt("NUMBER_DT", 4).to_fields(len(value), ctx)

        for v in value:
            fields.extend(BinaryInt("DT", dt_size).to_fields(v, ctx))

        return fields


@dataclass
class ExposureIndices(RuleSpec[list[int]]):
    """Handle the highly variable exposure indices."""

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> list[int]:
        num_exp = Int("NUM_EXP", 2).parse(fd, ctx)
        index_size = Int("INDEX_SIZE", 1).parse(fd, ctx)

        if index_size == 0:
            return []

        num_indices = Int("NUM_INDICES", 2).parse(fd, ctx)

        indices = [
            BinaryInt("INDEX_IN_IMG_OP_ID", index_size).parse(fd, ctx)
            for _ in ctx.iterate(range(num_indices))
        ]

        # If there is more than one exposure but only one index, it means the
        # indices are sequential starting at the supplied index.
        if num_indices == 1 and num_exp > 1:
            start_idx = indices[0]
            indices = [start_idx + m for m in range(num_exp)]

        return indices

    @override
    def _emit(self, value: list[int], *, ctx: EmitContext) -> list[Field]:
        num_exp = len(value)
        fields = Int("NUM_EXP", 2).to_fields(num_exp, ctx)

        if not value:
            fields.extend(Int("INDEX_SIZE", 1).to_fields(0, ctx))
            return fields

        # Check if the array is purely sequential (e.g., 5, 6, 7, 8)
        is_sequential = all(value[i] == value[0] + i for i in range(num_exp))

        # Determine num bytes needed for the largest index value
        max_val = max(value)
        index_size = (max_val.bit_length() + 7) // 8 if max_val > 0 else 1
        fields.extend(Int("INDEX_SIZE", 1).to_fields(index_size, ctx))

        if is_sequential:
            fields.extend(Int("NUM_INDICES", 2).to_fields(1, ctx))
            fields.extend(
                BinaryInt("INDEX_IN_IMG_OP_ID", index_size).to_fields(value[0], ctx)
            )
        else:
            fields.extend(Int("NUM_INDICESn", 2).to_fields(num_exp, ctx))
            for v in ctx.iterate(value):
                fields.extend(
                    BinaryInt("INDEX_IN_IMG_OP_ID", index_size).to_fields(v, ctx)
                )

        return fields


imaging_operation = DataclassRecord(
    ImagingOperation,
    [
        VarString(Int("CM_ID_LEN", 2, Range(0, 99)), name="CM_ID"),
        VarString(Int("SENSOR_CONFIG_LEN", 2, Range(0, 99)), name="SENSOR_CONFIG"),
        VarString(Int("IMG_OP_ID_LEN", 2, Range(0, 99)), name="IMG_OP_ID"),
        ExposureIndices(name="indices"),
        PrefixedList(
            Int("NUM_QUALITY_METRICS", 2, Range(0, 99)),
            DataclassRecord(
                QualityMetric,
                [
                    VarString(
                        Int("QUALITY_METRIC_NAME_LEN", 2, Range(1, 15)),
                        name="QUALITY_METRIC_NAME",
                    ),
                    VarString(
                        Int("QUALITY_METRIC_UNIT_LEN", 2),
                        name="QUALITY_METRIC_UNIT",
                    ),
                    BcsStringEnum("QUALITY_METRIC_TYPE", 1, enum=QualityType),
                    VarString(
                        Int("QUALITY_METRIC_VALUE_LEN", 2),
                        name="QUALITY_METRIC_VALUE",
                    ),
                ],
                name="quality_metrics",
            ),
        ),
    ],
    name="imaging_operations",
)

collection_criteria = DataclassRecord(
    CollectionCriteria,
    [
        VarString(
            Int("COLLECT_CRITERIA_NAME_LEN", 2, Range(1, 25)),
            name="COLLECT_CRITERIA_NAME",
        ),
        VarString(
            Int("COLLECT_CRITERIA_UNIT_LEN", 2, Range(0, 25)),
            name="COLLECT_CRITERIA_UNIT",
        ),
        VarString(
            Int("COLLECT_CRITERIA_VALUE_LEN", 2, Range(0, 25)),
            name="COLLECT_CRITERIA_VALUE",
        ),
    ],
)

rfa = DataclassRecord(
    TargetAndCollectionData,
    [
        Int("NUM_IMG_OPS", 2, Positive()),
        VarString(Int("TGT_ID_LEN", 2, Literals([0, 17])), name="TGT_ID"),
        VarString(Int("TGT_NAME_LEN", 2), name="TGT_NAME"),
        VarString(Int("TGT_TYPE_LEN", 2), name="TGT_TYPE"),
        Blankable(Fixed("TGT_LAT", 9, sign=True, ndigits=5)),
        Blankable(Fixed("TGT_LON", 10, sign=True, ndigits=5)),
        Blankable(Fixed("TGT_HT", 8, sign=True, ndigits=1)),
        Blankable(ConcatDatetime(name="TGT_DATE_TIME")),
        Blankable(Fixed("TGT_AZ", 7, Range(0, 359.999), ndigits=3)),
        Blankable(Fixed("TGT_ELEV_ANG", 7, Range(-90, 90), sign=True, ndigits=3)),
        Blankable(Fixed("TGT_BIDEC_ANG", 7, Range(0, 180), ndigits=3)),
        VarString(Int("COLL_REQ_ID_LEN", 3), name="COLL_REQ_ID"),
        VarString(Int("COLLECT_STRAT_LEN", 2), name="COLLECT_STRAT"),
        VarString(Int("COLLECT_TYPE_LEN", 2), name="COLLECT_TYPE"),
        VarString(Int("COLL_CODE_LEN", 2), name="COLL_CODE"),
        PrefixedList(
            name="collection_criteria",
            count=Int("NUM_COLLECT_CRITERIA", 2),
            body=collection_criteria,
        ),
        PrefixedList(Int("NUM_IMG_OPS_DATA", 2, Range(0, 99)), imaging_operation),
    ],
    name="rfa1",
)


scanner_timing = DataclassRecord(
    ScannerTiming,
    [
        IsoDate("DAY_FIRST_LINE_IMAGE"),
        Fixed("TIME_FIRST_LINE_IMAGE", 15, Range(0, 86399.999999999), ndigits=9),
        Fixed(
            "TIME_IMAGE_DURATION",
            16,
            Range(-86399.999999999, 86399.999999999),
            ndigits=9,
            sign=True,
        ),
    ],
)


class TimeStampLoc(IntEnum):
    CSEXRB = 0
    MTIMSA = 1


framer_timing = DataclassRecord(
    FramerTiming,
    [
        VariantRecord(
            BcsIntEnum("TIME_STAMP_LOC", 1, enum=TimeStampLoc),
            {
                TimeStampLoc.MTIMSA: DataclassRecord(MtimsaTiming, []),
                TimeStampLoc.CSEXRB: DataclassRecord(
                    DesFramerTiming,
                    [
                        Blankable(Int("REFERENCE_FRAME_NUM", 9, Positive())),
                        BcsString("BASE_TIMESTAMP", 24),
                        BinaryInt("DT_MULTIPLIER", 8, Positive()),
                        BinaryInt("DT_SIZE", 1, Positive()),
                        BinaryInt("NUMBER_FRAMES", 4, Positive()),
                        BinaryInt("NUMBER_DT", 4, NonNegative()),
                        TimeDeltas("time_deltas"),
                    ],
                ),
            },
        ),
    ],
)

csexrb = DataclassRecord(
    CSEXRB,
    [
        Constant(BcsString("CETAG", 6), "CSEXRB"),
        SizedBlock(
            length_spec=Int("CEL", 5),
            body=[
                Uuid("IMAGE_UUID"),
                PrefixedList(
                    name="associated_elements",
                    count=Int("NUM_ASSOC_DES", 3),
                    body=Uuid("ASSOC_DES_UUID"),
                ),
                BcsString("PLATFORM_ID", 6),
                BcsString("PAYLOAD_ID", 6),
                BcsString("SENSOR_ID", 6),
                BcsStringEnum("SENSOR_TYPE", 1, enum=SensorType),
                Blankable(Fixed("GROUND_REF_POINT_X", 12, sign=True, ndigits=2)),
                Blankable(Fixed("GROUND_REF_POINT_Y", 12, sign=True, ndigits=2)),
                Blankable(Fixed("GROUND_REF_POINT_Z", 12, sign=True, ndigits=2)),
                Switch(
                    name="timing",
                    get_tag=lambda ctx: ctx["SENSOR_TYPE"],
                    cases={
                        SensorType.SCANNER: scanner_timing,
                        SensorType.FRAMER: framer_timing,
                        SensorType.NONE: Nothing(),
                    },
                ),
                Blankable(Fixed("MAX_GSD", 12, NonNegative(), ndigits=1)),
                Blankable(Fixed("ALONG_SCAN_GSD", 12, NonNegative(), ndigits=1)),
                Blankable(Fixed("CROSS_SCAN_GSD", 12, NonNegative(), ndigits=1)),
                Blankable(Fixed("GEO_MEAN_GSD", 12, NonNegative(), ndigits=1)),
                Blankable(Fixed("A_S_VERT_GSD", 12, NonNegative(), ndigits=1)),
                Blankable(Fixed("C_S_VERT_GSD", 12, NonNegative(), ndigits=1)),
                Blankable(Fixed("GEO_MEAN_VERT_GSD", 12, NonNegative(), ndigits=1)),
                Blankable(Fixed("GSD_BETA_ANGLE", 5, Range(0, 180), ndigits=1)),
                Blankable(Int("DYNAMIC_RANGE", 5, NonNegative())),
                Int("NUM_LINES", 7, NonNegative()),
                Int("NUM_SAMPLES", 5, NonNegative()),
                Blankable(Fixed("ANGLE_TO_NORTH", 7, Range(0, 359.999), ndigits=3)),
                Blankable(Fixed("OBLIQUITY_ANGLE", 6, Range(0, 90), ndigits=3)),
                Blankable(Fixed("AZ_OF_OBLIQUITY", 7, Range(0, 359.999), ndigits=3)),
                Bool("ATM_REFR_FLAG", size=1),
                Bool("VEL_ABER_FLAG", size=1),
                BcsIntEnum("GRD_COVER", 1, enum=GroundCover),
                BcsIntEnum("SNOW_DEPTH_CATEGORY", 1, enum=SnowDepth),
                Blankable(Fixed("SUN_AZIMUTH", 7, Range(0, 359.999), ndigits=3)),
                Blankable(
                    Fixed("SUN_ELEVATION", 7, Range(-90, 90), sign=True, ndigits=3)
                ),
                Blankable(Fixed("PREDICTED_NIIRS", 3, Range(0.0, 9.0), ndigits=1)),
                Blankable(Fixed("CIRCL_ERR", 5, NonNegative(), ndigits=1)),
                Blankable(Fixed("LINEAR_ERR", 5, NonNegative(), ndigits=1)),
                Blankable(Int("CLOUD_COVER", 3)),
                Conditional(
                    condition=lambda ctx: ctx.get("SENSOR_TYPE") == SensorType.FRAMER,
                    body=Blankable(
                        BcsIntEnum("ROLLING_SHUTTER_FLAG", 1, enum=RollingShutter)
                    ),
                ),
                Blankable(Bool("UE_TIME_FLAG", size=1)),
                ReservedExtensions(
                    Int("RESERVED_LEN", 5, NonNegative()),
                    Int("MASK_LEN", 2, Positive()),
                    {
                        1: rfa,
                    },
                ),
            ],
        ),
    ],
)

register_tre("CSEXRB", csexrb)
