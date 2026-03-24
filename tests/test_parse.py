from pathlib import Path

import biif

TEST_DATA_DIR = Path(__file__).parent / "data"


def test_parse_minimal_file():
    """Parse a NITF file."""

    test_file = TEST_DATA_DIR / "mock.ntf"

    assert test_file.exists(), f"Test file not found at {test_file}"

    nitf = biif.load(test_file)

    assert nitf.FHDR == "NITF"
    assert nitf.FVER == "02.10"

    assert len(nitf.image_segments) == 1
    assert nitf.image_segments[0].IREP == "MONO"

    dump_str = biif.dump(nitf)
    assert "FHDR" in dump_str
    assert "QUAL_FLAG_EPH" in dump_str

    print(nitf)

