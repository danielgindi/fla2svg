"""
Combine several shapes into one SVG "sprite sheet", each centered and
scaled into its own square tile on a grid -- handy for a set of icons that
started life as separate symbols in one (or several) .fla file(s).
"""
from __future__ import annotations

from typing import List, Sequence, Tuple

from .gaps import DEFAULT_GAP_AREA_THRESHOLD
from .model import Shape
from .strokes import DEFAULT_SNAP_TOLERANCE
from .svg_render import _render_layers

DEFAULT_TILE_SIZE = 800.0
DEFAULT_TILE_PADDING = 60.0
DEFAULT_COLUMNS = 3


def build_sprite(named_shapes: Sequence[Tuple[str, Shape]], *,
                  columns: int = DEFAULT_COLUMNS,
                  tile_size: float = DEFAULT_TILE_SIZE,
                  tile_padding: float = DEFAULT_TILE_PADDING,
                  gap_area_threshold: float = DEFAULT_GAP_AREA_THRESHOLD,
                  stroke_snap_tolerance: float = DEFAULT_SNAP_TOLERANCE) -> str:
    """Render `named_shapes` (a list of (name, Shape) pairs, used for the
    tile's ``data-name`` attribute and to keep gradient ids from colliding)
    into one grid sheet and return the SVG document as a string.

    Each shape is scaled uniformly (never stretched) to fit within
    `tile_size - 2*tile_padding` on its longer axis and centered in its
    tile; tiles are laid out left-to-right, top-to-bottom in `columns`
    columns.
    """
    all_defs: List[str] = []
    all_tiles: List[str] = []
    max_row = 0

    for index, (name, shape) in enumerate(named_shapes):
        min_x, max_x, min_y, max_y = shape.bounds()
        width, height = max_x - min_x, max_y - min_y
        scale = (tile_size - 2 * tile_padding) / max(width, height, 1.0)
        center_x, center_y = (min_x + max_x) / 2, (min_y + max_y) / 2

        row, col = divmod(index, columns)
        max_row = max(max_row, row)
        origin_x = col * tile_size + tile_size / 2
        origin_y = row * tile_size + tile_size / 2

        id_prefix = f"s{index}_"
        defs, body = _render_layers(shape, gap_area_threshold=gap_area_threshold,
                                     stroke_snap_tolerance=stroke_snap_tolerance,
                                     id_prefix=id_prefix, stroke_width_scale=scale)
        all_defs.extend(defs)

        transform = (
            f"translate({origin_x:.2f} {origin_y:.2f}) scale({scale:.6f}) "
            f"translate({-center_x:.2f} {-center_y:.2f})"
        )
        all_tiles.append(f'<g transform="{transform}" data-name="{name}">{"".join(body)}</g>')

    sheet_width = columns * tile_size
    sheet_height = (max_row + 1) * tile_size
    defs_xml = f"<defs>{''.join(all_defs)}</defs>" if all_defs else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {sheet_width:.0f} {sheet_height:.0f}">'
        f"{defs_xml}{''.join(all_tiles)}</svg>"
    )
