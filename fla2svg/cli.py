"""
Command-line interface: ``python -m fla2svg ...`` (see __main__.py).
"""
from __future__ import annotations

import argparse
import os
import struct
import sys
from typing import List, Tuple

from .gaps import DEFAULT_GAP_AREA_THRESHOLD
from .ole_extract import extract_streams, iter_streams
from .shape import Shape, parse_shape
from .sprite import DEFAULT_COLUMNS, DEFAULT_TILE_SIZE, build_sprite
from .strokes import DEFAULT_SNAP_TOLERANCE
from .svg_render import render_svg


def _default_out_dir(fla_path: str, out_dir: str | None) -> str:
    return out_dir if out_dir else os.path.dirname(os.path.abspath(fla_path))


def _parse_all_shapes(fla_path: str, *, verbose: bool = True) -> List[Tuple[str, Shape]]:
    """Every stream in `fla_path` that successfully parses as a shape,
    paired with a filesystem-safe name derived from the stream name.

    Not every stream in a .fla is a shape -- "Contents" and "Page N"
    streams describe timeline/frame structure and only sometimes contain
    inline shape geometry of their own, so a class-tag match there can
    turn out to be a false positive once the fixed-layout style-table
    parsing that follows it doesn't line up. Rather than let one such
    stream abort the whole conversion, each is tried independently and
    skipped (with a note on stderr) on failure.
    """
    found = []
    for stream_name, data in iter_streams(fla_path):
        try:
            shape = parse_shape(data, source_stream=stream_name)
        except (ValueError, IndexError, struct.error) as exc:
            if verbose:
                print(f"skipping stream {stream_name!r}: {exc}", file=sys.stderr)
            continue
        if shape is None or not shape.edges:
            continue  # not a drawable shape (or an empty one) -- skip quietly
        safe_name = stream_name.replace(" ", "_")
        found.append((safe_name, shape))
    return found


def cmd_extract(args: argparse.Namespace) -> int:
    out_dir = _default_out_dir(args.fla, args.output)
    written = extract_streams(args.fla, out_dir)
    for path in written:
        print(path)
    return 0


def cmd_convert(args: argparse.Namespace) -> int:
    out_dir = _default_out_dir(args.fla, args.output)
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(args.fla))[0]

    shapes = _parse_all_shapes(args.fla)
    if not shapes:
        print(f"no drawable shapes found in {args.fla}", file=sys.stderr)
        return 1

    render_kwargs = dict(gap_area_threshold=args.gap_area_threshold,
                          stroke_snap_tolerance=args.snap_tolerance)

    for name, shape in shapes:
        out_path = os.path.join(out_dir, f"{base}__{name}.svg")
        svg = render_svg(shape, **render_kwargs)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(svg)
        print(out_path)

    if args.sprite:
        sprite_svg = build_sprite(shapes, columns=args.sprite_columns,
                                   tile_size=args.sprite_tile_size,
                                   gap_area_threshold=args.gap_area_threshold,
                                   stroke_snap_tolerance=args.snap_tolerance)
        sprite_path = args.sprite if os.path.isabs(args.sprite) else os.path.join(out_dir, args.sprite)
        with open(sprite_path, "w", encoding="utf-8") as f:
            f.write(sprite_svg)
        print(sprite_path)

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fla2svg",
        description="Convert shapes from legacy binary Flash (.fla) files into vector SVG.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    convert = subparsers.add_parser(
        "convert", help="Parse and render every shape stream in a .fla file to SVG."
    )
    convert.add_argument("fla", help="Path to the .fla file.")
    convert.add_argument("-o", "--output", help="Output directory (default: alongside the .fla file).")
    convert.add_argument("--sprite", metavar="FILENAME",
                          help="Also combine every shape into one grid sprite sheet with this filename.")
    convert.add_argument("--sprite-columns", type=int, default=DEFAULT_COLUMNS,
                          help=f"Sprite sheet grid columns (default: {DEFAULT_COLUMNS}).")
    convert.add_argument("--sprite-tile-size", type=float, default=DEFAULT_TILE_SIZE,
                          help=f"Sprite sheet tile size in SVG units (default: {DEFAULT_TILE_SIZE:g}).")
    convert.add_argument("--gap-area-threshold", type=float, default=DEFAULT_GAP_AREA_THRESHOLD,
                          help="Background faces smaller than this (in the shape's own square units) "
                               f"are patched as rounding gaps rather than kept as background (default: {DEFAULT_GAP_AREA_THRESHOLD:g}).")
    convert.add_argument("--snap-tolerance", type=float, default=DEFAULT_SNAP_TOLERANCE,
                          help="Stroke endpoints within this many units of each other are snapped "
                               f"together before rendering (default: {DEFAULT_SNAP_TOLERANCE:g}).")
    convert.set_defaults(func=cmd_convert)

    extract = subparsers.add_parser(
        "extract", help="Dump each raw OLE stream in a .fla file to its own .bin file (debugging aid)."
    )
    extract.add_argument("fla", help="Path to the .fla file.")
    extract.add_argument("-o", "--output", help="Output directory (default: alongside the .fla file).")
    extract.set_defaults(func=cmd_extract)

    return parser


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
