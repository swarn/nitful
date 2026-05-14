"""Common specifications used across multiple segments or SDEs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, BinaryIO, Literal, override

from nitful.core import Security
from nitful.core.common import ECI, SecurityClass
from nitful.core.errors import DefinitionError
from nitful.dsl.rules import (
    Alias,
    BcsString,
    Combinator,
    DataclassProtocol,
    EcsString,
    EcsStringEnum,
    EmitContext,
    FixedDecimal,
    FixedFloat,
    Int,
    Item,
    ParseContext,
    Rule,
    SizedBlock,
    Struct,
    item_size,
)
from nitful.dsl.validators import in_range


def security_spec(prefix: Literal["F", "I", "S", "T", "DE", "RE"]) -> Struct[Security]:
    """Return a spec for the Security fields with the given prefix.

    The same security fields are shared by the file, image, and segment
    headers. The prefix of the field name changes depending on which of these
    the security fields appear in. This doesn't affect parsing/emitting, but
    does make printed fields match the spec documents.
    """

    return Struct(
        name="security",
        model_cls=Security,
        rules=[
            Alias("SCLAS", EcsStringEnum(f"{prefix}SCLAS", 1, enum=SecurityClass)),
            Alias("SCLSY", EcsString(f"{prefix}SCLSY", 2)),
            Alias("SCODE", EcsString(f"{prefix}SCODE", 11)),
            Alias("SCTLH", EcsString(f"{prefix}SCTLH", 2)),
            Alias("SREL", EcsString(f"{prefix}SREL", 20)),
            Alias("SDCTP", EcsString(f"{prefix}SDCTP", 2)),
            Alias("SDCDT", EcsString(f"{prefix}SDCDT", 8)),
            Alias("SDCXM", EcsString(f"{prefix}SDCXM", 4)),
            Alias("SDG", EcsString(f"{prefix}SDG", 1)),
            Alias("SDGDT", EcsString(f"{prefix}SDGDT", 8)),
            Alias("SCLTX", EcsString(f"{prefix}SCLTX", 43)),
            Alias("SCATP", EcsString(f"{prefix}SCATP", 1)),
            Alias("SCAUT", EcsString(f"{prefix}SCAUT", 40)),
            Alias("SCRSN", EcsString(f"{prefix}SCRSN", 1)),
            Alias("SSRDT", EcsString(f"{prefix}SSRDT", 8)),
            Alias("SCTLN", EcsString(f"{prefix}SCTLN", 15)),
        ],
    )


# The length of the security fields.
security_len = 167


@dataclass
class Segment[T: DataclassProtocol](Struct[T]):
    """Splits a dataclass into header and data fields.

    NITF measures the length of the segment subheader and segment data
    separately.
    """

    model_cls: type[T]
    subheader: list[Rule[Any]]
    data: list[Rule[Any]]

    rules: Sequence[Rule[Any]] = field(init=False)

    def __post_init__(self) -> None:
        # Collect the subheader and data rules into `self.rules` so the
        # `Struct` logic works unchanged.
        self.rules = self.subheader + self.data

    def emit_segment(self, value: T, ctx: EmitContext) -> tuple[list[Item], list[Item]]:
        """As _emit, but return the fields split into subheader and data fields."""
        val_dict = vars(value)

        with ctx.scope(val_dict):
            sub_fields: list[Item] = []
            for rule in self.subheader:
                child_val = val_dict.get(rule.name) if rule.name else val_dict
                sub_fields.extend(rule.to_fields(child_val, ctx))

            data_fields: list[Item] = []
            for rule in self.data:
                child_val = val_dict.get(rule.name) if rule.name else val_dict
                data_fields.extend(rule.to_fields(child_val, ctx))

            return sub_fields, data_fields


@dataclass
class ReservedExtensions(Combinator[Any]):
    """A transparent block for dynamic Reserved Field Areas (e.g., CSCSDB).

    Reads the global reserved length, the mask length, the boolean mask,
    and then selectively reads the payload for each active area.
    Unrecognized areas are preserved as raw bytes to allow round-tripping.

    Each Rule in cases must have a name. When parsing, if that reserved area is
    present, it will be assigned to that name, which will otherwise be None.
    When emitting, a reserved area will be generated for each of the items with
    non-None values.
    """

    name: str = field(default="", init=False)
    size: Rule[int]
    mask_size: Rule[int]

    # Maps a **1-based** area index to a `Rule`.
    cases: dict[int, Rule[Any]]

    # Unknown Reserved Field Areas can be parsed as raw bytes and stored for
    # correct round-tripping. `unknown_name` will be the name for the unknown
    # fields, stored as a dict[int, bytes].
    unknown_name: str = "unknown_extensions"

    def __post_init__(self) -> None:
        for i, rule in self.cases.items():
            if not rule.name:
                msg = f"Area rules must have a 'name', but area {i} does not."
                raise DefinitionError(msg)

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> None:
        total_len = self.size.parse(fd, ctx)

        # Initialize all defined areas to None in the parent scope.
        for rule in self.cases.values():
            if rule.name:
                ctx[rule.name] = None

        # Initialize the unknown entries.
        ctx[self.unknown_name] = {}

        if total_len == 0:
            return

        mask_len = self.mask_size.parse(fd, ctx)
        mask = BcsString("RESERVED_FIELD_MASK", mask_len).parse(fd, ctx)

        unknowns: dict[int, bytes] = {}

        for i in range(1, mask_len + 1):
            if mask[i - 1] == "0":
                continue

            if i not in self.cases:
                area_len = Int(f"RESERVED_LEN_AREA{i}", 9).parse(fd, ctx)
                unknowns[i] = fd.read(area_len)
                continue

            rule = self.cases[i]
            SizedBlock(Int(f"RESERVED_LEN_AREA{i}", 9), [rule]).parse(fd, ctx)

        ctx[self.unknown_name] = unknowns
        return

    @override
    def _emit(self, value: dict[str, Any], *, ctx: EmitContext) -> list[Item]:
        unknowns: dict[int, bytes] = value.get(self.unknown_name) or {}

        active_indices = set(unknowns.keys())
        for i, rule in self.cases.items():
            if rule.name and value.get(rule.name) is not None:
                active_indices.add(i)

        if not active_indices:
            return self.size.to_fields(0, ctx)

        mask_len = max(active_indices)
        mask_chars: list[str] = []
        area_fields: list[Item] = []

        for i in range(1, mask_len + 1):
            if i not in active_indices:
                mask_chars.append("0")
                continue

            mask_chars.append("1")

            if i in unknowns:
                payload_bytes = unknowns[i]
                size = len(payload_bytes)
                alen_field = Int(f"RESERVED_LEN_AREA{i}", 9).to_fields(size, ctx=ctx)
                area_fields.extend(alen_field)
                area_fields.append(Item(f"RESERVED_AREA_{i}_DATA", payload_bytes))
            else:
                rule = self.cases[i]
                block = SizedBlock(Int(f"RESERVED_LEN_AREA{i}", 9), body=[rule])
                area_fields.extend(block.to_fields(value, ctx))

        mask_str = "".join(mask_chars)
        mlen_field = self.mask_size.to_fields(mask_len, ctx)
        mask_field = BcsString("RESERVED_FIELD_MASK", mask_len).to_fields(mask_str, ctx)
        header_fields = [*mlen_field, *mask_field]

        total_len = item_size(header_fields) + item_size(area_fields)
        rfa_len_field = self.size.to_fields(total_len, ctx)

        return [*rfa_len_field, *header_fields, *area_fields]


# ECI definition used in CSATTB and CSEPHB. The TA_POLE and TB_UT values _must_
# use the Decimal module: they have more significant digits than can be
# represented with a double-precision float.
eci_spec = Struct(
    ECI,
    [
        FixedDecimal(
            "TA_POLE", 19, in_range(Decimal("2e6"), Decimal("3e6")), ndigits=11
        ),
        FixedFloat("A_POLE", 11, in_range(-1.0, 1.0), sign=True, ndigits=8),
        FixedFloat("B_POLE", 11, in_range(-1.0, 1.0), sign=True, ndigits=8),
        FixedFloat("CJ1_POLE", 11, in_range(-1.0, 1.0), sign=True, ndigits=8),
        FixedFloat("CJ2_POLE", 11, in_range(-1.0, 1.0), sign=True, ndigits=8),
        FixedFloat("DJ1_POLE", 11, in_range(-1.0, 1.0), sign=True, ndigits=8),
        FixedFloat("DJ2_POLE", 11, in_range(-1.0, 1.0), sign=True, ndigits=8),
        FixedFloat("PJ1_POLE", 10, in_range(0.0, 500.0), ndigits=6),
        FixedFloat("PJ2_POLE", 10, in_range(0.0, 500.0), ndigits=6),
        FixedFloat("E_POLE", 11, in_range(-1.0, 1.0), sign=True, ndigits=8),
        FixedFloat("F_POLE", 11, in_range(-1.0, 1.0), sign=True, ndigits=8),
        FixedFloat("GK1_POLE", 11, in_range(-1.0, 1.0), sign=True, ndigits=8),
        FixedFloat("GK2_POLE", 11, in_range(-1.0, 1.0), sign=True, ndigits=8),
        FixedFloat("HK1_POLE", 11, in_range(-1.0, 1.0), sign=True, ndigits=8),
        FixedFloat("HK2_POLE", 11, in_range(-1.0, 1.0), sign=True, ndigits=8),
        FixedFloat("PK1_POLE", 10, in_range(0.0, 500.0), ndigits=6),
        FixedFloat("PK2_POLE", 10, in_range(0.0, 500.0), ndigits=6),
        FixedDecimal("TB_UT", 19, in_range(Decimal("2e6"), Decimal("3e6")), ndigits=11),
        FixedFloat("I_UT", 12, in_range(-1.0, 1.0), sign=True, ndigits=9),
        FixedFloat("J_UT", 12, in_range(-1.0, 1.0), sign=True, ndigits=9),
        FixedFloat("KN1_UT", 12, in_range(-1.0, 1.0), sign=True, ndigits=9),
        FixedFloat("KN2_UT", 12, in_range(-1.0, 1.0), sign=True, ndigits=9),
        FixedFloat("KN3_UT", 12, in_range(-1.0, 1.0), sign=True, ndigits=9),
        FixedFloat("KN4_UT", 12, in_range(-1.0, 1.0), sign=True, ndigits=9),
        FixedFloat("LN1_UT", 12, in_range(-1.0, 1.0), sign=True, ndigits=9),
        FixedFloat("LN2_UT", 12, in_range(-1.0, 1.0), sign=True, ndigits=9),
        FixedFloat("LN3_UT", 12, in_range(-1.0, 1.0), sign=True, ndigits=9),
        FixedFloat("LN4_UT", 12, in_range(-1.0, 1.0), sign=True, ndigits=9),
        FixedFloat("PN1_UT", 10, in_range(0.0, 500.0), ndigits=6),
        FixedFloat("PN2_UT", 10, in_range(0.0, 500.0), ndigits=6),
        FixedFloat("PN3_UT", 10, in_range(0.0, 500.0), ndigits=6),
        FixedFloat("PN4_UT", 10, in_range(0.0, 500.0), ndigits=6),
    ],
)
