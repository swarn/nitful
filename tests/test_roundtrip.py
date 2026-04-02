import io
from pathlib import Path

import pytest

from nitful import ParseError, SerializeError, load, write
from nitful._dsl.rules import Item
from nitful._format.file import to_fields

TEST_DATA_DIR = Path(__file__).parent / "data"
TEST_FILES = list(TEST_DATA_DIR.rglob("*.ntf"))


@pytest.mark.parametrize("filepath", TEST_FILES, ids=lambda p: p.name)
def test_full_nitf_roundtrip(filepath: Path) -> None:
    original_bytes = filepath.read_bytes()

    try:
        nitf_file = load(filepath)
    except ParseError as e:
        pytest.fail(f"Parsing failed for {filepath.name}:\n{e}")

    dest_fd = io.BytesIO()

    try:
        write(nitf_file, dest_fd)
    except SerializeError as e:
        pytest.fail(f"Emitting failed for {filepath.name}:\n{e}")

    new_bytes = dest_fd.getvalue()

    if original_bytes == new_bytes:
        return

    fields = to_fields(nitf_file)
    offset_to_field: dict[int, Item] = {}
    current_offset = 0
    for f in fields:
        field_len = len(f.value)

        for i in range(current_offset, current_offset + field_len):
            offset_to_field[i] = f

        current_offset += field_len

    for i, (orig, new) in enumerate(zip(original_bytes, new_bytes)):
        if orig != new:
            field = offset_to_field[i]

            msg = (
                f"Byte mismatch at offset {i} (0x{i:04x}) "
                f"inside field {field.name}: {field.value!r}\n"
                f"Expected: 0x{orig:02x} ({bytes([orig])!r})\n"
                f"Got:      0x{new:02x} ({bytes([new])!r})"
            )
            pytest.fail(msg)

    final_field = offset_to_field.get(len(new_bytes)-1, "UNKNOWN")
    assert len(original_bytes) == len(new_bytes), (
        f"Length mismatch: Original is {len(original_bytes)} bytes, "
        f"New is {len(new_bytes)} bytes, "
        f"ending with field {final_field}"
    )
