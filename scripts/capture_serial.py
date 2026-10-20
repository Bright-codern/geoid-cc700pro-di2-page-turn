# -*- coding: utf-8 -*-
"""Capture ESP32 serial log to a file for a fixed duration.

Usage: py -3 scripts/capture_serial.py [port] [seconds] [outfile]
"""
import pathlib
import sys
import time

import serial

port = sys.argv[1] if len(sys.argv) > 1 else "COM5"
duration = int(sys.argv[2]) if len(sys.argv) > 2 else 300
out = pathlib.Path(sys.argv[3] if len(sys.argv) > 3 else "notes/serial_di2_capture.log")

out.parent.mkdir(parents=True, exist_ok=True)
print(f"CAPTURE_START port={port} duration={duration}s out={out}", flush=True)

try:
    ser = serial.Serial(port, 115200, timeout=0.2)
except Exception as exc:
    print(f"CAPTURE_OPEN_FAILED {exc!r}", flush=True)
    raise SystemExit(1)

start = time.time()
last_beat = start
with out.open("w", encoding="utf-8", errors="replace") as f:
    f.write(f"# capture {port} 115200 start {time.ctime()}\n")
    f.flush()
    try:
        while time.time() - start < duration:
            data = ser.read(4096)
            if data:
                f.write(data.decode("utf-8", errors="replace"))
                f.flush()
            now = time.time()
            if now - last_beat >= 30:
                last_beat = now
                print(f"CAPTURE_ALIVE {int(now - start)}s", flush=True)
    finally:
        ser.close()
        f.write(f"\n# capture end {time.ctime()}\n")
        f.flush()

print(f"CAPTURE_END {out}", flush=True)
