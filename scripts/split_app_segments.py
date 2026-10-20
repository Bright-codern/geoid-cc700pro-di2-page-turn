#!/usr/bin/env python3
"""Split an ESP32 app image into Ghidra-loadable segment files and a manifest.

Usage:
    py -3 scripts/split_app_segments.py <app.bin> <output_dir>

The output directory is created if needed. It contains one file per segment
(named segN_0xLOAD.bin) and manifest.json. The manifest format matches what
scripts/make_elf.py expects.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path


def guess_flags(load: int) -> int:
    """Return ELF PF_* flags for the ESP32-S3 address range."""
    PF_X, PF_W, PF_R = 1, 2, 4
    if 0x3C000000 <= load < 0x3D000000:      # DROM
        return PF_R
    if 0x3FC00000 <= load < 0x40000000:      # DRAM
        return PF_R | PF_W
    if 0x40300000 <= load < 0x40400000:      # IRAM
        return PF_R | PF_X
    if 0x42000000 <= load < 0x43000000:      # IROM
        return PF_R | PF_X
    return PF_R | PF_X


def parse_image(raw: bytes):
    if len(raw) < 24:
        raise ValueError("file is too small to be an ESP app image")
    if raw[0] != 0xE9:
        raise ValueError(f"bad ESP image magic: 0x{raw[0]:02x}")
    segment_count = raw[1]
    entry = struct.unpack_from("<I", raw, 4)[0]
    segments = []
    off = 24
    for index in range(segment_count):
        if off + 8 > len(raw):
            raise ValueError(f"truncated segment header at file offset 0x{off:x}")
        load, length = struct.unpack_from("<II", raw, off)
        data_off = off + 8
        data = raw[data_off:data_off + length]
        if len(data) != length:
            raise ValueError(
                f"segment {index} truncated: need {length} bytes at 0x{data_off:x}, "
                f"only {len(data)} available"
            )
        segments.append({
            "index": index,
            "load": load,
            "length": length,
            "file_offset": data_off,
            "data": data,
        })
        off = data_off + length
    return entry, segments


def main() -> int:
    parser = argparse.ArgumentParser(description="Split an ESP32 app image into segments.")
    parser.add_argument("app", type=Path, help="input app image (.bin)")
    parser.add_argument("out_dir", type=Path, help="output directory")
    args = parser.parse_args()

    raw = args.app.read_bytes()
    entry, segments = parse_image(raw)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "source": args.app.name,
        "entry": f"0x{entry:08x}",
        "segments": [],
    }
    for seg in segments:
        name = f"seg{seg['index']}_0x{seg['load']:08x}.bin"
        (args.out_dir / name).write_bytes(seg["data"])
        manifest["segments"].append({
            "index": seg["index"],
            "load_addr": f"0x{seg['load']:08x}",
            "length": seg["length"],
            "file": name,
            "flags": guess_flags(seg["load"]),
            "sha256": hashlib.sha256(seg["data"]).hexdigest(),
        })

    (args.out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"source : {args.app}")
    print(f"output : {args.out_dir}")
    print(f"entry  : 0x{entry:08x}")
    for seg in segments:
        print(
            f"  seg{seg['index']}: load=0x{seg['load']:08x} "
            f"len=0x{seg['length']:x} file=0x{seg['file_offset']:x}"
        )
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
