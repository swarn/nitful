from dataclasses import dataclass, field
from typing import Any, BinaryIO, ClassVar, override

from nitful._format.tre import register_tre
from nitful.dsl.rules import (
    Accept,
    BcsString,
    BcsStringEnum,
    Blankable,
    Combinator,
    Constant,
    Dashable,
    DecimalFloat,
    EmitContext,
    Field,
    FixedBytes,
    FlexFloat,
    HMSeconds,
    Int,
    IsoDate,
    Item,
    Optional,
    Override,
    ParseContext,
    PrefixedList,
    Rule,
    SizedBlock,
    Struct,
    Switch,
)
from nitful.dsl.validators import in_range, nonnegative, one_of, positive
from nitful.extensions.sensrb import (
    SENSRB,
    AdditionalParameter,
    AngularUnit,
    CalibrationData,
    CalibrationUnit,
    ElevationDatum,
    EulerAngles,
    GeneralData,
    GeodeticType,
    ImageFormationData,
    LengthUnit,
    PixelReferencedDataSet,
    PixelReferenceInstance,
    Point,
    PointSet,
    PositionData,
    Quaternion,
    ReferenceData,
    SensorArrayData,
    SensorVelocity,
    TimeStampedDataSet,
    TimeStampInstance,
    Uncertainty,
    UnitVectors,
)


@dataclass
class YNBool(Field[bool]):
    """A Y/N boolean value.

    When parsing, accept both 'N' and ' ' as False. While the NITF spec only
    allows 'N', apparently some vendors use ' '.
    """

    size: int = field(default=1, init=False)
    true: ClassVar[bytes] = b"Y"
    false: ClassVar[bytes] = b"N"

    @override
    def encode(self, decoded: bool) -> bytes:
        return self.true if decoded else self.false

    @override
    def decode(self, encoded: bytes) -> bool:
        if encoded == self.true:
            return True
        if encoded in [self.false, b" "]:
            return False
        msg = f"Decoding error: read {encoded!r}"
        raise RuntimeError(msg)


@dataclass
class Nullable[T](Override[T, None]):
    """Represent NODATA as all '-' chars.

    While parsing, also accept all ' ' characters as 'no value'. While the
    SENSRB spec only allows all '-' characters, some vendors use ' '.
    """

    def __init__(self, rule: Field[T]) -> None:
        dash_bytes = b"-" * rule.size
        space_bytes = b" " * rule.size

        # The dict order is preserved, so the spec-compliant bytes will be
        # found first and used during serialization.
        super().__init__(rule, {dash_bytes: None, space_bytes: None})


# Module 1
general_data = Struct(
    GeneralData,
    [
        BcsString("SENSOR", 25),
        Dashable(BcsString("SENSOR_URI", 32)),
        BcsString("PLATFORM", 25),
        Dashable(BcsString("PLATFORM_URI", 32)),
        BcsString("OPERATION_DOMAIN", 10),
        Int("CONTENT_LEVEL", 1, in_range(0, 9)),
        BcsString("GEODETIC_SYSTEM", 5),
        BcsStringEnum("GEODETIC_TYPE", 1, enum=GeodeticType),
        BcsStringEnum("ELEVATION_DATUM", 3, enum=ElevationDatum),
        Accept(
            BcsStringEnum("LENGTH_UNIT", 2, enum=LengthUnit),
            {b" m": LengthUnit.SI, b"ft": LengthUnit.EE},
        ),
        Accept(
            BcsStringEnum("ANGULAR_UNIT", 3, enum=AngularUnit),
            {b"deg": AngularUnit.DEG, b"rad": AngularUnit.RAD, b"smc": AngularUnit.SMC},
        ),
        Blankable(IsoDate("START_DATE")),
        DecimalFloat("START_TIME", 14, in_range(0, 86399.99999999)),
        IsoDate("END_DATE"),
        DecimalFloat("END_TIME", 14, in_range(0, 86399.99999999)),
        Int("GENERATION_COUNT", 2, in_range(0, 99)),
        Blankable(Dashable(IsoDate("GENERATION_DATE"))),
        Blankable(Dashable(HMSeconds("GENERATION_TIME", 10))),
    ],
)

