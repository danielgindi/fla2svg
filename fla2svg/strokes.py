"""
Fix up stroke-edge coordinates before rendering them.

Fill edges always meet at bit-identical shared coordinates (both
directions of an edge come from the same parsed floats -- see
`faces._round_key`), which is why fill reconstruction needs no tolerance
at all. Visible-stroke edges are different: two stroke edges that are
meant to touch at the same corner were sometimes *authored* with slightly
different coordinates for that point (evidently a lower-precision pass in
the original tool, off by anywhere from a fraction of a unit up to a few
dozen, out of drawings thousands of units across).

Left alone, that shows up two ways when rendered: a visible gap in an
outline that should be continuous, or -- if you instead try to paper over
it by force-closing every stroke run back to its own start -- a spurious
straight "chord" cutting across the shape whenever a run's start and end
were never meant to coincide at all.

The fix applied here sidesteps both failure modes: cluster stroke-edge
endpoints that fall within `tolerance` units of each other and snap them
to one shared point, then draw every real stroke edge once, as its own
segment. Genuinely adjacent segments now share an exact coordinate (so
they join with no visible gap) and nothing is ever force-closed, so no
chord is ever synthesized.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Dict, List

from .model import Edge, Point

DEFAULT_SNAP_TOLERANCE = 15.0


class _UnionFind:
    def __init__(self):
        self._parent: Dict[Point, Point] = {}

    def find(self, x: Point) -> Point:
        self._parent.setdefault(x, x)
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[x] != root:
            self._parent[x], x = root, self._parent[x]
        return root

    def union(self, a: Point, b: Point) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[ra] = rb


def snap_stroke_edges(edges: List[Edge], tolerance: float = DEFAULT_SNAP_TOLERANCE) -> List[Edge]:
    """Return the stroked subset of `edges` (those with a non-zero
    `stroke` id), with every endpoint remapped so that points within
    `tolerance` of each other become one shared coordinate (the centroid
    of the cluster).

    Clustering is a simple O(n^2) pairwise union-find, which is fine at
    the scale a single symbol's stroke edges reach (low hundreds to low
    thousands); a spatial index would be worth adding before using this on
    much larger inputs.
    """
    stroke_edges = [e for e in edges if e.stroke]
    points = {e.start for e in stroke_edges} | {e.end for e in stroke_edges}
    points = list(points)

    uf = _UnionFind()
    for p in points:
        uf.find(p)
    tol2 = tolerance * tolerance
    for i in range(len(points)):
        xi, yi = points[i]
        for j in range(i + 1, len(points)):
            dx, dy = xi - points[j][0], yi - points[j][1]
            if dx * dx + dy * dy <= tol2:
                uf.union(points[i], points[j])

    clusters: Dict[Point, List[Point]] = {}
    for p in points:
        clusters.setdefault(uf.find(p), []).append(p)

    remap: Dict[Point, Point] = {}
    for members in clusters.values():
        cx = sum(p[0] for p in members) / len(members)
        cy = sum(p[1] for p in members) / len(members)
        for p in members:
            remap[p] = (cx, cy)

    return [replace(e, start=remap[e.start], end=remap[e.end]) for e in stroke_edges]


def edge_path_d(edge: Edge) -> str:
    """SVG path data for a single edge, as its own ``M ... L``/``Q``."""
    sx, sy = edge.start
    if edge.control is None:
        ex, ey = edge.end
        return f"M {sx:.3f} {sy:.3f} L {ex:.3f} {ey:.3f} "
    cx, cy = edge.control
    ex, ey = edge.end
    return f"M {sx:.3f} {sy:.3f} Q {cx:.3f} {cy:.3f} {ex:.3f} {ey:.3f} "


def group_by_line_style(edges: List[Edge]) -> Dict[int, List[Edge]]:
    """Group (already-snapped) stroke edges by their line-style id, in a
    dict ordered by first appearance -- iterate `sorted(result)` for a
    deterministic style-id order when rendering."""
    groups: Dict[int, List[Edge]] = {}
    for e in edges:
        groups.setdefault(e.stroke, []).append(e)
    return groups
