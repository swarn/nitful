from __future__ import annotations

import io
from dataclasses import dataclass

import pytest

from nitful import ParseError, SerializeError
from nitful.dsl.io import write_fields
from nitful.dsl.rules import (
    BcsString,
    Case,
    EmitContext,
    Int,
    ParseContext,
    Struct,
    Switch,
    Variant,
)


@dataclass
class MockClass:
    a: str
    b: str


# A spec with an anonymous rule mixed in
header_spec = Struct(
    model_cls=MockClass,
    rules=[
        BcsString("a", 4),
        Int("", size=4),
        BcsString("b", 4),
    ],
)


def test_struct_ignores_anonymous_rules_and_isolates_scope():
    raw_bytes = b"abcd1234efgh"

    ctx = ParseContext()
    ctx["a"] = "PARENT_VALUE"

    # The anonymous rule should read bytes, but be ignored.
    parsed = header_spec.parse(io.BytesIO(raw_bytes), ctx)
    assert parsed.a == "abcd"
    assert parsed.b == "efgh"

    # The struct-local 'a' value should pop, leaving the parent value.
    assert ctx["a"] == "PARENT_VALUE"


@dataclass
class Outer:
    a: str
    inner: Inner
    c: str


@dataclass
class Inner:
    a: str
    b: str


outer_spec = Struct(
    model_cls=Outer,
    rules=[
        BcsString("a", 2),
        Struct(
            name="inner",
            model_cls=Inner,
            rules=[
                BcsString("a", 2),
                BcsString("b", 2),
            ],
        ),
        BcsString("c", 2),
    ],
)


def test_struct_composition_roundtrip():
    raw_bytes = b"aaAABBcc"

    # Test that the inner Struct correctly builds its dataclass and passes it
    # up; also check that the outer `a` is isolate from the inner `a`.
    expected_obj = Outer(
        a="aa",
        inner=Inner(
            a="AA",
            b="BB",
        ),
        c="cc",
    )

    ctx = ParseContext()
    parsed = outer_spec.parse(io.BytesIO(raw_bytes), ctx)
    assert parsed == expected_obj

    emit_ctx = EmitContext()
    items = outer_spec.to_fields(expected_obj, emit_ctx)
    outstream = io.BytesIO()
    write_fields(items, outstream)
    assert outstream.getvalue() == raw_bytes


@dataclass
class TextClass:
    text: str


@dataclass
class NumericClass:
    num: int


variant_spec = Variant(
    tag_rule=BcsString("tag", 1),
    cases=[
        Case(
            tag="T",
            condition=TextClass,
            rule=Struct(TextClass, [BcsString("text", 3)]),
        ),
        Case(
            tag="N",
            condition=NumericClass,
            rule=Struct(NumericClass, [Int("num", 3)]),
        ),
    ],
)


def test_variant_routing_success():
    parsed = variant_spec.parse(io.BytesIO(b"TFOO"), ParseContext())
    assert parsed == TextClass("FOO")

    items = variant_spec.to_fields(NumericClass(42), EmitContext())
    emitted_bytes = b"".join(i.value for i in items)
    assert emitted_bytes == b"N042"


def test_variant_routing_failures():
    with pytest.raises(ParseError, match="Unrecognized tag 'X'"):
        variant_spec.parse(io.BytesIO(b"XFOO"), ParseContext())

    with pytest.raises(SerializeError, match="Cannot map str to a Variant branch"):
        variant_spec.to_fields("unmapped_string", EmitContext())


switch_spec = Switch(
    get_tag=lambda ctx: ctx.get("version"),
    cases={
        1: BcsString("data", 4),
        2: Int("data", 4),
    },
)


def test_switch_routing_success():
    parse_ctx = ParseContext(init={"version": 1})
    parsed = switch_spec.parse(io.BytesIO(b"TEXT"), parse_ctx)
    assert parsed == "TEXT"

    emit_ctx = EmitContext(init={"version": 2})
    items = switch_spec.to_fields(42, emit_ctx)
    assert items[0].value == b"0042"


def test_switch_routing_failures():
    parse_ctx = ParseContext(init={"version": 99})
    with pytest.raises(ParseError, match="Unrecognized tag 99 for Switch"):
        switch_spec.parse(io.BytesIO(b"TEXT"), parse_ctx)

    emit_ctx = EmitContext(init={"version": 99})
    with pytest.raises(SerializeError, match="Unrecognized tag 99 for Switch"):
        switch_spec.to_fields("TEXT", emit_ctx)
