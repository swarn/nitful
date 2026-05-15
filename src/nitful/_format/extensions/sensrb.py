import copy
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


# Modules 12 and 13 specify fields by their name in the NITF spec: "02a",
# "03f", etc. Then, they list values that match the size and type of that
# field. This dict is a registry of SENSRB fields.
_field_registry: dict[str, Rule[Any]] = {}


def idx[R: Rule[Any]](code: str, rule: R) -> R:
    """Register a rule and return it unmodified for the spec."""
    if code in _field_registry:
        msg = f"Duplicate SENSRB index: {code}"
        raise ValueError(msg)

    _field_registry[code] = rule
    return rule


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
        Nullable(IsoDate("GENERATION_DATE")),
        Nullable(HMSeconds("GENERATION_TIME", 10)),
    ],
)

# Module 2
sensor_array_data = Struct(
    SensorArrayData,
    [
        idx("02a", BcsString("DETECTION", 20)),
        idx("02b", Int("ROW_DETECTORS", 8, positive)),
        idx("02c", Int("COLUMN_DETECTORS", 8, positive)),
        idx("02d", Dashable(DecimalFloat("ROW_METRIC", 8, positive))),
        idx("02e", Dashable(DecimalFloat("COLUMN_METRIC", 8, positive))),
        idx("02f", Dashable(DecimalFloat("FOCAL_LENGTH", 8, positive))),
        idx("02g", Dashable(DecimalFloat("ROW_FOV", 8, nonnegative))),
        idx("02h", Dashable(DecimalFloat("COLUMN_FOV", 8, nonnegative))),
        idx("02i", YNBool("CALIBRATED")),
    ],
)

# Module 3
calibration_data = Struct(
    CalibrationData,
    [
        idx("03a", BcsStringEnum("CALIBRATION_UNIT", 2, enum=CalibrationUnit)),
        idx("03b", Dashable(DecimalFloat("PRINCIPAL_POINT_OFFSET_X", 9))),
        idx("03c", Dashable(DecimalFloat("PRINCIPAL_POINT_OFFSET_Y", 9))),
        idx("03d", Dashable(FlexFloat("RADIAL_DISTORT_1", 12))),
        idx("03e", Dashable(FlexFloat("RADIAL_DISTORT_2", 12))),
        idx("03f", Dashable(FlexFloat("RADIAL_DISTORT_3", 12))),
        idx("03g", Dashable(DecimalFloat("RADIAL_DISTORT_LIMIT", 9, nonnegative))),
        idx("03h", Dashable(FlexFloat("DECENT_DISTORT_1", 12))),
        idx("03i", Dashable(FlexFloat("DECENT_DISTORT_2", 12))),
        idx("03j", Dashable(FlexFloat("AFFINITY_DISTORT_1", 12))),
        idx("03k", Dashable(FlexFloat("AFFINITY_DISTORT_2", 12))),
        idx("03l", Dashable(IsoDate("CALIBRATION_DATE"))),
    ],
)

# Module 4
image_formation_data = Struct(
    ImageFormationData,
    [
        idx("04a", BcsString("METHOD", 15)),
        idx("04b", BcsString("MODE", 3)),
        idx("04c", Int("ROW_COUNT", 8)),
        idx("04d", Int("COLUMN_COUNT", 8)),
        idx("04e", Int("ROW_SET", 8)),
        idx("04f", Int("COLUMN_SET", 8)),
        idx("04g", DecimalFloat("ROW_RATE", 10)),
        idx("04h", DecimalFloat("COLUMN_RATE", 10)),
        idx("04i", Int("FIRST_PIXEL_ROW", 8)),
        idx("04j", Int("FIRST_PIXEL_COLUMN", 8)),
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
        idx("05a", Nullable(DecimalFloat("REFERENCE_TIME", 12))),
        idx("05b", Nullable(Int("REFERENCE_ROW", 8))),
        idx("05c", Nullable(Int("REFERENCE_COLUMN", 8))),
    ],
)