# Module 2
sensor_array_data = Struct(
    SensorArrayData,
    [
        BcsString("DETECTION", 20),
        Int("ROW_DETECTORS", 8, positive),
        Int("COLUMN_DETECTORS", 8, positive),
        Dashable(DecimalFloat("ROW_METRIC", 8, positive)),
        Dashable(DecimalFloat("COLUMN_METRIC", 8, positive)),
        Dashable(DecimalFloat("FOCAL_LENGTH", 8, positive)),
        Dashable(DecimalFloat("ROW_FOV", 8, nonnegative)),
        Dashable(DecimalFloat("COLUMN_FOV", 8, nonnegative)),
        YNBool("CALIBRATED"),
    ],
)

# Module 3
calibration_data = Struct(
    CalibrationData,
    [
        BcsStringEnum("CALIBRATION_UNIT", 2, enum=CalibrationUnit),
        Dashable(DecimalFloat("PRINCIPAL_POINT_OFFSET_X", 9)),
        Dashable(DecimalFloat("PRINCIPAL_POINT_OFFSET_Y", 9)),
        Dashable(FlexFloat("RADIAL_DISTORT_1", 12)),
        Dashable(FlexFloat("RADIAL_DISTORT_2", 12)),
        Dashable(FlexFloat("RADIAL_DISTORT_3", 12)),
        Dashable(DecimalFloat("RADIAL_DISTORT_LIMIT", 9, nonnegative)),
        Dashable(FlexFloat("DECENT_DISTORT_1", 12)),
        Dashable(FlexFloat("DECENT_DISTORT_2", 12)),
        Dashable(FlexFloat("AFFINITY_DISTORT_1", 12)),
        Dashable(FlexFloat("AFFINITY_DISTORT_2", 12)),
        Dashable(IsoDate("CALIBRATION_DATE")),
    ],
)

# Module 4
image_formation_data = Struct(
    ImageFormationData,
    [
        BcsString("METHOD", 15),
        BcsString("MODE", 3),
        Int("ROW_COUNT", 8),
        Int("COLUMN_COUNT", 8),
        Int("ROW_SET", 8),
        Int("COLUMN_SET", 8),
        DecimalFloat("ROW_RATE", 10),
        DecimalFloat("COLUMN_RATE", 10),
        Int("FIRST_PIXEL_ROW", 8),
        Int("FIRST_PIXEL_COLUMN", 8),
        PrefixedList(
            name="transform_params",
            count=Int("TRANSFORM_PARAMS", 1, in_range(0, 8)),
            body=FlexFloat("TRANSFORM_PARAM", 12),
        ),
    ],
)

# Module 5
reference_data = Struct(
    name="reference",
    model_cls=ReferenceData,
    rules=[
        Nullable(DecimalFloat("REFERENCE_TIME", 12)),
        Nullable(Int("REFERENCE_ROW", 8)),
        Nullable(Int("REFERENCE_COL", 8)),
    ],
)

# Module 6
sensor_position = Struct(
    name="position",
    model_cls=PositionData,
    rules=[
        DecimalFloat("LATITUDE_OR_X", 11),
        Nullable(DecimalFloat("LONGITUDE_OR_Y", 12)),
        Nullable(DecimalFloat("ALTITUDE_OR_Z", 11)),
        DecimalFloat("SENSOR_X_OFFSET", 8),
        DecimalFloat("SENSOR_Y_OFFSET", 8),
        DecimalFloat("SENSOR_Z_OFFSET", 8),
    ],
)

# Module 7
euler_angles = Struct(
    EulerAngles,
    [
        Int("SENSOR_ANGLE_MODEL", 1, one_of(1, 2, 3)),
        DecimalFloat("SENSOR_ANGLE_1", 10, in_range(-180.0, 180.0)),
        DecimalFloat("SENSOR_ANGLE_2", 9, in_range(-90.0, 90.0)),
        DecimalFloat("SENSOR_ANGLE_3", 10, in_range(-180.0, 180.0)),
        Blankable(DecimalFloat("PLATFORM_HEADING", 9, in_range(0, 360.0))),
        Blankable(DecimalFloat("PLATFORM_PITCH", 9, in_range(0, 90.0))),
        Blankable(DecimalFloat("PLATFORM_ROLL", 10, in_range(0, 180.0))),
    ],
)


