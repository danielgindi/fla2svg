"""
Top-level entry point for decoding one stream's worth of shape data.
"""
from __future__ import annotations

from typing import Optional

from .binary_reader import ByteReader, find_class_start
from .edge_records import detect_general_line_byte, find_edge_stream_start, parse_edge_stream
from .model import Shape
from .styles import parse_styles

# Most shapes are serialized as a CPicShape object. A few (seen so far:
# shapes with no separate line/fill-style table of their own, e.g. a
# timeline's background) are embedded directly inside their parent
# CPicFrame instead -- falling back to that class tag still finds a valid
# fills/lines/edges layout at the same relative position.
_SHAPE_CLASS_NAMES = ("CPicShape", "CPicFrame")

# Bytes of fixed, currently-unused header fields between the shape-flag
# byte and the start of the fill-style table (bounding box, transform,
# and similar bookkeeping fields we don't need for a static render).
_HEADER_SKIP_BYTES = 41


def parse_shape(data: bytes, source_stream: str = "") -> Optional[Shape]:
    """Decode one shape stream's fill/line styles and vector edge data.

    Returns None if none of the recognized class tags are found, or if no
    plausible edge stream follows the style tables (either or both usually
    means `data` isn't actually a drawable shape stream -- e.g. it's a
    stream with no vector content).
    """
    start = None
    for class_name in _SHAPE_CLASS_NAMES:
        start = find_class_start(data, class_name)
        if start is not None:
            break
    if start is None:
        return None

    reader = ByteReader(data, start)
    reader.skip(1)  # shape-flag byte, not currently used
    reader.skip(_HEADER_SKIP_BYTES)

    fills, lines = parse_styles(reader)

    general_line_byte = detect_general_line_byte(data, reader.pos)
    edge_stream_start = find_edge_stream_start(data, reader.pos, search_len=200,
                                                general_line_byte=general_line_byte)
    if edge_stream_start is None:
        return None

    subpaths, _end, edges = parse_edge_stream(
        data, edge_stream_start, general_line_byte=general_line_byte
    )

    if not fills and not lines:
        # A real shape always defines at least one fill or line style for
        # its edges to reference. Zero of each usually means the class-tag
        # scan landed on unrelated bytes that only happened to resemble one
        # (this shows up on "Contents"/"Page N" streams sometimes, which
        # carry timeline/frame structure rather than inline shape data) --
        # treat it the same as "no shape found here".
        return None

    return Shape(fills=fills, lines=lines, subpaths=subpaths, edges=edges,
                 source_stream=source_stream)


def parse_shape_file(path: str) -> Optional[Shape]:
    """Convenience wrapper: parse a shape from an already-extracted
    ``*.bin`` stream file on disk."""
    with open(path, "rb") as f:
        data = f.read()
    return parse_shape(data, source_stream=path)
