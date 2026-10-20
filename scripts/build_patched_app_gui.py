#!/usr/bin/env python3
"""Build a patched CC700 Pro app image that turns Di2 page-4 button events
into the same GUI page-switch messages used by the physical page buttons.

This version avoids calling the full KeyFunc wrappers from the BLE task.
It builds the 12-byte GUI message directly and calls the existing GUI queue
sender FUN_420f65b4, which is much lighter than the wrapper + logging path.

Patch layout (IROM segment, load address 0x42000020):
  0x422f4d1c  u32 FUN_420f65b4 (GUI message send)
  0x422f4d20  u32 0 (reserved)
  0x422f4d24  hook code (50 bytes)
  0x422f4d56  pad to 4-byte boundary

The Di2 mapper's shared key-injector literal at 0x4203f520 is changed from
0x422e4138 (empty stub) to 0x422f4d24 (hook).  The hook receives the Di2 key
code in a2:
  0x0e -> next page (0x4b)
  0x0f -> previous page (0x99, double press)
  0x10 -> previous page (0x99, long press)
Other key codes are ignored.

The message pointer is passed to FUN_420f65b4 in a10 (caller-side windowed
ABI argument), matching the physical KeyFunc_SwitchPageHorRight wrapper.
Writing it to a2 instead makes FUN_420f65b4 read an invalid pointer and crash.

Message layout copied from KeyFunc_SwitchPageHorRight/Left:
  message[0] = 0
  message[1] = key code (offset 4)
  message[2] = 0
  message[3] = 0
"""
from pathlib import Path
import argparse
import hashlib
import struct
import sys

PROJECT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = PROJECT / "extracts" / "ota_0_app.bin"
DEFAULT_OUT = PROJECT / "extracts" / "ota_0_app_di2_gui.bin"

# Exactly the stock V1.905 app partition. Refuse anything else: all offsets
# below are tied to this image.
STOCK_SHA256 = "261805152eb9716ae6ff83a2773b2e3e45d950e0461867ab1ad63280ff77cfac"

GUI_SEND = 0x420F65B4    # FUN_420f65b4, GUI message send
HOOK_ADDR = 0x422F4D24
CAVE_ADDR = 0x422F4D1C
INJECTOR_LITERAL = 0x4203F520
OLD_INJECTOR_VALUE = 0x422E4138

