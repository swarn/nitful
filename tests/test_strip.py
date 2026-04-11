import io
from pathlib import Path

from nitful import read, strip
from nitful.core.image import DeferredImageData

TEST_DATA_DIR = Path(__file__).parent / "data"

fake_pixels = bytes.fromhex("DEADBEEF")


def test_strip_replaces_image_data():
    input_file = TEST_DATA_DIR / "strict" / "two_images_jpeg.ntf"

    # The original file doesn't have the fake data yet.
    original_bytes = input_file.read_bytes()
    assert fake_pixels not in original_bytes, "Test image already stripped."

    # The stripped file does have the fake data.
    out_stream = io.BytesIO()
    with open(input_file, "rb") as in_stream:
        strip(in_stream, out_stream)
    stripped_bytes = out_stream.getvalue()
    assert fake_pixels in stripped_bytes, "Output is missing fake pixels"

    # The stripped file parses correctly.
    out_stream.seek(0)
    parsed_file = read(out_stream)
    assert len(parsed_file.image_segments) == 2
    img_data = parsed_file.image_segments[0].data
    assert type(img_data) is DeferredImageData
    assert img_data.length == 4


def test_strip_preserves_metadata():
    """Test that non-spec-compliant metadata is preserved as-is."""
    input_file = TEST_DATA_DIR / "canonical" / "SENSRB.ntf"

    # These are fields in the input image that the parser will read, but will
    # be replace with spec-compliant values if serializing from the model.
    known_bad = [
        b" m",  # should be 'SI'
        b"deg",  # should be capitalized
        b"         470",  # should be zero-padded
    ]

    # Make sure the test file hasn't been changed.
    original_bytes = input_file.read_bytes()
    for b in known_bad:
        assert b in original_bytes, "Test data is missing expected bytes."

    out_stream = io.BytesIO()
    with open(input_file, "rb") as in_stream:
        strip(in_stream, out_stream)

    # Strip operated without correcting the fields.
    stripped_bytes = out_stream.getvalue()
    for b in known_bad:
        assert b in stripped_bytes, "Strip function modified metadata bytes."

    assert fake_pixels in stripped_bytes, "Output is missing fake pixels"
