"""
Detect and patch the tiny background gaps left between adjacent fills.

Coordinate rounding during the original authoring/export sometimes leaves
a sliver of "no fill" (fill id 0) between two regions that were clearly
meant to butt up against each other -- from a fraction of a square unit up
to a couple hundred, out of a drawing with millions of square units of
area. This module finds those slivers among fill id 0's traced faces (the
*true* background is always one huge face -- the outer boundary of the
whole drawing -- so a simple area cutoff separates it from genuine gaps)
and figures out which real fill should have covered each one, by seeing
which neighboring fill borders the most of its perimeter.
"""
from __future__ import annotations

from collections import Counter
from typing import List, Tuple

from .faces import Face, HalfEdge, trace_fill_faces
from .model import Edge

BACKGROUND_FILL_ID = 0

# Deliberately generous. In every sample file this tool has been tested
# against, the *true* unbounded exterior face is at least an order of
# magnitude bigger than this (tens of millions of square units) even for
# small icons, while genuine rounding gaps top out at a few thousand -- so
# there's normally a wide, safe margin to sit in.
#
# One wrinkle: a handful of very simple shapes were authored so that most
# of their edges carry no inline fill reference at all (fill0=fill1=0),
# leaving their entire visible body to be reconstructed here as a
# "background gap" patch rather than a real per-edge fill loop -- so this
# threshold sometimes needs to be well above what "a gap" suggests just to
# pick up genuinely-filled content. If a shape's own enclosed regions
# (e.g. a deliberately large negative-space cutout) are close in size to
# its own bounding box, lower this rather than trust the default blindly.
DEFAULT_GAP_AREA_THRESHOLD = 1_000_000.0

GapPatch = Tuple[List[HalfEdge], Face, int]  # (half_edges, gap face, fill id to patch with)


def _polygon_area(half_edges: List[HalfEdge], face: Face) -> float:
    points = [half_edges[face.half_edge_indices[0]].start]
    for i in face.half_edge_indices:
        points.append(half_edges[i].end)
    area = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def _dominant_neighbor_fill(half_edges: List[HalfEdge], face: Face) -> int | None:
    """Which fill id borders the most total edge length of this face."""
    weight_by_fill: Counter = Counter()
    for i in face.half_edge_indices:
        h = half_edges[i]
        neighbor_fill = half_edges[h.twin].fill_id
        if not neighbor_fill:
            continue
        (sx, sy), (ex, ey) = h.start, h.end
        weight_by_fill[neighbor_fill] += ((ex - sx) ** 2 + (ey - sy) ** 2) ** 0.5
    if not weight_by_fill:
        return None
    return max(weight_by_fill.items(), key=lambda kv: kv[1])[0]


def find_gap_patches(edges: List[Edge], area_threshold: float = DEFAULT_GAP_AREA_THRESHOLD
                      ) -> List[GapPatch]:
    """Return one GapPatch per small background face, each paired with the
    fill id that should cover it. Faces larger than `area_threshold` are
    assumed to be the drawing's real background/exterior and skipped."""
    half_edges, faces = trace_fill_faces(edges, BACKGROUND_FILL_ID, step=1)
    patches: List[GapPatch] = []
    for face in faces:
        if face.broken:
            continue
        if _polygon_area(half_edges, face) > area_threshold:
            continue
        fill_id = _dominant_neighbor_fill(half_edges, face)
        if fill_id is None:
            continue
        patches.append((half_edges, face, fill_id))
    return patches
