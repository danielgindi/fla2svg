"""
Low-level byte-reading helpers shared by the parser.

Flash's binary format is written with an MFC-style ``CArchive`` (the
serialization layer MFC applications used to save C++ object graphs to
disk). Each serialized class instance is preceded by a small "class tag"
the archive uses to know what type to reconstruct:

    FF FF <schema-version: u16> <name-length: u16> <name bytes>

We don't reimplement CArchive's full object graph -- we just scan for the
class-name bytes we care about (e.g. ``CPicShape``) and start parsing our
own known-fixed-layout fields immediately after that tag.
"""
from __future__ import annotations

import struct
from typing import Optional


def find_class_start(data: bytes, class_name: str, from_pos: int = 0) -> Optional[int]:
    """Return the byte offset right after a CArchive class tag for
    `class_name`, or None if it doesn't appear in `data` at or after
    `from_pos`.

    The tag layout is ``FF FF <u16 schema> <u16 namelen> <name>``; we find
    the ASCII class name and skip past it plus the 2-byte schema-version
    field that always immediately precedes it.
    """
    idx = data.find(class_name.encode("ascii"), from_pos)
    if idx == -1:
        return None
    return idx + len(class_name) + 2


def read_fixed_16_16(data: bytes, pos: int) -> float:
    """Read a 32-bit signed 16.16 fixed-point number (used for gradient
    transform matrices)."""
    return struct.unpack_from("<i", data, pos)[0] / 65536.0


class ByteReader:
    """A tiny forward-only cursor over a bytes buffer.

    Kept deliberately minimal (just enough for the little-endian integer
    reads `styles.py` needs) rather than pulling in a general binary
    parsing dependency.
    """

    __slots__ = ("data", "pos")

    def __init__(self, data: bytes, pos: int = 0):
        self.data = data
        self.pos = pos

    def u8(self) -> int:
        v = self.data[self.pos]
        self.pos += 1
        return v

    def u16(self) -> int:
        v = struct.unpack_from("<H", self.data, self.pos)[0]
        self.pos += 2
        return v

    def skip(self, n: int) -> None:
        self.pos += n

    def bytes(self, n: int) -> bytes:
        v = self.data[self.pos:self.pos + n]
        self.pos += n
        return v
