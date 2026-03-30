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
    Constant,
    DataclassRecord,
    EmitContext,
    Field,
    Fixed,
    Int,
    IsoDate,
    Nothing,
    ParseContext,
    Spec,
    Switch,
    Uuid,
    VariantRecord,
)
from nitful._dsl.validator import NonNegative, Positive, Range
from nitful._format.tre import register_tre
from nitful.extensions.csexrb import (
    CSEXRB,
    DesFramerTiming,
    FramerTiming,
    MtimsaTiming,
    ScannerTiming,
    SensorType,
)


class TimeStampLoc(IntEnum):
    CSEXRB = 0
    MTIMSA = 1


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


@dataclass
class TimeDeltas(Spec[list[int]]):

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
        Constant(BcsString("CETAG", 6), "RPC00B"),
        Constant(Int("CEL", 5), 1041),
        Uuid("IMAGE_UUID"),
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
        # TODO: work in progress
    ],
)

register_tre("CSEXRB", csexrb)
