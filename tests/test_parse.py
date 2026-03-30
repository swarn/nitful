from pathlib import Path

import nitful

TEST_DATA_DIR = Path(__file__).parent / "data"


def test_parse_minimal_file():
    """Parse a NITF file."""

    test_file = TEST_DATA_DIR / "mock.ntf"

    assert test_file.exists(), f"Test file not found at {test_file}"

    nitf = nitful.load(test_file)

    assert nitf.FHDR == "NITF"
    assert nitf.FVER == "02.10"

    for tre in nitf.UDHD:
        assert tre.CETAG is not None

    for tre in nitf.XHD:
        assert tre.CETAG is not None

    for des in nitf.data_segments:
        assert des.DESID is not None

    assert len(nitf.image_segments) == 1
    assert nitf.image_segments[0].IREP == "MONO"

    dump_str = nitful.dump(nitf)
    assert "FHDR" in dump_str
    assert "QUAL_FLAG_EPH" in dump_str