# Module 6
sensor_position = Struct(
    name="position",
    model_cls=PositionData,
    rules=[
        idx("06a", DecimalFloat("LATITUDE_OR_X", 11)),
        idx("06b", Nullable(DecimalFloat("LONGITUDE_OR_Y", 12))),
        idx("06c", Nullable(DecimalFloat("ALTITUDE_OR_Z", 11))),
        idx("06d", DecimalFloat("SENSOR_X_OFFSET", 8)),
        idx("06e", DecimalFloat("SENSOR_Y_OFFSET", 8)),
        idx("06f", DecimalFloat("SENSOR_Z_OFFSET", 8)),
    ],
)

# Module 7
euler_angles = Struct(
    EulerAngles,
    [
        idx("07a", Int("SENSOR_ANGLE_MODEL", 1, one_of(1, 2, 3))),
        idx("07b", DecimalFloat("SENSOR_ANGLE_1", 10, in_range(-180.0, 180.0))),
        idx("07c", DecimalFloat("SENSOR_ANGLE_2", 9, in_range(-90.0, 90.0))),
        idx("07d", DecimalFloat("SENSOR_ANGLE_3", 10, in_range(-180.0, 180.0))),
        idx("07e", YNBool("PLATFORM_RELATIVE")),
        idx("07f", Blankable(DecimalFloat("PLATFORM_HEADING", 9, in_range(0, 360)))),
        idx("07g", Blankable(DecimalFloat("PLATFORM_PITCH", 9, in_range(-90, 90)))),
        idx("07h", Blankable(DecimalFloat("PLATFORM_ROLL", 10, in_range(-180, 180)))),
    ],
)


# Module 8
unit_vectors = Struct(
    UnitVectors,
    [
        idx("08a", DecimalFloat("ICX_NORTH_OR_X", 10, in_range(-1.0, 1.0))),
        idx("08b", DecimalFloat("ICX_EAST_OR_Y", 10, in_range(-1.0, 1.0))),
        idx("08c", DecimalFloat("ICX_DOWN_OR_Z", 10, in_range(-1.0, 1.0))),
        idx("08d", DecimalFloat("ICY_NORTH_OR_X", 10, in_range(-1.0, 1.0))),
        idx("08e", DecimalFloat("ICY_EAST_OR_Y", 10, in_range(-1.0, 1.0))),
        idx("08f", DecimalFloat("ICY_DOWN_OR_Z", 10, in_range(-1.0, 1.0))),
        idx("08g", DecimalFloat("ICZ_NORTH_OR_X", 10, in_range(-1.0, 1.0))),
        idx("08h", DecimalFloat("ICZ_EAST_OR_Y", 10, in_range(-1.0, 1.0))),
        idx("08i", DecimalFloat("ICZ_DOWN_OR_Z", 10, in_range(-1.0, 1.0))),
    ],
)

# Module 9
quaternion_spec = Struct(
    Quaternion,
    [
        idx("09a", DecimalFloat("ATTITUDE_Q1", 10, in_range(-1.0, 1.0))),
        idx("09b", DecimalFloat("ATTITUDE_Q2", 10, in_range(-1.0, 1.0))),
        idx("09c", DecimalFloat("ATTITUDE_Q3", 10, in_range(-1.0, 1.0))),
        idx("09d", DecimalFloat("ATTITUDE_Q4", 10, in_range(-1.0, 1.0))),
    ],
)

# Module 10
sensor_velocity_spec = Struct(
    SensorVelocity,
    [
        idx("10a", DecimalFloat("VELOCITY_NORTH_OR_X", 9)),
        idx("10b", DecimalFloat("VELOCITY_EAST_OR_Y", 9)),
        idx("10c", DecimalFloat("VELOCITY_DOWN_OR_Z", 9)),
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


def get_switch_cases(new_name: str) -> dict[str, Rule[Any]]:
    """Deep copy registered rules and patch their names for the Switch."""

    # Recursively change the name of wrapped rules.
    def _patch(node: Any) -> Any:
        if hasattr(node, "name"):
            node.name = new_name

        if hasattr(node, "rule"):
            _patch(node.rule)

        return node

    return {
        code: _patch(copy.deepcopy(original_rule))
        for code, original_rule in _field_registry.items()
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
                        cases=get_switch_cases("TIME_STAMP_VALUE"),
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
                        cases=get_switch_cases("PIXEL_REFERENCE_VALUE"),
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
