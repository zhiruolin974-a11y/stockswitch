"""Generate original Windows icon and EXE metadata from the single version source."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

from src.app.version import VERSION

ROOT = Path(__file__).resolve().parents[1]


def _png(size: int) -> bytes:
    rows = bytearray()
    for y in range(size):
        rows.append(0)
        for x in range(size):
            u, v = (x + .5) / size, (y + .5) / size
            background = .08 < u < .92 and .08 < v < .92
            line = (.23 < u < .76 and abs(v - (.70 - .48 * u)) < .052)
            first = (u - .29) ** 2 + (v - .58) ** 2 < .095 ** 2
            second = (u - .72) ** 2 + (v - .34) ** 2 < .095 ** 2
            color = ((29, 48, 76, 255) if background else (0, 0, 0, 0))
            if line or first or second:
                color = (66, 210, 164, 255)
            rows.extend(color)

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + chunk(b"IEND", b""))


def generate(root: Path = ROOT) -> tuple[Path, Path]:
    images = [(size, _png(size)) for size in (16, 32, 48, 256)]
    icon = root / "assets" / "StockSwitch.ico"
    icon.parent.mkdir(parents=True, exist_ok=True)
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = bytearray()
    for size, data in images:
        entries.extend(struct.pack("<BBBBHHII", 0 if size == 256 else size,
                                   0 if size == 256 else size, 0, 0, 1, 32, len(data), offset))
        offset += len(data)
    icon.write_bytes(header + entries + b"".join(data for _, data in images))

    build = root / "build"
    build.mkdir(exist_ok=True)
    components = tuple(int(part) for part in VERSION.split(".")) + (0,)
    version = build / "version_info.txt"
    version.write_text(
        "VSVersionInfo(ffi=FixedFileInfo(filevers=" + repr(components) +
        ", prodvers=" + repr(components) +
        ", mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)), "
        "kids=[StringFileInfo([StringTable('040904B0', ["
        "StringStruct('CompanyName', 'StockSwitch Project'), "
        "StringStruct('FileDescription', 'StockSwitch Quantitative Research & Paper Trading'), "
        "StringStruct('FileVersion', '" + VERSION + "'), "
        "StringStruct('InternalName', 'StockSwitch'), "
        "StringStruct('OriginalFilename', 'StockSwitch.exe'), "
        "StringStruct('ProductName', 'StockSwitch'), "
        "StringStruct('ProductVersion', '" + VERSION + "')])]), "
        "VarFileInfo([VarStruct('Translation', [1033, 1200])])])\n", encoding="utf-8")
    return icon, version


if __name__ == "__main__":
    print(*generate(), sep="\n")
