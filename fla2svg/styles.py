"""
Decode the fill-style and line-style tables that precede a shape's edge
stream, and render them to SVG paint (`fill="..."` / `<linearGradient>`).
"""
from __future__ import annotations

import struct
from typing import List, Tuple

from .binary_reader import ByteReader, read_fixed_16_16
from .model import FillStyle, GradientMatrix, LineStyle, RGBA

SOLID = 0x00
LINEAR_GRADIENT = 0x10
RADIAL_GRADIENT = 0x12

# Every non-gradient fill entry we've seen ends with this 4-byte marker
# before the next entry (or the line-style table) begins.
_LINE_TRAILER_MARKER = bytes([0x01, 0x01, 0x00, 0x03])


def parse_styles(reader: ByteReader) -> Tuple[List[FillStyle], List[LineStyle]]:
    """Read the fill-style table followed by the line-style table from
    `reader`'s current position, advancing it past both."""
    fills = _parse_fill_styles(reader)
    lines = _parse_line_styles(reader)
    return fills, lines


def _parse_fill_styles(r: ByteReader) -> List[FillStyle]:
    count = r.u16()
    fills: List[FillStyle] = []
    for _ in range(count):
        color_placeholder: RGBA = tuple(r.data[r.pos:r.pos + 4])  # type: ignore[assignment]
        fill_type = r.data[r.pos + 4]

        if fill_type == SOLID:
            r.skip(6)
            fills.append(FillStyle(kind="solid", color=color_placeholder))
            continue

        if fill_type in (LINEAR_GRADIENT, RADIAL_GRADIENT):
            entry_start = r.pos
            matrix = GradientMatrix(
                scale_x=read_fixed_16_16(r.data, entry_start + 6),
                rotate_skew0=read_fixed_16_16(r.data, entry_start + 10),
                rotate_skew1=read_fixed_16_16(r.data, entry_start + 14),
                scale_y=read_fixed_16_16(r.data, entry_start + 18),
                translate_x=struct.unpack_from("<i", r.data, entry_start + 22)[0],
                translate_y=struct.unpack_from("<i", r.data, entry_start + 26)[0],
            )
            stop_count = r.data[entry_start + 30]
            stops = []
            sp = entry_start + 39
            for _ in range(stop_count):
                ratio = r.data[sp]
                rgba = tuple(r.data[sp + 1:sp + 5])
                stops.append((ratio, rgba))
                sp += 5
            kind = "radial" if fill_type == RADIAL_GRADIENT else "linear"
            fills.append(FillStyle(kind=kind, matrix=matrix, stops=stops))
            r.pos = sp
            continue

        raise ValueError(f"unknown fill type 0x{fill_type:02x} at offset {r.pos + 4}")

    return fills


def _parse_line_styles(r: ByteReader) -> List[LineStyle]:
    count = r.u16()
    lines: List[LineStyle] = []
    for i in range(count):
        rgba: RGBA = tuple(r.data[r.pos:r.pos + 4])  # type: ignore[assignment]
        r.skip(4)
        width = r.u16()
        r.skip(6)
        # A handful of optional flag/joint-style fields sit between the
        # width and a fixed trailer marker; rather than decode them (we
        # don't need them), scan a short window for the marker and resync.
        marker = r.data[r.pos:r.pos + 4]
        if marker != _LINE_TRAILER_MARKER:
            window = r.data[r.pos:r.pos + 40]
            offset = window.find(_LINE_TRAILER_MARKER)
            if offset == -1:
                raise ValueError(f"line-style trailer marker not found for line {i}")
            r.skip(offset)
        r.skip(4)  # the trailer marker itself
        r.skip(6)  # fixed padding before the next entry
        lines.append(LineStyle(color=rgba, width=width))
    return lines


def color_css(rgba: RGBA) -> str:
    r, g, b, a = rgba
    if a == 255:
        return f"#{r:02x}{g:02x}{b:02x}"
    return f"rgba({r},{g},{b},{a / 255.0:.3f})"


def gradient_svg(fill: FillStyle, gradient_id: str) -> str:
    """Render a FillStyle with kind "linear"/"radial" as an SVG
    <linearGradient>/<radialGradient> definition.

    Flash gradients are always authored over a fixed [-16384, 16384]
    (linear) or radius-16384 (radial) unit space and then positioned with
    a transform matrix -- we reproduce that directly via
    `gradientTransform` rather than trying to bake the matrix into stop
    coordinates.
    """
    m = fill.matrix
    assert m is not None
    transform = (
        f"matrix({m.scale_x:.8f} {m.rotate_skew0:.8f} {m.rotate_skew1:.8f} "
        f"{m.scale_y:.8f} {int(m.translate_x)} {int(m.translate_y)})"
    )
    stop_tags = []
    for ratio, rgba in fill.stops or []:
        r, g, b, a = rgba
        stop_tags.append(
            f'<stop offset="{ratio / 255.0:.4f}" stop-color="#{r:02x}{g:02x}{b:02x}" '
            f'stop-opacity="{a / 255.0:.3f}" />'
        )
    stops_xml = "".join(stop_tags)
    if fill.kind == "radial":
        return (
            f'<radialGradient id="{gradient_id}" gradientUnits="userSpaceOnUse" '
            f'cx="0" cy="0" r="16384" gradientTransform="{transform}">{stops_xml}</radialGradient>'
        )
    return (
        f'<linearGradient id="{gradient_id}" gradientUnits="userSpaceOnUse" '
        f'x1="-16384" y1="0" x2="16384" y2="0" gradientTransform="{transform}">{stops_xml}</linearGradient>'
    )
