# -*- coding: utf-8 -*-
"""Capture ESP32 serial log, reconnecting after USB serial disconnects.

Usage: py -3 scripts/capture_serial_reconnect.py [port] [seconds] [outfile]
"""
import pathlib
import sys
import time

import serial

port = sys.argv[1] if len(sys.argv) > 1 else "COM5"
duration = int(sys.argv[2]) if len(sys.argv) > 2 else 1800
out = pathlib.Path(sys.argv[3] if len(sys.argv) > 3 else "notes/serial_capture.log")

out.parent.mkdir(parents=True, exist_ok=True)
print(f"CAPTURE_START port={port} duration={duration}s out={out}", flush=True)

start = time.time()
last_beat = start
last_open_fail = 0.0
ser = None

with out.open("w", encoding="utf-8", errors="replace") as f:
    f.write(f"# capture {port} 115200 start {time.ctime()}\n")
    f.flush()

    while time.time() - start < duration:
        if ser is None:
            try:
                ser = serial.Serial(port, 115200, timeout=0.2)
                f.write(f"\n# capture connected {time.ctime()}\n")
                f.flush()
                print(f"CAPTURE_CONNECTED {int(time.time() - start)}s", flush=True)
            except Exception as exc:
                now = time.time()
                if now - last_open_fail >= 5:
                    last_open_fail = now
                    print(f"CAPTURE_WAIT_OPEN {int(now - start)}s {exc!r}", flush=True)
                time.sleep(1.0)
                continue

        try:
            data = ser.read(4096)
            if data:
                f.write(data.decode("utf-8", errors="replace"))
                f.flush()
        except Exception as exc:
            print(f"CAPTURE_DISCONNECTED {int(time.time() - start)}s {exc!r}", flush=True)
            f.write(f"\n# capture disconnected {time.ctime()} {exc!r}\n")
            f.flush()
            try:
                ser.close()
            except Exception:
                pass
            ser = None
            time.sleep(1.0)
            continue

        now = time.time()
        if now - last_beat >= 30:
            last_beat = now
            print(f"CAPTURE_ALIVE {int(now - start)}s", flush=True)

    if ser is not None:
        try:
            ser.close()
        except Exception:
            pass
    f.write(f"\n# capture end {time.ctime()}\n")
    f.flush()

print(f"CAPTURE_END {out}", flush=True)
