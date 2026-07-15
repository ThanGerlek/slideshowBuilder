#!/usr/bin/env python3
"""Generate simple PNG test images for the sample slideshow."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path


def _chunk(chunk_type: bytes, data: bytes) -> bytes:
    payload = chunk_type + data
    crc = struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)
    return struct.pack(">I", len(data)) + payload + crc


def write_png(path: Path, width: int, height: int, rgb: tuple[int, int, int]) -> None:
    raw_rows = []
    r, g, b = rgb
    row = bytes([0, r, g, b] * width)
    for _ in range(height):
        raw_rows.append(row)
    compressed = zlib.compress(b"".join(raw_rows), level=9)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", ihdr)
    png += _chunk(b"IDAT", compressed)
    png += _chunk(b"IEND", b"")
    path.write_bytes(png)


def main() -> None:
    photos_dir = Path(__file__).resolve().parent / "photos"
    photos_dir.mkdir(parents=True, exist_ok=True)
    samples = [
        ("001.png", (220, 80, 70)),
        ("002.png", (70, 130, 180)),
        ("003.png", (90, 160, 100)),
    ]
    for filename, color in samples:
        write_png(photos_dir / filename, 1600, 900, color)
        print(f"Wrote {photos_dir / filename}")


if __name__ == "__main__":
    main()
