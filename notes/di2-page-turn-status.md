# Di2 7170 BLE page-turn patch — status 2026-10-19

> **FINAL STATUS: WORKING / hardware-tested.**
> Final image: `extracts/ota_0_app_di2_gui.bin` (checksum `0x79`).
> Final test log: `notes/serial_di2_gui_test4_20261019.log`.
> Handover / restore / new-firmware reproduction: `docs/di2-page-turn.md`.
> - Restore: section 2.
> - Patch locations: sections 3-5.
> - Future stock firmware: section 9.

## Device / firmware
- GEOID CC700 Pro, ESP32-S3, 16 MB flash, 8 MB PSRAM.
- Firmware `CC700Pro_1.9_V1.905-dirty`.
- Full flash backup: `dumps/cc700pro_flash_16MB_v1.905_20261019.bin` (SHA-256 `d40584dd...dac8a8`).
- Original app image for restore: `extracts/ota_0_app.bin` (SHA-256 `26180515...77cfac`, checksum `0xda`).
- Patched app: `extracts/ota_0_app_di2_gui.bin` (SHA-256 `abaff7dd...59bc03`, checksum `0x79`).
- Active partition: `ota_0` at `0x20000`, size `0x7d0000`; `ota_1` at `0x7f0000`, same size.

## Confirmed BLE Di2 chain
- GATT callback: `BLE_Di2_Handler` `0x421e3968`.
- Di2 page-4 mapper: `FUN_4205c178`.
- Logged event: `Di2p4`, `Ch1Pos=1,Ass=0,Evt=1` -> `Get ShftBtnEvent:2-1-0-1`.
- Mapper key codes:
  - single press `2-1-0-1` -> `0x0e`
  - double press `2-1-0-2` -> `0x0f`
  - long press `2-1-0-4` -> `0x10`
- Shared key-injector literal at `0x4203f520`: original `0x422e4138` (empty stub).

## GUI page-switch chain
- Left wrapper `KeyFunc_SwitchPageHorLeft` `0x420f7ef4`:
  - builds 12-byte message at `a1+0x10`
  - key code `0x99` at offset 4
  - calls `FUN_420f65b4`.
- Right wrapper `KeyFunc_SwitchPageHorRight` `0x420f7f78`:
  - builds key code `0x4b` at offset 4
  - actual tail is at `0x420f7fea`: `movi.n a8,0x4b`; `addi a10,a1,0x10`; `s32i.n a8,a1,0x14`; `call8 0x420f65b4`; `retw.n`.
  - It **does** call `FUN_420f65b4`. An earlier note claimed the target was `0x420f657c`; that was from decoding the same bytes at the wrong instruction address (`0x420f7fb9`). At the real call site `0x420f7ff1`, the target is `FUN_420f65b4`.
- GUI queue `_DAT_3c77aa2c` is created by `FUN_420f6594`:
  - `xQueueCreate(0x32, 0xc, 1)` -> 50 items, 12-byte items.
- `FUN_420f65b4(param_1)`:
  - copies 12 bytes from `param_1` to its own stack
  - calls `FUN_4205158c(queue, buffer, 0)` (`xQueueGenericSend`)
  - returns 0 on success.
- GUI handler `FUN_4208e8e0`:
  - key `0x4b` -> `RidePageSwitch(0)`
  - key `0x99` -> `RidePageSwitch(1)`.

## First attempt and crash
- First patch routed `0x0e` to `KeyFunc_SwitchPageHorRight` and `0x0f/0x10` to `KeyFunc_SwitchPageHorLeft`.
- Pressing the Di2 button after BLE connect / ride start produced:
  - `_KeyFunc_SwitchPageHorRight[143]`
  - `Guru Meditation Error: Core 0 panic'ed (Double exception)`
  - backtrace `0x4038f4e3`, `0x4205c32f`.
- Coredump read from `0x10000` to `extracts/coredump_after_di2_crash.bin`.
- Crash stack showed the wrapper frame at `0x3c812390`, copied GUI message at `0x3c812360`, and the BLE-task return address `0x8205c332`.
- Crash PC `0x4038f4e6` is inside the Xtensa window-overflow/underflow handler (the `rotw` sequence), not the GUI code. `EXCCAUSE=2` / `EXCVADDR=0xfffffff4` indicates a double exception while spilling/restoring register windows.
- The first hook used a small frame (`entry a1,0x20`) while calling the full wrapper; the wrapper adds a `0x40` frame plus logging calls. The BLE-task call chain exhausted/overlapped the window spill area. This is why the wrapper/logging path is unsafe from the Di2 BLE callback.