# Module 8
unit_vectors = Struct(
    UnitVectors,
    [
        DecimalFloat("ICX_NORTH_OR_X", 10, in_range(-1.0, 1.0)),
        DecimalFloat("ICX_EAST_OR_Y", 10, in_range(-1.0, 1.0)),
        DecimalFloat("ICX_DOWN_OR_Z", 10, in_range(-1.0, 1.0)),
        DecimalFloat("ICY_NORTH_OR_X", 10, in_range(-1.0, 1.0)),
        DecimalFloat("ICY_EAST_OR_Y", 10, in_range(-1.0, 1.0)),
        DecimalFloat("ICY_DOWN_OR_Z", 10, in_range(-1.0, 1.0)),
        DecimalFloat("ICZ_NORTH_OR_X", 10, in_range(-1.0, 1.0)),
        DecimalFloat("ICZ_EAST_OR_Y", 10, in_range(-1.0, 1.0)),
        DecimalFloat("ICZ_DOWN_OR_Z", 10, in_range(-1.0, 1.0)),
    ],
)

# Module 9
quaternion_spec = Struct(
    Quaternion,
    [
        DecimalFloat("ATTITUDE_Q1", 10, in_range(-1.0, 1.0)),
        DecimalFloat("ATTITUDE_Q2", 10, in_range(-1.0, 1.0)),
        DecimalFloat("ATTITUDE_Q3", 10, in_range(-1.0, 1.0)),
        DecimalFloat("ATTITUDE_Q4", 10, in_range(-1.0, 1.0)),
    ],
)

# Module 10
sensor_velocity_spec = Struct(
    SensorVelocity,
    [
        DecimalFloat("VELOCITY_NORTH_OR_X", 9),
        DecimalFloat("VELOCITY_EAST_OR_Y", 9),
        DecimalFloat("VELOCITY_DOWN_OR_Z", 9),
    ],
)

# Module 11
point_set_spec = Struct(
    PointSet,
    [
        BcsString("POINT_SET_TYPE", 25),
        PrefixedList(
            name="points",
            count=Int("POINT_COUNT", 3, positive),
            body=Struct(
                Point,
                [
                    DecimalFloat("P_ROW", 8),
                    DecimalFloat("P_COLUMN", 8),
                    Dashable(DecimalFloat("P_LATITUDE", 10, in_range(-90.0, 90.0))),
                    Dashable(DecimalFloat("P_LONGITUDE", 11, in_range(-180.0, 180.0))),
                    Dashable(DecimalFloat("P_ELEVATION", 6)),
                    Dashable(DecimalFloat("P_RANGE", 8, positive)),
                ],
            ),
        ),
    ],
)

# NOTE: I'm not enthusiastic about repeating all the Field definitions here,
# but other approaches, e.g., adding all fields to a local registry while
# defining them, makes the specs vastly harder to read.
#
# The NITF specifications for Module 12 and 13 specify "any appropriate" field
# can be referenced. Rather than exploring which fields are appropriate, simply
# add them all here.


