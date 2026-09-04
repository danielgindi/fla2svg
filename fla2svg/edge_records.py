"""
The reverse-engineered binary layout of one "edge record" -- the atomic
drawing instruction Flash's binary format uses for vector artwork.

Each record starts with a single flags byte:

    bit 7   NO_SELECTION   (style change carries no from/to selection info)
    bit 6   HAS_STYLES     (a fill0/fill1/stroke style change is encoded here)
    bits 4-5 TO_MASK       coordinate encoding for the mandatory "to" point
    bits 2-3 CONTROL_MASK  coordinate encoding for an optional control point
    bits 0-1 FROM_MASK     coordinate encoding for an optional "from" point

A zero TO_MASK is not a valid record -- every real edge must move
*somewhere* -- so it doubles as the end-of-stream sentinel.

FROM, CONTROL and TO are not absolute coordinates: each is a *delta* from
wherever the pen currently is (FROM moves the pen without drawing, as an
explicit "moveto"; CONTROL and TO draw a curve/line segment and leave the
pen at the new TO position). All three encodings share one 2-bit "which
coordinate format" value:

    1 = BYTE_ENC   8.8 fixed point, 4 bytes total (2 per axis)
    2 = FLOAT_ENC  24.8 fixed point, 8 bytes total (4 per axis)
    3 = SHORT_ENC  signed 16-bit half-units, 4 bytes total (2 per axis)

When HAS_STYLES is set, a style-change block of 3 or 6 bytes (depending on
NO_SELECTION) follows immediately with the new stroke/fill0/fill1 style
ids -- these ids stay in effect for every subsequent edge until the next
style change.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from .model import Edge, Point, Subpath

FROM_MASK = 0x03
CONTROL_MASK = 0x0C
TO_MASK = 0x30
HAS_STYLES = 0x40
NO_SELECTION = 0x80

BYTE_ENC = 1
FLOAT_ENC = 2
SHORT_ENC = 3

_ENC_SIZE = {BYTE_ENC: 4, FLOAT_ENC: 8, SHORT_ENC: 4}


def _read_short_xy(data: bytes, p: int):
    x = _signed16(data, p) / 2.0
    y = _signed16(data, p + 2) / 2.0
    return x, y, p + 4


def _signed16(data: bytes, p: int) -> int:
    import struct
    return struct.unpack_from("<h", data, p)[0]


def _read_byte_xy(data: bytes, p: int):
    # 8.8 fixed point: a fractional byte followed by a signed whole-unit byte.
    frac_x, whole_x = data[p], _signed8(data[p + 1])
    frac_y, whole_y = data[p + 2], _signed8(data[p + 3])
    x = whole_x + frac_x / 256.0
    y = whole_y + frac_y / 256.0
    return x, y, p + 4


def _signed8(b: int) -> int:
    return b - 256 if b >= 128 else b


def _read_float_xy(data: bytes, p: int):
    # 24.8 fixed point: a fractional byte followed by a 24-bit signed whole part.
    frac_x = data[p]
    whole_x = _signed24(data[p + 1] | (data[p + 2] << 8) | (data[p + 3] << 16))
    frac_y = data[p + 4]
    whole_y = _signed24(data[p + 5] | (data[p + 6] << 8) | (data[p + 7] << 16))
    x = whole_x + frac_x / 256.0
    y = whole_y + frac_y / 256.0
    return x, y, p + 8


def _signed24(v: int) -> int:
    return v - 0x1000000 if v & 0x800000 else v


def _read_xy(data: bytes, p: int, encoding: int):
    if encoding == SHORT_ENC:
        return _read_short_xy(data, p)
    if encoding == BYTE_ENC:
        return _read_byte_xy(data, p)
    if encoding == FLOAT_ENC:
        return _read_float_xy(data, p)
    raise ValueError(f"unknown coordinate encoding {encoding}")


class EdgeRecord:
    """One parsed edge record. `end` is the byte offset immediately after
    it, i.e. where the next record (if any) begins."""

    __slots__ = ("stroke", "fill0", "fill1", "from_delta", "control_delta",
                 "to_delta", "end")

    def __init__(self, stroke, fill0, fill1, from_delta, control_delta, to_delta, end):
        self.stroke = stroke
        self.fill0 = fill0
        self.fill1 = fill1
        self.from_delta = from_delta
        self.control_delta = control_delta
        self.to_delta = to_delta
        self.end = end


def parse_edge_record(data: bytes, pos: int, limit: int,
                       general_line_byte: bool = True) -> Optional[EdgeRecord]:
    """Parse one edge record at byte offset `pos`.

    `general_line_byte` controls whether a straight (no-control) edge is
    followed by a trailing marker byte -- true for FLA format CS3 and
    later, false for older formats (Flash 8 / MX 2004) which omit it.
    Returns None at end-of-stream (a record with no TO field is not valid).
    """
    if pos >= limit:
        return None
    flags = data[pos]
    to_bits = flags & TO_MASK
    if to_bits == 0:
        return None  # TO is mandatory for every real edge record
    from_bits = flags & FROM_MASK
    control_bits = flags & CONTROL_MASK
    has_styles = bool(flags & HAS_STYLES)
    no_selection = bool(flags & NO_SELECTION)
    q = pos + 1

    stroke = fill0 = fill1 = None
    if has_styles:
        needed = 3 if no_selection else 6
        if q + needed > limit:
            return None
        if no_selection:
            stroke, fill0, fill1 = data[q], data[q + 1], data[q + 2]
            q += 3
        else:
            # Each id is followed by one reserved/unused byte.
            stroke, fill0, fill1 = data[q], data[q + 2], data[q + 4]
            q += 6

    from_delta = None
    if from_bits:
        size = _ENC_SIZE[from_bits]
        if q + size > limit:
            return None
        fx, fy, q = _read_xy(data, q, from_bits)
        from_delta = (fx, fy)

    control_delta = None
    if control_bits:
        enc = control_bits >> 2
        size = _ENC_SIZE[enc]
        if q + size > limit:
            return None
        cx, cy, q = _read_xy(data, q, enc)
        control_delta = (cx, cy)

    to_enc = to_bits >> 4
    size = _ENC_SIZE[to_enc]
    if q + size > limit:
        return None
    tx, ty, q = _read_xy(data, q, to_enc)

    if general_line_byte and control_delta is None:
        if q >= limit:
            return None
        q += 1  # trailing marker byte, value unused by this tool

    return EdgeRecord(stroke, fill0, fill1, from_delta, control_delta, (tx, ty), q)


def find_edge_stream_start(data: bytes, search_start: int, search_len: int = 400,
                            general_line_byte: bool = True) -> Optional[int]:
    """Scan forward from `search_start` for the first byte offset that
    parses as a plausible first edge record (a style change naming small,
    sane fill/stroke ids). Fill/line style tables precede the edge stream
    but have no fixed length, so this heuristic is how we find the boundary.
    """
    limit = len(data)
    for candidate in range(search_start, min(search_start + search_len, limit)):
        rec = parse_edge_record(data, candidate, limit, general_line_byte)
        if rec is None:
            continue
        if rec.stroke is None and rec.fill0 is None and rec.fill1 is None:
            continue
        if rec.fill0 is not None and rec.fill0 > 250:
            continue
        if rec.fill1 is not None and rec.fill1 > 250:
            continue
        return candidate
    return None


def _probe_length(data: bytes, start: int, general_line_byte: bool,
                   limit: Optional[int] = None) -> Tuple[int, int]:
    """Count consecutive valid edge records from `start`. Used to
    auto-detect `general_line_byte` for a given file's format version."""
    n = len(data) if limit is None else limit
    pos = start
    count = 0
    while True:
        rec = parse_edge_record(data, pos, n, general_line_byte)
        if rec is None:
            break
        pos = rec.end
        count += 1
        if count > 200_000:
            break
    return count, pos


