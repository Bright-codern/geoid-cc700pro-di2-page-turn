# -*- coding: utf-8 -*-
"""Wrap ESP32-S3 app segments into a minimal ELF32/Xtensa executable so Ghidra
imports them with correct virtual addresses.

Usage:
    py -3 scripts/make_elf.py [segment_dir] [output_elf]

Defaults:
    segment_dir = extracts/app_segments
    output_elf  = ghidra/cc700pro_app.elf

The segment directory is produced by scripts/split_app_segments.py and must
contain manifest.json plus one segN_0xLOAD.bin per segment. If the manifest has
an "entry" field, it is used; otherwise the V1.905 entry point is the fallback.
"""
import json, pathlib, struct, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SEGDIR = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "extracts" / "app_segments"
OUT = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "ghidra" / "cc700pro_app.elf"

EM_XTENSA = 94
PT_LOAD = 1
PF_X, PF_W, PF_R = 1, 2, 4
FLAGS = {0: PF_R, 1: PF_R | PF_W, 2: PF_R | PF_X, 3: PF_R | PF_X, 4: PF_R | PF_X}

manifest = json.loads((SEGDIR / "manifest.json").read_text(encoding="utf-8"))
ENTRY = int(manifest.get("entry", "0x40375788"), 16)
segs = manifest["segments"]

blobs = []
for seg in segs:
    flags = seg.get("flags")
    if flags is None:
        flags = FLAGS.get(seg["index"], PF_R | PF_X)
    blobs.append({
        "addr": int(seg["load_addr"], 16),
        "data": (SEGDIR / seg["file"]).read_bytes(),
        "flags": flags,
    })

EHSIZE, PHENTSIZE = 52, 32
PHOFF = EHSIZE
PHNUM = len(blobs)
DATA_OFF = 0x1000

cur = DATA_OFF
for b in blobs:
    b["off"] = cur
    cur = (cur + len(b["data"]) + 0xFFF) & ~0xFFF

e_ident = b"\x7fELF" + bytes([1, 1, 1, 0, 0]) + bytes(7)
ehdr = struct.pack(
    "<16sHHIIIIIHHHHHH",
    e_ident, 2, EM_XTENSA, 1, ENTRY, PHOFF, 0, 0,
    EHSIZE, PHENTSIZE, PHNUM, 40, 0, 0,
)
phdrs = b"".join(
    struct.pack(
        "<IIIIIIII", PT_LOAD, b["off"], b["addr"], b["addr"],
        len(b["data"]), len(b["data"]), b["flags"], 0x1000,
    )
    for b in blobs
)

out = bytearray(ehdr + phdrs)
out += b"\x00" * (DATA_OFF - len(out))
for b in blobs:
    out += b"\x00" * (b["off"] - len(out))
    out += b["data"]
    out += b"\x00" * ((-len(out)) % 0x1000)

OUT.write_bytes(bytes(out))
print("wrote:", OUT)
print("size:", len(out))
for b in blobs:
    print(f"  PT_LOAD off=0x{b['off']:06x} vaddr=0x{b['addr']:08x} len={len(b['data'])} flags={b['flags']}")