def get_rules(field_name: str) -> dict[str, Rule[Any]]:
    """Generate a registry of Rules for most of the SENSRB fields.

    Modules 12 and 13 specify fields by their name in the NITF spec: "02a",
    "03f", etc. Then, they list values that match the size and type of
    that field.

    Our DSL spec for those modules use a `Switch` to find the correct rule for
    parsing/emitting. This function generates the lookup tables used by those
    switches. It injects the name (e.g. TIME_STAMP_VALUE) so that fields in
    plain text dumps will be labeled corrrectly.
    """
    return {
        "02a": BcsString(field_name, 20),
        "02b": Int(field_name, 8),
        "02c": Int(field_name, 8),
        "02d": DecimalFloat(field_name, 8),
        "02e": DecimalFloat(field_name, 8),
        "02f": DecimalFloat(field_name, 8),
        "02g": DecimalFloat(field_name, 8),
        "02h": DecimalFloat(field_name, 8),
        "02i": YNBool(field_name),
        "03a": BcsString(field_name, 2),
        "03b": DecimalFloat(field_name, 9),
        "03c": DecimalFloat(field_name, 9),
        "03d": FlexFloat(field_name, 12),
        "03e": FlexFloat(field_name, 12),
        "03f": FlexFloat(field_name, 12),
        "03g": DecimalFloat(field_name, 9),
        "03h": FlexFloat(field_name, 12),
        "03i": FlexFloat(field_name, 12),
        "03j": FlexFloat(field_name, 12),
        "03k": FlexFloat(field_name, 12),
        "03l": IsoDate(field_name),
        "04a": BcsString(field_name, 15),
        "04b": BcsString(field_name, 3),
        "04c": Int(field_name, 8),
        "04d": Int(field_name, 8),
        "04e": Int(field_name, 8),
        "04f": Int(field_name, 8),
        "04g": DecimalFloat(field_name, 10),
        "04h": DecimalFloat(field_name, 10),
        "04i": Int(field_name, 8),
        "04j": Int(field_name, 8),
        "04k": Int(field_name, 1),
        "04l": FlexFloat(field_name, 12),
        "04m": FlexFloat(field_name, 12),
        "04n": FlexFloat(field_name, 12),
        "04o": FlexFloat(field_name, 12),
        "04p": FlexFloat(field_name, 12),
        "04q": FlexFloat(field_name, 12),
        "04r": FlexFloat(field_name, 12),
        "04s": FlexFloat(field_name, 12),
        "05a": DecimalFloat(field_name, 12),
        "05b": Int(field_name, 8),
        "05c": Int(field_name, 8),
        "06a": DecimalFloat(field_name, 11),
        "06b": DecimalFloat(field_name, 12),
        "06c": DecimalFloat(field_name, 11),
        "06d": DecimalFloat(field_name, 8),
        "06e": DecimalFloat(field_name, 8),
        "06f": DecimalFloat(field_name, 8),
        "07a": Int(field_name, 1),
        "07b": DecimalFloat(field_name, 10),
        "07c": DecimalFloat(field_name, 9),
        "07d": DecimalFloat(field_name, 10),
        "07e": YNBool(field_name),
        "07f": DecimalFloat(field_name, 9),
        "07g": DecimalFloat(field_name, 9),
        "07h": DecimalFloat(field_name, 10),
        "08a": DecimalFloat(field_name, 10),
        "08b": DecimalFloat(field_name, 10),
        "08c": DecimalFloat(field_name, 10),
        "08d": DecimalFloat(field_name, 10),
        "08e": DecimalFloat(field_name, 10),
        "08f": DecimalFloat(field_name, 10),
        "08g": DecimalFloat(field_name, 10),
        "08h": DecimalFloat(field_name, 10),
        "08i": DecimalFloat(field_name, 10),
        "09a": DecimalFloat(field_name, 10),
        "09b": DecimalFloat(field_name, 10),
        "09c": DecimalFloat(field_name, 10),
        "09d": DecimalFloat(field_name, 10),
        "10a": DecimalFloat(field_name, 9),
        "10b": DecimalFloat(field_name, 9),
        "10c": DecimalFloat(field_name, 9),
    }


# Module 12
time_stamp_data_set = Struct(
    TimeStampedDataSet,
    [
        BcsString("TIME_STAMP_TYPE", 3),
        PrefixedList(
            name="instances",
            count=Int("TIME_STAMP_COUNT", 4),
            body=Struct(
                TimeStampInstance,
                [
                    DecimalFloat("TIME_STAMP_TIME", 12),
                    Switch(
                        name="TIME_STAMP_VALUE",
                        get_tag=lambda ctx: ctx["TIME_STAMP_TYPE"],
                        cases=get_rules("TIME_STAMP_VALUE"),
                    ),
                ],
            ),
        ),
    ],
)

# Module 13
pixel_reference_data_set = Struct(
    PixelReferencedDataSet,
    [
        BcsString("PIXEL_REFERENCE_TYPE", 3),
        PrefixedList(
            name="instances",
            count=Int("PIXEL_REFERENCE_COUNT", 4),
            body=Struct(
                PixelReferenceInstance,
                [
                    DecimalFloat("PIXEL_REFERENCE_ROW", 8),
                    DecimalFloat("PIXEL_REFERENCE_COLUMN", 8),
                    Switch(
                        name="PIXEL_REFERENCE_VALUE",
                        get_tag=lambda ctx: ctx["PIXEL_REFERENCE_TYPE"],
                        cases=get_rules("PIXEL_REFERENCE_VALUE"),
                    ),
                ],
            ),
        ),
    ],
)