def detect_general_line_byte(data: bytes, start: int, limit: Optional[int] = None) -> bool:
    """Try both format conventions and keep whichever consumes more of the
    buffer (ties favor True, the newer/more common convention)."""
    _, end_true = _probe_length(data, start, True, limit)
    _, end_false = _probe_length(data, start, False, limit)
    return end_false <= end_true


def parse_edge_stream(data: bytes, start: int, general_line_byte: bool = True,
                       limit: Optional[int] = None
                       ) -> Tuple[List[Subpath], int, List[Edge]]:
    """Decode a maximal run of edge records starting at `start` into
    (subpaths, end_pos, edges).

    `subpaths` groups records purely by pen-continuity (a new one starts
    whenever a FROM delta appears, i.e. a "moveto"); it's a cheap
    approximation good enough for bounding boxes but NOT reliable for
    stroke rendering (see `strokes.py`).

    `edges` is the flat, authoritative list: every single edge with its
    own fill0/fill1/stroke exactly as active at that edge (a style can
    change mid-subpath without a new moveto). Fill-region reconstruction
    in `faces.py` must use this list, not `subpaths`.
    """
    n = len(data) if limit is None else limit
    pos = start
    subpaths: List[Subpath] = []
    edges: List[Edge] = []
    current: Optional[Subpath] = None
    pen: Point = (0.0, 0.0)
    stroke = fill0 = fill1 = 0
    count = 0

    while True:
        rec = parse_edge_record(data, pos, n, general_line_byte)
        if rec is None:
            break

        if rec.stroke is not None:
            stroke, fill0, fill1 = rec.stroke, rec.fill0, rec.fill1

        if rec.from_delta is not None:
            pen = (pen[0] + rec.from_delta[0], pen[1] + rec.from_delta[1])
            current = Subpath(start=pen, segments=[], fill0=fill0, fill1=fill1, stroke=stroke)
            subpaths.append(current)
        elif current is None:
            current = Subpath(start=pen, segments=[], fill0=fill0, fill1=fill1, stroke=stroke)
            subpaths.append(current)

        segment_start = pen
        if rec.control_delta is not None:
            cx = pen[0] + rec.control_delta[0]
            cy = pen[1] + rec.control_delta[1]
            ex = pen[0] + rec.to_delta[0]
            ey = pen[1] + rec.to_delta[1]
            current.segments.append(("curve", cx, cy, ex, ey))
            edges.append(Edge(start=segment_start, end=(ex, ey), control=(cx, cy),
                               fill0=fill0, fill1=fill1, stroke=stroke))
            pen = (ex, ey)
        else:
            ex = pen[0] + rec.to_delta[0]
            ey = pen[1] + rec.to_delta[1]
            current.segments.append(("line", ex, ey))
            edges.append(Edge(start=segment_start, end=(ex, ey), control=None,
                               fill0=fill0, fill1=fill1, stroke=stroke))
            pen = (ex, ey)

        pos = rec.end
        count += 1
        if count > 200_000:
            break

    return subpaths, pos, edges
