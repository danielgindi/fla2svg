"""
fla2svg -- convert shapes from legacy binary Adobe/Macromedia Flash (.fla)
project files into real, editable vector SVG.

This targets the *pre-XFL* binary .fla format used by Flash 8, MX 2004 and
earlier. Those files are OLE/CFBF compound documents (the same container
format as old .doc/.xls files) with one stream per timeline or symbol, and
each stream encodes its vector artwork as a sequence of delta-compressed
"edge records" -- there is no off-the-shelf library or documented spec for
this, so the format here was recovered by reverse engineering.

This tool draws real closed vector paths from that binary edge data. It
does NOT rasterize the artwork and trace bitmaps, so output quality does
not depend on resolution and fills/strokes come out exactly where the
original author put them.

Pipeline, roughly:

    .fla file (OLE compound document)
      -> ole_extract.iter_streams()   split into per-symbol byte streams
      -> shape.parse_shape()          decode fill/line styles + edge data
      -> faces.trace_fill_faces()     reconstruct closed fill regions
      -> strokes.snap_stroke_edges()  fix up near-duplicate stroke vertices
      -> svg_render.render_svg()      emit an SVG document

See README.md for the full format notes, CLI usage, and known limitations.
"""

from .model import Edge, FillStyle, LineStyle, Shape, Subpath
from .shape import parse_shape
from .ole_extract import iter_streams, extract_streams
from .svg_render import render_svg, render_svg_to_file
from .sprite import build_sprite

__version__ = "1.0.0"

__all__ = [
    "Shape", "Edge", "Subpath", "FillStyle", "LineStyle", "parse_shape",
    "iter_streams", "extract_streams",
    "render_svg", "render_svg_to_file",
    "build_sprite",
]
