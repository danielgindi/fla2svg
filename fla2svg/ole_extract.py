"""
Split a binary .fla file's OLE/CFBF streams apart.

An old-format .fla is a plain OLE compound document -- the same container
format Microsoft Office used for .doc/.xls before the .docx/.xlsx era.
Each timeline and each symbol in the Flash document gets its own top-level
stream, typically named things like "Contents", "Page 1", "Symbol 2", ...

This module only peels the container open; it knows nothing about the
Flash-specific byte layout inside each stream (see edge_records.py and
shape.py for that).
"""
from __future__ import annotations

import os
from typing import Iterator, List, Tuple

import olefile


def iter_streams(fla_path: str) -> Iterator[Tuple[str, bytes]]:
    """Yield (stream_name, raw_bytes) for every top-level stream in a .fla
    file, in the order OLE lists them.

    Only top-level streams are considered -- for every .fla this tool has
    encountered, the streams that matter (``Contents``, ``Page N``,
    ``Symbol N``) all live at the root of the compound document.
    """
    ole = olefile.OleFileIO(fla_path)
    try:
        for entry in ole.listdir():
            if len(entry) != 1:
                continue
            name = entry[0]
            data = ole.openstream(entry).read()
            yield name, data
    finally:
        ole.close()


def extract_streams(fla_path: str, out_dir: str) -> List[str]:
    """Write every stream of `fla_path` to its own ``<basename>__<stream
    name>.bin`` file under `out_dir` (spaces in the stream name become
    underscores). Returns the list of paths written.

    This is a debugging/inspection convenience -- `parse_shape` can be
    handed stream bytes directly via `iter_streams`, without ever touching
    disk.
    """
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(fla_path))[0]
    written = []
    for name, data in iter_streams(fla_path):
        safe_name = name.replace(" ", "_")
        out_path = os.path.join(out_dir, f"{base}__{safe_name}.bin")
        with open(out_path, "wb") as f:
            f.write(data)
        written.append(out_path)
    return written
