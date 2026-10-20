# 脚本说明

这些脚本按“读回原厂 app → 打补丁 → 校验 → 刷写”的顺序使用。所有地址只对
GEOID CC700 Pro V1.905 成立。

## 构建

| 脚本 | 用途 |
|---|---|
| `build_patched_app_gui.py` | 从原厂 app 生成 Di2 翻页补丁镜像 |

```powershell
py -3 scripts\build_patched_app_gui.py --input extracts\ota_0_app.bin --output extracts\ota_0_app_di2_gui.bin
```

脚本会校验输入镜像的 SHA-256、segment 布局和旧字节，并在写出后重新解析
镜像，逐项验证补丁、checksum 和 SHA-256。

## Ghidra

| 脚本 | 用途 |
|---|---|
| `split_app_segments.py` | 按 ESP app header 拆分 segment，生成 manifest |
| `make_elf.py` | 把 segment 包装成 Ghidra 可导入的 ELF |
| `AssembleHookGui.java` | 在 Ghidra 中汇编 Di2 翻页 hook |
| `DecompileSelected.java` | 批量反编译指定函数 |
| `decompile_selected.py` | `DecompileSelected.java` 的 Python 版本 |
| `PseudoDisasm.java` | 反汇编指定地址范围 |
| `WhoRefs.java` | 查引用 |
| `FindMoviVal.java` | 搜索立即数/字面量 |

典型流程：

```powershell
py -3 scripts\split_app_segments.py extracts\ota_0_app.bin extracts\app_segments
py -3 scripts\make_elf.py extracts\app_segments ghidra\cc700pro_app.elf
```

然后在 Ghidra 中导入 `cc700pro_app.elf`，运行自动分析，再使用其余脚本。

## 串口

| 脚本 | 用途 |
|---|---|
| `capture_serial.py` | 固定时长串口抓包 |
| `capture_serial_reconnect.py` | USB 断线自动重连抓包 |

```powershell
py -3 scripts\capture_serial_reconnect.py COM5 1800 notes\serial_test.log
```

原始串口日志可能包含 WiFi SSID/BSSID、云端 token、设备序列号和配对设备名。
公开分享前先脱敏。
