# GEOID CC700 Pro 固件补丁

把 Shimano Di2 7170 左手变的上方按钮，通过 BLE 映射为 GEOID CC700 Pro
码表的翻页键。原厂固件已经能收到 Di2 按键事件，但共享键值注入点指向一个
空 stub，所以按键不会产生任何界面动作。本仓库记录了这个注入点的定位过程、
最小补丁、镜像重建方法和实机验证结果。

> 适用固件：`CC700Pro_1.9_V1.905-dirty`（V1.905）
>
> 设备：GEOID CC700 Pro，ESP32-S3，16 MB flash，8 MB PSRAM
>
> 状态：Di2 单按/双击翻页已实机验证；长按走同一路径但未单独抓包确认。

> **免责声明**：本项目仅用于个人学习与自用，不得商用或据此获利；未经许可
> 不得重新打包分发；如权利人认为侵权，请通过 Issues 联系，我会立即删除。
> 完整条款见 [`DISCLAIMER.md`](DISCLAIMER.md)。

## 行为

| Di2 操作 | 串口事件 | 注入键值 | GUI 消息 | 码表行为 |
|---|---|---|---|---|
| 单按 | `Get ShftBtnEvent:2-1-0-1` | `0x0e` → `0x4b` | `src:0 type:75` | 下一页 |
| 双击 | `Get ShftBtnEvent:2-1-0-2` | `0x0f` → `0x99` | `src:0 type:153` | 上一页 |
| 长按 | `Get ShftBtnEvent:2-1-0-4` | `0x10` → `0x99` | `src:0 type:153` | 上一页（未单独抓包） |
| 松开 | `Get ShftBtnEvent:2-1-0-0` | 不处理 | 无 | 无动作 |

正常变速不受影响：左手下方按钮仍是前拨 1/2，右手两个按钮仍是后拨升/降。

## 补丁做了什么

功能修改只有两处，另外三处是镜像完整性字段：

| 位置 | 修改 |
|---|---|
| `0x4203f520` 的 4 字节字面量 | `0x422e4138`（空 stub）→ `0x422f4d24`（hook） |
| IROM segment 3 末尾 | 追加 60 字节 cave：GUI 发送函数指针 + 保留字 + 50 字节 hook |
| segment 3 length | `0x2f4cfc` → `0x2f4d38` |
| 镜像 footer | 重算 checksum（`0xda` → `0x79`）和 SHA-256 |
| 镜像尾部 | 重新填充 `0xFF` 到 `0x7d0000` |

hook 只接受 `0x0e/0x0f/0x10`，其他键值直接返回。它不调用完整的
`KeyFunc_SwitchPageHorRight/Left` 包装函数，而是直接构造 12 字节 GUI
消息并调用轻量的 `FUN_420f65b4`。这是为了避免在 BLE 任务上触发
Xtensa 窗口溢出导致的 Double exception。

一个容易踩错的 ABI 细节：`FUN_420f65b4` 是窗口化 ABI 函数，消息指针
必须放在调用方 `a10`，对应被调方 `a2`。写成 `addi a2, a1, 0x10` 会让
被调方读到 `0x48`，在 `memcpy` 里触发 `LoadProhibited`。这个错误已经
在实机上复现过，文档保留了崩溃记录。

## 快速开始

### 0. 已构建镜像

如果不想自己构建，Release 里提供了预构建 app 镜像：

<https://github.com/Bright-codern/geoid-cc700pro-di2-page-turn/releases/tag/v1.905-di2>

- `ota_0_app_di2_gui.bin`：Di2 翻页单补丁，实机验证通过。

附件只包含 app 分区，不含 NVS、BLE 绑定、校准或用户数据；但二进制主体是
厂商 app 代码，无法在不破坏功能的前提下删除。刷写前仍建议按下面的步骤先
备份并确认活动 OTA 槽。

### 1. 先备份并读回 app

下面的示例使用 `COM5`，按实际端口替换。只读回 app 分区不会改动设备；
建议同时保留一份完整 flash 备份。

```powershell
py -3 -m esptool --port COM5 --baud 921600 read_flash 0x0 0x1000000 dumps\cc700pro_flash_backup.bin
py -3 -m esptool --port COM5 --baud 921600 read_flash 0x20000 0x7d0000 extracts\ota_0_app.bin
```

如果当前活动槽是 `ota_1`，app 偏移改为 `0x7f0000`。先看启动日志或
`otadata` 确认，不要猜。

### 2. 构建补丁镜像

要求 Python 3.10+。脚本会校验原厂 app 的 SHA-256、segment 布局、注入点
旧字节和镜像 footer，不匹配就直接拒绝。