# Module 14
uncertainty_data = Struct(
    Uncertainty,
    [
        BcsString("UNCERTAINTY_FIRST_TYPE", 11),
        Dashable(BcsString("UNCERTAINTY_SECOND_TYPE", 11)),
        FlexFloat("UNCERTAINTY_VALUE", 10),
    ],
)


@dataclass
class AdditionalParameterList(Combinator[list[bytes]]):
    """Handle the dynamic byte size of Module 15 'Additional Parameters'"""

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> list[bytes]:
        size = Int("PARAMETER_SIZE", 3).parse(fd, ctx)
        count = Int("PARAMETER_COUNT", 4).parse(fd, ctx)

        return [
            FixedBytes("PARAMETER_VALUE", size).parse(fd, ctx)
            for _ in ctx.iterate(range(count))
        ]

    @override
    def _emit(self, value: list[bytes], *, ctx: EmitContext) -> list[Item]:
        size = len(value[0]) if value else 0
        count = len(value)

        for v in value:
            if len(v) != size:
                msg = "All parameter values must be the same size!"
                raise ValueError(msg)

        fields: list[Item] = []
        fields.extend(Int("PARAMETER_SIZE", 3).to_fields(size, ctx))
        fields.extend(Int("PARAMETER_COUNT", 4).to_fields(count, ctx))
        for v in ctx.iterate(value):
            fields.extend(FixedBytes("PARAMETER_VALUE", size).to_fields(v, ctx))

        return fields


additional_parameter = Struct(
    AdditionalParameter,
    [
        BcsString("PARAMETER_NAME", 25),
        AdditionalParameterList(name="values"),
    ],
)

sensrb = Struct(
    SENSRB,
    [
        Constant(BcsString("CETAG", 6), "SENSRB"),
        SizedBlock(
            length_rule=Int("CEL", 5),
            body=[
                Optional(
                    name="general_data",
                    condition=YNBool("GENERAL_DATA"),
                    rule=general_data,
                ),
                Optional(
                    name="sensor_array",
                    condition=YNBool("SENSOR_ARRAY_DATA"),
                    rule=sensor_array_data,
                ),
                Optional(
                    name="calibration",
                    condition=YNBool("SENSOR_CALIBRATION_DATA"),
                    rule=calibration_data,
                ),
                Optional(
                    name="image_formation",
                    condition=YNBool("IMAGE_FORMATION_DATA"),
                    rule=image_formation_data,
                ),
                reference_data,
                sensor_position,
                Optional(
                    name="euler_angles",
                    condition=YNBool("ATTITUDE_EULER_ANGLES"),
                    rule=euler_angles,
                ),
                Optional(
                    name="unit_vectors",
                    condition=YNBool("ATTITUDE_UNIT_VECTORS"),
                    rule=unit_vectors,
                ),
                Optional(
                    name="quaternion",
                    condition=YNBool("ATTITUDE_QUATERNION"),
                    rule=quaternion_spec,
                ),
                Optional(
                    name="velocity",
                    condition=YNBool("SENSOR_VELOCITY_DATA"),
                    rule=sensor_velocity_spec,
                ),
                PrefixedList(
                    name="point_sets",
                    count=Int("POINT_SET_DATA", 2),
                    body=point_set_spec,
                ),
                PrefixedList(
                    name="time_stamped_data",
                    count=Int("TIME_STAMPED_DATA_SETS", 2),
                    body=time_stamp_data_set,
                ),
                PrefixedList(
                    name="pixel_referenced_data",
                    count=Int("PIXEL_REFERENCED_DATA_SETS", 2),
                    body=pixel_reference_data_set,
                ),
                PrefixedList(
                    name="uncertainty_data",
                    count=Int("UNCERTAINTY_DATA", 3),
                    body=uncertainty_data,
                ),
                PrefixedList(
                    name="additional_parameters",
                    count=Int("ADDITIONAL_PARAMETER_DATA", 3),
                    body=additional_parameter,
                ),
            ],
        ),
    ],
)

register_tre("SENSRB", sensrb)
