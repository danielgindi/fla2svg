"""
Reconstruct closed fill regions ("faces") from the flat edge list.

This is the key trick that makes real vector fills possible: the binary
format never stores "here is fill #4's outline" directly, only individual
edges each tagged with the fill(s) they border. To get fill #4's actual
outline(s) back, we build a planar graph and walk it.

The construction is the classic doubly-connected-edge-list (half-edge)
approach: every geometric edge becomes two directed half-edges (one for
each side/direction), each knowing the half-edge that runs the other way
along the same geometry (its "twin"). To trace fill #4's boundary, start
on any half-edge whose fill id is 4, then repeatedly: jump to the twin
(crossing to the other side of the edge we just walked), and from there
take the *next* half-edge in angular order around that shared vertex. That
next-in-rotation step is what "hugs" the fill region's actual boundary
instead of wandering off across unrelated geometry.
"""
from __future__ import annotations

import math
from typing import Dict, List, Tuple

from .model import Edge, Point


def _round_key(point: Point) -> Tuple[float, float]:
    """Coordinates that are meant to be the same vertex always arrive
    bit-identical from the parser (both directions of an edge share the
    same floats), so rounding to 2 decimal places is just cheap insurance
    against float noise, not a tolerance for genuinely different points."""
    return round(point[0], 2), round(point[1], 2)


class HalfEdge:
    __slots__ = ("start", "end", "control", "fill_id", "twin")

    def __init__(self, start, end, control, fill_id):
        self.start = start
        self.end = end
        self.control = control
        self.fill_id = fill_id
        self.twin = -1  # index of the paired half-edge, filled in below


def _tangent_angle(half_edge: HalfEdge) -> float:
    """Direction the half-edge leaves its start vertex in, for sorting the
    half-edges around a vertex into a consistent rotational order."""
    start, end, control = half_edge.start, half_edge.end, half_edge.control
    if control is not None and _round_key(control) != _round_key(start):
        dx, dy = control[0] - start[0], control[1] - start[1]
    else:
        dx, dy = end[0] - start[0], end[1] - start[1]
    return math.atan2(dy, dx)


class _FaceGraph:
    """The half-edge graph plus, for each half-edge, its position within
    the angularly-sorted rotation of half-edges leaving the same vertex."""

    def __init__(self, edges: List[Edge]):
        half_edges: List[HalfEdge] = []
        for e in edges:
            forward = HalfEdge(e.start, e.end, e.control, e.fill0)
            backward = HalfEdge(e.end, e.start, e.control, e.fill1)
            i_fwd, i_bwd = len(half_edges), len(half_edges) + 1
            half_edges.append(forward)
            half_edges.append(backward)
            forward.twin, backward.twin = i_bwd, i_fwd

        by_start: Dict[Tuple[float, float], List[int]] = {}
        for i, h in enumerate(half_edges):
            by_start.setdefault(_round_key(h.start), []).append(i)
        for indices in by_start.values():
            indices.sort(key=lambda i: _tangent_angle(half_edges[i]))

        rotation_of: Dict[int, List[int]] = {}
        position_of: Dict[int, int] = {}
        for indices in by_start.values():
            for pos, i in enumerate(indices):
                rotation_of[i] = indices
                position_of[i] = pos

        self.half_edges = half_edges
        self._rotation_of = rotation_of
        self._position_of = position_of

    def next_in_rotation(self, half_edge_index: int, step: int = 1) -> int:
        rotation = self._rotation_of[half_edge_index]
        pos = self._position_of[half_edge_index]
        return rotation[(pos + step) % len(rotation)]


class Face:
    """One traced loop: a sequence of half-edge indices into the
    `half_edges` list `trace_fill_faces` returns alongside it. `broken`
    means the walk ran into an already-used or wrong-fill half-edge before
    closing back to its start -- i.e. the edge data doesn't actually form
    a closed loop here (normally only happens on malformed input)."""
    __slots__ = ("half_edge_indices", "broken")

    def __init__(self, half_edge_indices: List[int], broken: bool):
        self.half_edge_indices = half_edge_indices
        self.broken = broken


def trace_fill_faces(edges: List[Edge], fill_id: int, step: int = 1
                      ) -> Tuple[List[HalfEdge], List[Face]]:
    """Trace every closed boundary loop bordering `fill_id`.

    Returns (half_edges, faces): `half_edges` is the full graph (needed to
    resolve the indices each Face stores), `faces` is one Face per
    boundary loop found. A shape with fill regions that have holes (e.g. a
    letter "O") naturally produces multiple loops for the same fill id --
    render them together with the even-odd fill rule.

    `step`: +1 walks the "next" half-edge in angular order at each hop,
    -1 the "previous" one. Which one traces the *outer* boundary (instead
    of degenerately bouncing along each edge's own twin) depends on the
    coordinate system's winding convention; +1 is correct for this format.
    """
    graph = _FaceGraph(edges)
    half_edges = graph.half_edges
    used = [False] * len(half_edges)
    faces: List[Face] = []

    for i, h in enumerate(half_edges):
        if h.fill_id != fill_id or used[i]:
            continue

        loop = [i]
        used[i] = True
        current = i
        broken = False

        for _ in range(len(half_edges) + 1):
            twin = half_edges[current].twin
            next_index = graph.next_in_rotation(twin, step)
            if next_index == i:
                break  # walked all the way back to the start: closed loop
            if used[next_index] or half_edges[next_index].fill_id != fill_id:
                broken = True
                break
            loop.append(next_index)
            used[next_index] = True
            current = next_index
        else:
            broken = True  # safety net; should not happen on real data

        faces.append(Face(loop, broken))

    return half_edges, faces
