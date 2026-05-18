import io
from itertools import zip_longest
from pathlib import Path

import pytest

from nitful import ParseError, SerializeError
from nitful._format.file import read_file, to_fields
from nitful.dsl.io import write_fields
from nitful.dsl.rules import ParseContext


def run_roundtrip(filepath: Path, *, strict: bool = True) -> None:
    """Test by parsing a file, serializing the resulting model, and comparing.

    If `strict` is true, check that the serialized file is identical to the
    input file. Otherwise, parse the serialized file and check that it produces
    an identical model.
    """
    with open(filepath, "rb") as fd:
        ctx = ParseContext()
        try:
            original_model = read_file(fd, ctx)
        except ParseError as e:
            pytest.fail(f"Parsing failed for {filepath.name}:\n{e}")

    parse_items = [item for (item, _) in ctx.fields]

    try:
        emit_items = to_fields(original_model)
    except SerializeError as e:
        pytest.fail(f"Emitting failed for {filepath.name}:\n{e}")

    _compare_items(parse_items, emit_items)

    if strict:
        _compare_bytes(parse_items, emit_items)
    else:
        _assert_idempotent(original_model, emit_items)


def _compare_items(parse_items, emit_items) -> None:
    """Check that the parsed and emitted Items are similar.

    There should be the same number of items, each should have the same name,
    and each should have the same size. This verifies that parsing and emitting
    are doing the same thing, while allowing differences in the generated
    bytes.
    """
    for p_item, e_item in zip_longest(parse_items, emit_items):
        if p_item is None:
            p_str = f"{parse_items[-1].name}: {parse_items[-1].value!r}\n"
            e_str = f"{e_item.name}: {e_item.value!r}\n"
            msg = (
                "More emitted fields than parsed fields.\n"
                f"  Last parsed field: {p_str}\n"
                f"  Extra emitted field: {e_str}"
            )
            pytest.fail(msg)

        if e_item is None:
            p_str = f"{p_item.name}: {p_item.value!r}\n"
            e_str = f"{emit_items[-1].name}: {emit_items[-1].value!r}\n"
            msg = (
                "More parsed fields than emitted fields.\n"
                f"  Extra parsed field: {p_str}\n"
                f"  Last emitted field: {e_str}"
            )
            pytest.fail(msg)

        assert p_item.name == e_item.name, (
            "Different field names:\n"
            f"  Parse trace expected: {p_item.name}\n"
            f"  Emit trace generated: {e_item.name}"
        )

        assert len(p_item.value) == len(e_item.value), (
            "Different field sizes:\n"
            f"  Parse trace for {p_item.name}: {p_item.value!r}\n"
            f"  Emit trace for {e_item.name}: {e_item.value!r}"
        )


def _compare_bytes(parse_items, emit_items) -> None:
    """Check that Items values are identical.

    Assumes that _compare_items already ran without error.
    """
    current_offset = 0
    for p_item, e_item in zip(parse_items, emit_items):
        if p_item.value == e_item.value:
            current_offset += len(p_item.value)
            continue

        # Ignore StreamablePayload; there's no need to compare image bytes.
        if not isinstance(p_item.value, bytes) and not isinstance(e_item.value, bytes):
            current_offset += len(p_item.value)
            continue

        if type(p_item.value) is not type(e_item.value):
            msg = (
                f"Data type mismatch in {p_item.name}: "
                f"{type(p_item.value)} vs {type(e_item.value)}"
            )
            pytest.fail(msg)

        for i, (orig, new) in enumerate(zip(p_item.value, e_item.value)):
            if orig != new:
                abs_offset = current_offset + i
                msg = (
                    f"Byte mismatch at offset {abs_offset} (0x{abs_offset:04x}) "
                    f"inside field {p_item.name}: \n"
                    f"Expected: 0x{orig:02x} ({bytes([orig])!r})\n"
                    f"Got:      0x{new:02x} ({bytes([new])!r})"
                )
                pytest.fail(msg)


def _assert_idempotent(original_model, emit_items) -> None:
    new_fd = io.BytesIO()

    write_fields(emit_items, new_fd)
    new_fd.seek(0)

    ctx = ParseContext()
    try:
        reparsed_model = read_file(new_fd, ctx)
    except ParseError as e:
        pytest.fail(f"Idempotency parsing failed. Emitted bytes are invalid:\n{e}")

    assert (
        original_model == reparsed_model
    ), "Idempotency failed: The second model does not match the original model."
