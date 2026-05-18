"""Round-trip tests

Verify the parsing and serialization logic by parsing an input file into a
NitfFile object, then serializing the object: a "round trip."
"""

from pathlib import Path

import pytest

from .helpers import run_roundtrip  # pyrefly: ignore

TEST_DATA_DIR = Path(__file__).parent / "data"


# Files which should round-trip as byte-identical.
STRICT_FILES = list((TEST_DATA_DIR / "strict").glob("*.ntf"))

# Files which may change during round-trip, because the input file is not
# spec-compliant or because the fields can have different representations.
CANONICAL_FILES = list((TEST_DATA_DIR / "canonical").glob("*.ntf"))

ALL_FILES = STRICT_FILES + CANONICAL_FILES


@pytest.mark.parametrize("filepath", STRICT_FILES, ids=lambda p: p.name)
def test_strict_roundtrip(filepath: Path) -> None:
    run_roundtrip(filepath, strict=True)


@pytest.mark.parametrize("filepath", CANONICAL_FILES, ids=lambda p: p.name)
def test_canonical_roundtrip(filepath: Path):
    run_roundtrip(filepath, strict=False)
