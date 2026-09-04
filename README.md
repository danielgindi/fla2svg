# fla2svg

Convert shapes from **legacy binary Adobe/Macromedia Flash (`.fla`) files**
into real, editable vector SVG — by parsing the actual vector edge data,
not by rasterizing and tracing bitmaps.

This targets the *old* binary `.fla` format used by Flash 8, MX 2004 and
earlier (the format that predates the XML-based XFL/`.fla` format from
CS5 onward). There is no public specification for it, and mainstream
libraries don't read it; the format used here was recovered by reverse
engineering a handful of real `.fla` files. It works well on every file
this tool has been tested against, but it hasn't seen the breadth of
inputs a mature library would have — see **Limitations** below, and
please open an issue (or send a PR) if you find a file it chokes on.

## Why this exists

The obvious fallback for an old `.fla` you can't open anymore is: open it
in a compatible Flash version, export a PNG, and trace the bitmap in
Illustrator/Inkscape/potrace. That works, but you lose true vector
precision — curves become polygon approximations, and quality is capped
by whatever export resolution you traced.

This tool instead reads the file's own vector data directly and
reconstructs real `<path>` fills and strokes from it, so the output is as
precise as the original artwork, at any output size.

## How it works, briefly

A binary `.fla` is an OLE/CFBF compound document — the same container
format old `.doc`/`.xls` files used — with one stream per timeline/symbol.
Each stream encodes its vector artwork as a sequence of delta-compressed
"edge records": individual straight or curved segments, each carrying the
fill/stroke style active on it, with coordinates expressed as offsets from
wherever the "pen" currently sits rather than as absolute positions.

Turning that into clean SVG paths takes a bit of reconstruction:

* **Fills** aren't stored as "here's fill #4's outline" — only as
  individual edges tagged with which fill(s) border them. `faces.py`
  builds a planar half-edge graph from every edge and walks it to trace
  each fill's actual closed boundary (or boundaries, for a fill with a
  hole in it).
* **Small background gaps** are patched. Coordinate rounding in the
  original files sometimes leaves a sliver of "no fill" between two
  regions that were clearly meant to touch; `gaps.py` finds these (by
  filtering the traced background faces by area) and fills them with
  whichever real fill should have covered them.
* **Stroke edges** that are supposed to meet at a shared corner were
  sometimes authored with slightly different coordinates for that point.
  `strokes.py` clusters and snaps nearby stroke endpoints together before
  rendering, so adjacent segments always join with no visible gap, and
  nothing needs to be force-closed into a spurious straight line to hide
  the problem.

See the module docstrings (`faces.py`, `gaps.py`, `strokes.py` especially)
for the full explanation with more detail; they're written to stand alone.

## Install

```bash
pip install olefile   # the only runtime dependency
```

or, from a checkout of this tool:

```bash
pip install -e .
```

Requires Python 3.8+.

## Command-line usage

Convert every shape in a `.fla` file to its own SVG, next to the input file:

```bash
python -m fla2svg convert path/to/file.fla
```

...or (after `pip install`) just:

```bash
fla2svg convert path/to/file.fla
```

Choose an output directory, and also combine every shape into one grid
sprite sheet:

```bash
fla2svg convert icons.fla -o out/ --sprite icons_combined.svg
```

Dump the raw OLE streams for inspection, without parsing them as shapes:

```bash
fla2svg extract path/to/file.fla -o streams/
```

Run `fla2svg convert --help` for the full list of tuning options
(`--gap-area-threshold`, `--snap-tolerance`, `--sprite-columns`, etc).

Not every stream in a `.fla` is a shape — `Contents` and `Page N` streams
describe timeline/frame structure and don't usually carry inline shape
geometry of their own. `convert` tries every stream and quietly skips (or,
for a stream that starts parsing but fails partway through, reports on
stderr and skips) whichever ones aren't actually shapes; you'll typically
see one output SVG per symbol defined in the file.

## Library usage

```python
from fla2svg import parse_shape, render_svg
from fla2svg.ole_extract import iter_streams

for name, data in iter_streams("icons.fla"):
    shape = parse_shape(data, source_stream=name)
    if shape is None:
        continue  # not a drawable shape
    svg_text = render_svg(shape)
    with open(f"{name}.svg", "w") as f:
        f.write(svg_text)
```

`render_svg` takes optional `gap_area_threshold` and `stroke_snap_tolerance`
keyword arguments if the defaults don't suit a particular file (very large
or very small artwork especially — see the tuning note in `gaps.py`).

To combine several shapes into one sprite sheet:

```python
from fla2svg import build_sprite

named_shapes = [("arrow", shape_a), ("plus", shape_b)]
sheet_svg = build_sprite(named_shapes, columns=3)
```

## Project layout

```
fla2svg/
  model.py          Shape / Edge / Subpath / FillStyle / LineStyle data classes
  ole_extract.py     Split a .fla's OLE streams apart
  binary_reader.py   Low-level byte-reading helpers, MFC class-tag scanning
  edge_records.py    The edge-record binary format itself
  styles.py          Fill/line style tables -> SVG paint
  shape.py           Top-level "decode one stream into a Shape" entry point
  faces.py           Planar half-edge graph / fill-region reconstruction
  gaps.py            Small background-gap detection and patching
  strokes.py         Stroke-vertex snapping and per-edge path rendering
  svg_render.py      Shape -> SVG document
  sprite.py          Multiple shapes -> one grid sprite sheet
  cli.py / __main__.py   Command-line interface
tests/
  test_smoke.py      Parses and renders every bundled sample file
  samples/           A handful of real extracted shape streams to test against
```

Each module is meant to be read top-to-bottom on its own; start with
`shape.py` to see the overall flow, then follow into `faces.py`,
`gaps.py`, and `strokes.py` for the interesting parts.

## Limitations

* Only the pre-XFL binary `.fla` container is supported. A modern
  `.fla`/`.xfl` (CS5+) is a zip of XML files and needs a completely
  different (much simpler, since it's documented) parser.
* Stream discovery in `parse_shape`/`convert` is heuristic (it scans for
  known class-tag byte patterns rather than parsing a real object graph),
  so it's possible for a stream that isn't really a shape to produce
  nonsense output rather than being cleanly rejected. `shape.py` filters
  the one false-positive pattern observed in testing (a match with zero
  fill and zero line styles); if you hit another, please report the
  symptom (garbage coordinates, usually in the tens of thousands, are the
  giveaway).
* Only solid fills and 2-stop-or-more linear/radial gradients have been
  observed and are supported; bitmap fills, gradient spread modes other
  than the default, and filters/blend modes are not handled.
* `gap_area_threshold` and `stroke_snap_tolerance` are tuned against every
  sample file available during development, but they're still just
  numbers — a shape at a very different scale, or with unusually small
  real detail, may need different values. Try rendering with `--sprite`
  omitted and inspecting one file first if output looks off.

## License

All the code here is under MIT license. Which means you could do virtually anything with the code.
I will appreciate it very much if you keep an attribution where appropriate.

    The MIT License (MIT)
    
    Copyright (c) 2013 Daniel Cohen Gindi (danielgindi@gmail.com)
    
    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:
    
    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.
    
    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.
