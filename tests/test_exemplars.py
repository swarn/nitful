import os
from pathlib import Path

import pytest

from .helpers import run_strict_roundtrip, run_trace_symmetry  # pyrefly: ignore

EXEMPLAR_DIR_ENV = os.environ.get("NITFUL_EXEMPLAR_DIR")
EXEMPLAR_DIR = Path(EXEMPLAR_DIR_ENV) if EXEMPLAR_DIR_ENV else Path()

if not EXEMPLAR_DIR or not EXEMPLAR_DIR.exists():
    pytest.skip(
        "NITFUL_EXEMPLAR_DIR is not set or does not exist. Skipping exemplar tests.",
        allow_module_level=True,
    )


def get_exemplar_files():
    return [
        pytest.param(filepath, id=str(filepath.relative_to(EXEMPLAR_DIR)))
        for filepath in sorted(EXEMPLAR_DIR.rglob("*"))
        if filepath.is_file()
        and filepath.suffix.lower() in [".ntf", ".nsf"]
        and not filepath.name.startswith(".")
    ]


@pytest.mark.parametrize("filepath", get_exemplar_files())
def test_exemplar_file(filepath: Path):
    run_trace_symmetry(filepath)
    run_strict_roundtrip(filepath)
