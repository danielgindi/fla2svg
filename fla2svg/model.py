"""
The data model shared by every stage of the pipeline: what a "shape" is,
once decoded from the binary format, before anything SVG-specific happens.

A `Shape` is one symbol's/timeline's worth of vector artwork:

* `fills` / `lines` -- the palette of fill and stroke styles used, indexed
  1-based by the ids that appear on edges (id 0 always means "no fill" /
  "no stroke").
* `edges` -- every individual drawn segment, each tagged with the fill(s)
  and/or stroke active on it. This is the ground truth used to reconstruct
  closed fill regions (see `faces.py`): a segment shared by two regions
  carries both `fill0` (the region to its left) and `fill1` (to its right).
* `subpaths` -- the same edges, but grouped only by pen-continuity (i.e.
  "don't lift the pen"). Less structurally meaningful than `edges`, but
  cheap to compute and useful for quick bounding-box calculations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

Point = Tuple[float, float]

# A stroke or curve segment within a Subpath: either ('line', x, y) or
# ('curve', control_x, control_y, x, y).
Segment = tuple


@dataclass
class Edge:
    """One drawn segment (straight or quadratic-curve) with the fill/stroke
    style ids active on it. `fill0` is the fill to the left of the
    from->to direction, `fill1` to the right -- both use 0 for "none"."""
    start: Point
    end: Point
    control: Optional[Point]
    fill0: int
    fill1: int
    stroke: int


@dataclass
class Subpath:
    """A pen-continuous run of segments, in one fill/stroke style. Two
    subpaths can be geometrically adjacent (share an endpoint) without
    being the *same* subpath, if a style change or an interruption forced
    a new pen-down in between -- see `strokes.snap_stroke_edges`."""
    start: Point
    segments: List[Segment]
    fill0: int
    fill1: int
    stroke: int

    def end_point(self) -> Point:
        x, y = self.start
        for seg in self.segments:
            if seg[0] == "line":
                x, y = seg[1], seg[2]
            else:
                x, y = seg[3], seg[4]
        return x, y

    def points(self):
        """Yield every vertex relevant to a bounding-box calculation:
        start, each segment's endpoint, AND (for curves) the control point.
        A quadratic curve can bulge well outside the straight line between
        its endpoints, so the control point has to be included too or a
        curvy outline can end up cropped."""
        yield self.start
        for seg in self.segments:
            if seg[0] == "line":
                yield seg[1], seg[2]
            else:
                yield seg[1], seg[2]  # control point
                yield seg[3], seg[4]  # curve endpoint


RGBA = Tuple[int, int, int, int]


@dataclass
class GradientMatrix:
    scale_x: float
    scale_y: float
    rotate_skew0: float
    rotate_skew1: float
    translate_x: float
    translate_y: float


@dataclass
class FillStyle:
    kind: str  # "solid" | "linear" | "radial"
    color: Optional[RGBA] = None                       # kind == "solid"
    matrix: Optional[GradientMatrix] = None             # kind != "solid"
    stops: Optional[List[Tuple[int, RGBA]]] = None       # (ratio 0-255, rgba)


@dataclass
class LineStyle:
    color: RGBA
    width: int  # in twips (1/20 px)


@dataclass
class Shape:
    fills: List[FillStyle]
    lines: List[LineStyle]
    subpaths: List[Subpath]
    edges: List[Edge]
    source_stream: str = ""

    def fill_ids(self):
        """Every non-zero fill id actually used by an edge, sorted."""
        ids = set()
        for e in self.edges:
            if e.fill0:
                ids.add(e.fill0)
            if e.fill1:
                ids.add(e.fill1)
        return sorted(ids)

    def fill_style(self, fill_id: int) -> Optional[FillStyle]:
        if 1 <= fill_id <= len(self.fills):
            return self.fills[fill_id - 1]
        return None

    def line_style(self, line_id: int) -> Optional[LineStyle]:
        if 1 <= line_id <= len(self.lines):
            return self.lines[line_id - 1]
        return None

    def bounds(self):
        """(min_x, max_x, min_y, max_y) over every subpath vertex."""
        xs: List[float] = []
        ys: List[float] = []
        for sp in self.subpaths:
            for x, y in sp.points():
                xs.append(x)
                ys.append(y)
        if not xs:
            return 0.0, 100.0, 0.0, 100.0
        return min(xs), max(xs), min(ys), max(ys)
