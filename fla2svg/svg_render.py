"""
Turn a decoded `Shape` into an SVG document.

Rendering happens in three layers, each painted over the last:

1. Fills -- one ``<path>`` per fill style, built from every closed loop
   `faces.trace_fill_faces` finds for that fill id, combined with the
   even-odd fill rule (so a fill with a hole in it "just works").
2. Gap patches -- `gaps.find_gap_patches` finds slivers of background
   between fills that were clearly meant to touch; each gets its own tiny
   patch path in whichever fill should have covered it.
3. Strokes -- every visible-stroke edge, snapped and grouped by line
   style (see `strokes.py`), drawn with round caps/joins so exactly
   touching segments read as one continuous line.

`_render_layers` does the actual work and is reused by `sprite.py` to
combine several shapes into one sheet; `render_svg` is the everyday
single-shape entry point.
"""
from __future__ import annotations

from typing import List, Tuple

from .faces import Face, HalfEdge, trace_fill_faces
from .gaps import DEFAULT_GAP_AREA_THRESHOLD, find_gap_patches
from .model import Shape
from .strokes import DEFAULT_SNAP_TOLERANCE, edge_path_d, group_by_line_style, snap_stroke_edges
from .styles import color_css, gradient_svg


def _loop_path_d(half_edges: List[HalfEdge], face: Face) -> str:
    start = half_edges[face.half_edge_indices[0]].start
    parts = [f"M {start[0]:.3f} {start[1]:.3f} "]
    for i in face.half_edge_indices:
        h = half_edges[i]
        if h.control is None:
            parts.append(f"L {h.end[0]:.3f} {h.end[1]:.3f} ")
        else:
            parts.append(f"Q {h.control[0]:.3f} {h.control[1]:.3f} {h.end[0]:.3f} {h.end[1]:.3f} ")
    parts.append("Z ")
    return "".join(parts)


def _fill_paint(shape: Shape, fill_id: int, gradient_id: str, defs: List[str]) -> str:
    fill = shape.fill_style(fill_id)
    if fill is None:
        return "#888"
    if fill.kind == "solid":
        return color_css(fill.color)
    defs.append(gradient_svg(fill, gradient_id))
    return f"url(#{gradient_id})"


def _render_layers(shape: Shape, *, gap_area_threshold: float, stroke_snap_tolerance: float,
                    id_prefix: str = "", stroke_width_scale: float = 1.0
                    ) -> Tuple[List[str], List[str]]:
    """Build the (defs, body) SVG fragments for one shape. `id_prefix`
    keeps gradient ids from colliding when several shapes' output is
    combined into one document (see `sprite.build_sprite`). `stroke_width_scale`
    compensates for an outer ``scale(...)`` transform the caller will wrap
    this content in (again, `sprite.build_sprite`) -- SVG stroke widths are
    affected by transforms just like geometry is, so a caller that scales
    the drawing down must scale the stroke width up by the same factor
    first, or every outline comes out too thin/thick once transformed."""
    defs: List[str] = []
    body: List[str] = []

    for fill_id in shape.fill_ids():
        half_edges, faces = trace_fill_faces(shape.edges, fill_id, step=1)
        gradient_id = f"{id_prefix}g{fill_id}"
        paint = _fill_paint(shape, fill_id, gradient_id, defs)
        d = " ".join(_loop_path_d(half_edges, f) for f in faces if not f.broken)
        body.append(f'<path d="{d}" fill="{paint}" fill-rule="evenodd" />')

    for half_edges, face, patch_fill_id in find_gap_patches(shape.edges, gap_area_threshold):
        paint = _fill_paint(shape, patch_fill_id, f"{id_prefix}g{patch_fill_id}", defs)
        d = _loop_path_d(half_edges, face)
        body.append(f'<path d="{d}" fill="{paint}" />')

    snapped = snap_stroke_edges(shape.edges, stroke_snap_tolerance)
    for line_id, group in sorted(group_by_line_style(snapped).items()):
        line = shape.line_style(line_id)
        color = color_css(line.color) if line else "#000"
        width = max((line.width / 20.0) if line else 1.0, 0.5) / stroke_width_scale
        d = " ".join(edge_path_d(e) for e in group)
        body.append(
            f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width:.2f}" '
            f'stroke-linecap="round" stroke-linejoin="round" />'
        )

    return defs, body


def render_svg(shape: Shape, *, gap_area_threshold: float = DEFAULT_GAP_AREA_THRESHOLD,
               stroke_snap_tolerance: float = DEFAULT_SNAP_TOLERANCE,
               padding_fraction: float = 0.02) -> str:
    """Render `shape` to a complete standalone SVG document (as a string).

    `gap_area_threshold` and `stroke_snap_tolerance` are the tuning knobs
    for `gaps.find_gap_patches` and `strokes.snap_stroke_edges`
    respectively -- the defaults work well across every file this tool has
    been tested against, but very small or very large artwork may want
    different values (see README.md).
    """
    min_x, max_x, min_y, max_y = shape.bounds()
    pad = max(10.0, (max_x - min_x) * padding_fraction)
    view_box = (min_x - pad, min_y - pad, (max_x - min_x) + 2 * pad, (max_y - min_y) + 2 * pad)

    defs, body = _render_layers(shape, gap_area_threshold=gap_area_threshold,
                                 stroke_snap_tolerance=stroke_snap_tolerance)

    defs_xml = f"<defs>{''.join(defs)}</defs>" if defs else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{view_box[0]:.3f} {view_box[1]:.3f} {view_box[2]:.3f} {view_box[3]:.3f}">'
        f"{defs_xml}{''.join(body)}</svg>"
    )


def render_svg_to_file(shape: Shape, out_path: str, **render_kwargs) -> None:
    svg = render_svg(shape, **render_kwargs)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(svg)