## New lightweight hook (current image)
- Output image: `extracts/ota_0_app_di2_gui.bin`.
- Builder: `scripts/build_patched_app_gui.py`.
- Hook assembler: `scripts/AssembleHookGui.java`.
- Ghidra helpers: `scripts/split_app_segments.py` (split a new app image), `scripts/make_elf.py` (wrap segments into ELF; accepts optional segment dir/output path).
- Cave at `0x422f4d1c`:
  - `0x422f4d1c`: `0x420f65b4`
  - `0x422f4d20`: 0 (reserved)
  - `0x422f4d24`: hook code
- Injector literal at `0x4203f520` changed to `0x422f4d24`.
- Hook behavior:
  - `a2 == 0x0e` -> message key `0x4b` (next)
  - `a2 == 0x0f` or `0x10` -> message key `0x99` (previous)
  - all other key codes ignored
  - entry frame `0x30`; message at `a1+0x10`; saved a0-a3 at `a1+0x20`
  - calls `FUN_420f65b4` directly; no wrapper, no logging.
  - **ABI fix:** the message pointer must be in `a10` (caller-side windowed ABI arg), not `a2`. The physical right wrapper also uses `addi a10,a1,0x10` before the call.
- Image validation:
  - seg3 length `0x2f4d38` (was `0x2f4cfc`)
  - checksum `0x79` (final a10-argument build)
  - `esptool image_info`: checksum valid, hash valid
  - flashed to `ota_0` at `0x20000`, write verification passed.

## Second hardware test (before ABI fix)
- First lightweight hook used `addi a2,a1,0x10`; the Di2 single press caused `LoadProhibited` at PC `0x40056fc0` (`memcpy`), `EXCVADDR=0x48`.
- Backtrace: `memcpy` -> `FUN_420f65b4` -> hook `0x422f4d51` -> injector `0x4205c32f`.
- Cause: `FUN_420f65b4` reads `param_1` from callee `a2`, which is caller `a10`. The hook put the pointer in `a2`, so `FUN_420f65b4` received `0x48` and `memcpy` faulted.
- Fixed by changing the hook instruction to `addi a10,a1,0x10`, rebuilding, and reflashing.
- ESP image footer alignment note: the SHA-256 footer starts on a 16-byte boundary. The builder inserts zero padding before the footer so `(footer_offset + 12) % 16 == 0`.

## Final test result
- Serial capture: `notes/serial_di2_gui_test4_20261019.log` (started after the a10-argument reflash).
- Previous failing capture: `notes/serial_di2_gui_test3_20261019.log` (contains the `LoadProhibited` crash).
- Verified:
  - single press -> `Get ShftBtnEvent:2-1-0-1` -> `Recv GUI event, src:0 type:75` -> page 0->1->2->3;
  - double press -> `Get ShftBtnEvent:2-1-0-2` -> `Recv GUI event, src:0 type:153` -> page 3->2->1->0;
  - no panic/reboot in the final capture;
  - normal shifting unchanged.
- Long press uses the same `0x99` path but was not separately captured as `Evt=4` in the final log; recommend one extra long-press capture if strict confirmation is needed.
- Restore if needed (details, warnings, and validation in `docs/di2-page-turn.md` section 2):
  - App-only, current `ota_0`: `py -3 -m esptool --port COM5 --baud 921600 write_flash 0x20000 extracts/ota_0_app.bin`
  - Both OTA slots (fully remove patch): `py -3 -m esptool --port COM5 --baud 921600 write_flash 0x20000 extracts/ota_0_app.bin 0x7f0000 extracts/ota_0_app.bin`
  - Full 16 MB restore: `py -3 -m esptool --port COM5 --baud 921600 write_flash 0x0 dumps/cc700pro_flash_16MB_v1.905_20261019.bin`
  - Do not use the old V1.905 app to "restore" a newer stock firmware; see section 2.4.
