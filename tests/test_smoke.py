"""
A minimal smoke test: parse and render every bundled sample shape and check
nothing crashes and the output looks structurally sane. This is not a
pixel-perfect regression test (SVG output legitimately varies with the
tuning parameters), just a sanity net for contributors.

Run with: pytest tests/  (or: python -m pytest tests/)
"""
import glob
import os

import pytest

from fla2svg import parse_shape, render_svg
from fla2svg.shape import parse_shape_file

SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "samples")
SAMPLE_FILES = sorted(glob.glob(os.path.join(SAMPLES_DIR, "*.bin")))


@pytest.mark.skipif(not SAMPLE_FILES, reason="no sample .bin files bundled")
@pytest.mark.parametrize("path", SAMPLE_FILES)
def test_parse_and_render(path):
    shape = parse_shape_file(path)
    assert shape is not None, f"failed to parse {path}"
    assert shape.edges, f"no edges parsed from {path}"

    svg = render_svg(shape)
    assert svg.startswith("<svg")
    assert svg.endswith("</svg>")
    assert "viewBox=" in svg


def test_empty_data_returns_none():
    assert parse_shape(b"not a real shape stream") is None