# Ghidra-assembled hook bytes at 0x422f4d24.
#   a8 = key - 0xe; accept only 0xe, 0xf, 0x10 (unsigned < 3)
#   a10 = 0x99 (prev), a11 = 0x4b (next); moveqz selects next for 0xe
HOOK_CODE = bytes.fromhex(
    "366100"          # entry a1, 0x30
    "a2a099"          # movi a10, 0x99
    "b2a04b"          # movi a11, 0x4b
    "82a00e"          # movi a8, 0xe
    "8082c0"          # sub a8, a2, a8
    "c2a003"          # movi a12, 3
    "c7b81a"          # bgeu a8, a12, 0x422f4d54
    "80ab83"          # moveqz a10, a11, a8
    "a26105"          # s32i a10, a1, 0x14
    "82a000"          # movi a8, 0
    "826104"          # s32i a8, a1, 0x10
    "826106"          # s32i a8, a1, 0x18
    "826107"          # s32i a8, a1, 0x1c
    "a2c110"          # addi a10, a1, 0x10 (windowed-ABI arg for FUN_420f65b4)
    "81f3ff"          # l32r a8, 0x422f4d1c
    "e00800"          # callx8 a8
    "1df0"            # retw.n
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Patch a stock GEOID CC700 Pro V1.905 app image for Di2 BLE page turn."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_SRC,
                        help=f"stock app image (default: {DEFAULT_SRC})")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT,
                        help=f"patched app image (default: {DEFAULT_OUT})")
    args = parser.parse_args()

    src = args.input
    out_path = args.output
    if not src.exists():
        raise SystemExit(f"missing source image: {src}")
    raw = bytearray(src.read_bytes())
    source_sha = hashlib.sha256(raw).hexdigest()
    if source_sha != STOCK_SHA256:
        raise SystemExit(
            "source SHA-256 mismatch: this patch only applies to the stock V1.905 app.\n"
            f"  expected: {STOCK_SHA256}\n"
            f"  actual  : {source_sha}"
        )
    image_size = len(raw)
    assert raw[0] == 0xE9, "not an ESP app image"
    seg_count = raw[1]

    segments = []
    off = 24
    for i in range(seg_count):
        load = int.from_bytes(raw[off:off + 4], "little")
        length = int.from_bytes(raw[off + 4:off + 8], "little")
        data_off = off + 8
        data = bytes(raw[data_off:data_off + length])
        segments.append({
            "index": i,
            "hdr_off": off,
            "load": load,
            "length": length,
            "data_off": data_off,
            "data": data,
        })
        off = data_off + length
    footer_off = off

    assert raw[footer_off:footer_off + 11] == b"\x00" * 11, "unexpected footer padding"
    old_checksum = raw[footer_off + 11]
    old_hash = bytes(raw[footer_off + 12:footer_off + 44])
    assert hashlib.sha256(bytes(raw[:footer_off + 12])).digest() == old_hash, "original hash mismatch"
    old_xor = 0xEF
    for seg in segments:
        for v in seg["data"]:
            old_xor ^= v
    assert old_xor == old_checksum, "original checksum mismatch"

    seg3 = segments[3]
    assert seg3["load"] == 0x42000020
    assert seg3["length"] == 0x2F4CFC

    cave = bytearray()
    cave += struct.pack("<I", GUI_SEND)
    cave += struct.pack("<I", 0)
    cave += HOOK_CODE
    assert len(cave) == 58, len(cave)
    cave += b"\x00" * ((-len(cave)) % 4)
    assert len(cave) == 60, len(cave)

    new_seg3 = bytearray(seg3["data"] + cave)
    lit_off = INJECTOR_LITERAL - seg3["load"]
    assert 0 <= lit_off < seg3["length"]
    old_lit = int.from_bytes(new_seg3[lit_off:lit_off + 4], "little")
    assert old_lit == OLD_INJECTOR_VALUE, f"unexpected injector literal {old_lit:#x}"
    new_seg3[lit_off:lit_off + 4] = struct.pack("<I", HOOK_ADDR)

    out = bytearray()
    out += raw[:24]
    for i, seg in enumerate(segments):
        data = new_seg3 if i == 3 else seg["data"]
        out += struct.pack("<II", seg["load"], len(data))
        out += data
    body_end = len(out)
    assert body_end == footer_off + len(cave), (hex(body_end), hex(footer_off + len(cave)))

    # The ESP image checksum is the last byte of a 16-byte block, so the
    # 32-byte SHA-256 that follows starts 16-byte aligned.
    pad_len = (-(body_end + 12)) % 16
    out += b"\x00" * pad_len
    footer_at = len(out)
    assert (footer_at + 12) % 16 == 0

    checksum = 0xEF
    for i, seg in enumerate(segments):
        data = new_seg3 if i == 3 else seg["data"]
        for v in data:
            checksum ^= v

    out += b"\x00" * 11
    out.append(checksum)
    out += hashlib.sha256(bytes(out)).digest()
    assert len(out) == footer_at + 44

    if len(out) > image_size:
        raise SystemExit("patched image exceeds original partition image size")
    out += b"\xFF" * (image_size - len(out))
    assert len(out) == image_size

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(out)

    # Verify the produced image by parsing it back.
    chk = bytes(out)
    assert chk[0] == 0xE9 and chk[1] == seg_count
    p = 24
    parsed = []
    for i in range(seg_count):
        load = int.from_bytes(chk[p:p + 4], "little")
        length = int.from_bytes(chk[p + 4:p + 8], "little")
        data = chk[p + 8:p + 8 + length]
        parsed.append((load, length, data))
        p += 8 + length
    # After the parsed segments, p is the segment end; alignment padding
    # precedes the checksum/hash footer.
    assert p == body_end, (hex(p), hex(body_end))
    assert p + pad_len == footer_at
    assert chk[p:footer_at] == b"\x00" * pad_len
    assert parsed[3][0] == 0x42000020
    assert parsed[3][1] == 0x2F4D38, hex(parsed[3][1])
    assert parsed[3][2][0x2F4CFC:0x2F4CFC + 4] == struct.pack("<I", GUI_SEND)
    assert parsed[3][2][0x2F4CFC + 4:0x2F4CFC + 8] == b"\x00\x00\x00\x00"
    assert parsed[3][2][0x2F4CFC + 8:0x2F4CFC + 8 + len(HOOK_CODE)] == HOOK_CODE
    assert parsed[3][2][lit_off:lit_off + 4] == struct.pack("<I", HOOK_ADDR)

    assert chk[footer_at:footer_at + 11] == b"\x00" * 11
    assert chk[footer_at + 11] == checksum
    assert hashlib.sha256(chk[:footer_at + 12]).digest() == chk[footer_at + 12:footer_at + 44]
    xor2 = 0xEF
    for _, _, data in parsed:
        for v in data:
            xor2 ^= v
    assert xor2 == checksum
    assert all(v == 0xFF for v in chk[footer_at + 44:])

    print(f"source       : {src}")
    print(f"source sha256: {source_sha}")
    print(f"output       : {out_path}")
    print(f"image size   : {image_size:#x} ({image_size})")
    print(f"seg3 length  : {seg3['length']:#x} -> {len(new_seg3):#x}")
    print(f"hook address : {HOOK_ADDR:#x}")
    print(f"injector lit : {OLD_INJECTOR_VALUE:#x} -> {HOOK_ADDR:#x} (file offset {seg3['data_off'] + lit_off:#x})")
    print(f"checksum     : {old_checksum:#04x} -> {checksum:#04x}")
    print(f"sha256       : {hashlib.sha256(chk).hexdigest()}")
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