```powershell
py -3 scripts\build_patched_app_gui.py
```

默认输入 `extracts\ota_0_app.bin`，输出 `extracts\ota_0_app_di2_gui.bin`。
也可以显式指定：

```powershell
py -3 scripts\build_patched_app_gui.py --input extracts\ota_0_app.bin --output extracts\ota_0_app_di2_gui.bin
```

构建成功的输出应包含：

```text
seg3 length  : 0x2f4cfc -> 0x2f4d38
hook address : 0x422f4d24
checksum     : 0xda -> 0x79
sha256       : abaff7dd921aa6b3a64986c05f988f746d1d658084d72f370c8b4214c859bc03
OK
```

再用 esptool 验证一次镜像结构：

```powershell
py -3 -m esptool image-info extracts\ota_0_app_di2_gui.bin
```

应看到 `Segment 3: Length 0x2f4d38, Load addr 0x42000020`、`Checksum: 0x79 (valid)`、
`Validation hash: 8b3a3296... (valid)`。

### 3. 刷写

```powershell
py -3 -m esptool --port COM5 --baud 921600 write_flash 0x20000 extracts\ota_0_app_di2_gui.bin
```

只写 app 分区，不动 bootloader、分区表、NVS、BLE 绑定和校准数据。

### 4. 回退

```powershell
py -3 -m esptool --port COM5 --baud 921600 write_flash 0x20000 extracts\ota_0_app.bin
```

如果要确保两个 OTA 槽都不含补丁，把原厂 app 同时写入两个槽：

```powershell
py -3 -m esptool --port COM5 --baud 921600 write_flash 0x20000 extracts\ota_0_app.bin 0x7f0000 extracts\ota_0_app.bin
```

## 兼容性与风险

- 所有地址、文件偏移和机器码只对 **V1.905** 成立。厂商发布新固件后，函数和
  字面量池会重排，不能直接复用本仓库的镜像或字节表。
- 不要用 V1.905 的旧 app 去“恢复”已经升级到新版本的设备。先备份新固件，
  再从新 app 重新定位注入点和 GUI 发送函数。
- 刷写有变砖风险。至少保留一份完整 16 MB flash 备份，并确认活动 OTA 槽。
- 本仓库不包含 GEOID 的固件、完整 flash、NVS、BLE 绑定密钥或用户数据；
  补丁脚本只对你自己读回的镜像做字节级修改。
- Di2 键值来自 7170 左手变上方按钮的 BLE page-4 映射。其他 Di2 型号或按键
  配置可能使用不同键值，需要重新抓包确认。

新固件上的完整复现流程见 [`docs/di2-page-turn.md`](docs/di2-page-turn.md)
第 9 节，包括重新定位 BLE handler、键值注入点、GUI 发送函数和选择 cave。

## 目录

| 路径 | 内容 |
|---|---|
| `docs/di2-page-turn.md` | 交接、恢复、补丁位置、新固件复现、调试历史 |
| `scripts/build_patched_app_gui.py` | 生成 Di2 补丁 app 镜像 |
| `scripts/AssembleHookGui.java` | Ghidra 汇编 hook 源码 |
| `scripts/split_app_segments.py` | 拆分 ESP app segment |
| `scripts/make_elf.py` | 把 segment 包装成 Ghidra 可导入的 ELF |
| `notes/di2-page-turn-status.md` | 调试状态与实机结果 |
| `notes/di2-ble-gui-chain.md` | Di2 → GUI 消息链的静态分析摘要 |
| `notes/serial_di2_gui_test4_excerpt.log` | 脱敏后的最终验证日志片段 |

## 验证证据

最终镜像在实机上单按/双击翻页通过，连续操作页码按
`0 -> 1 -> 2 -> 3` 和 `3 -> 2 -> 1 -> 0` 变化，没有出现 `Guru`、
`panic` 或 `LoadProhibited`。脱敏日志片段见
[`notes/serial_di2_gui_test4_excerpt.log`](notes/serial_di2_gui_test4_excerpt.log)。

原始串口日志包含 WiFi SSID/BSSID、云端 token、设备序列号和 Di2 名称，
因此没有上传；仓库里只保留与翻页链路相关的行。

## English summary

GEOID CC700 Pro (ESP32-S3) firmware patch that maps Shimano Di2 7170
BLE button events to page-turn messages. Stock V1.905 routes the Di2
key-injector literal to an empty stub; this patch redirects it to a
50-byte hook that builds the 12-byte GUI message directly and calls the
lightweight queue sender. Hardware-tested for single/double press.
Addresses and bytes apply to V1.905 only. Vendor firmware, full flash
dumps, NVS, BLE keys and raw logs are intentionally not included.
