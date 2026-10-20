# GEOID CC700 Pro：Di2 7170 BLE 按键翻页 — 交接与复现文档

- 文档性质：交接文档（修改说明 + 原厂固件恢复 + 新固件复现指南）
- 当前状态：**实机验证通过**
- 适用固件：`CC700Pro_1.9_V1.905-dirty`
- 设备：GEOID CC700 Pro，ESP32-S3，16 MB flash，8 MB PSRAM
- 最后更新：2026-10-19

> **重要：本文中的地址、文件偏移和机器码只对 V1.905 原厂 app 成立。**
> 如果设备已经升级到新的原厂固件，不要直接刷本文的补丁镜像；按第 9 节重新定位地址、重新生成镜像。
>
> 阅读顺序：只关心恢复 → 第 2 节；只关心改了哪里 → 第 3-5 节；原厂固件更新后复现 → 第 9 节。
>
> **仓库边界**：本仓库只包含补丁脚本、分析文档和脱敏后的证据。厂商原厂固件、完整
> flash 备份、NVS、BLE 绑定密钥、用户数据和原始串口日志都不在仓库内；构建前请从
> 自己的设备读回对应版本的 app 镜像。
>
> **免责声明**：本项目仅用于个人学习与自用，不得商用或据此获利；未经许可不得
> 重新打包分发；如权利人认为侵权，请通过仓库 Issues 联系，我会立即删除。完整
> 条款见仓库根目录 `DISCLAIMER.md`。

---

## 0. 交接摘要

### 0.1 做了什么

把 Di2 7170 左手变速器的**上方信号输出按钮**映射为码表翻页键：

| Di2 操作 | 码表行为 |
|---|---|
| 单按 | 下一页 |
| 双击 | 上一页 |
| 长按 | 上一页 |
| 松开 | 无动作 |

正常变速保持不变：左手下方按钮仍然是前拨 1/2，右手两个按钮仍然是后拨升/降。

### 0.2 修改了什么

功能修改只有两处：

| 序号 | 位置 | 修改 |
|---|---|---|
| 1 | `0x4203f520` 的 4 字节字面量 | `0x422e4138` → `0x422f4d24`，把 Di2 键值注入从空 stub 重定向到 hook |
| 2 | IROM segment 3 末尾追加 60 字节 code cave | `0x422f4d1c` 起：GUI 发送函数指针 + 保留字 + 50 字节 hook + 对齐填充 |

因为 app 镜像结构发生变化，还必须同步更新：

- segment 3 的长度：`0x2f4cfc` → `0x2f4d38`；
- 镜像 footer 的 checksum 和 SHA-256；
- 整个 app 镜像的 0xFF 填充。

这些是**镜像完整性字段**，不是额外的功能修改。

### 0.3 没有修改什么

- 没有改 bootloader；
- 没有改分区表；
- 没有改 NVS、BLE 绑定密钥、校准数据；
- 没有改 GUI 代码和正常变速代码；
- 没有改 ANT+ 路径；本补丁只覆盖已经确认的 BLE Di2 路径。

### 0.4 当前设备状态

- 当前启动槽：`ota_0`，flash 偏移 `0x20000`；
- 当前运行镜像：`extracts/ota_0_app_di2_gui.bin`；
- `ota_1` 在制作备份时为空（全 `0xFF`）；
- 原厂 app 镜像：`extracts/ota_0_app.bin`；
- 完整 16 MB flash 备份：`dumps/cc700pro_flash_16MB_v1.905_20261019.bin`；
- 之前失败版本的 coredump 可能仍在 `coredump` 分区，不影响运行，可按需清理。

### 0.5 还原原厂固件（最短路径）

当前设备活动槽是 `ota_0`，只还原 app、保留 NVS/绑定/校准：

```powershell
py -3 -m esptool --port COM5 --baud 921600 write_flash 0x20000 extracts\ota_0_app.bin
```

为了确保两个 OTA 槽都不再含补丁，把原厂 app 同时写入两个槽：

```powershell
py -3 -m esptool --port COM5 --baud 921600 write_flash 0x20000 extracts\ota_0_app.bin 0x7f0000 extracts\ota_0_app.bin
```

最彻底、回到备份时的完整状态（会覆盖 NVS/BLE 绑定/校准）：

```powershell
py -3 -m esptool --port COM5 --baud 921600 write_flash 0x0 dumps\cc700pro_flash_16MB_v1.905_20261019.bin
```

> 以上命令只是速查；其中的 `extracts\ota_0_app.bin` 和完整备份都是 **V1.905** 版本。
> 如果设备已经升级到新原厂固件，不要用这些旧文件恢复；先看 2.4 节和第 9 节。
> 完整的前置检查、活动槽判断、风险说明和验证步骤见第 2 节。

### 0.6 原厂固件更新后怎么办

不要刷旧的补丁镜像，也不要用旧原厂 app 去“恢复”新固件。正确流程是：

1. 先完整备份新固件；
2. 从设备读回新版本的 app 分区；
3. 在新 app 中重新定位 Di2 注入点和 GUI 发送函数；
4. 重新汇编 hook、更新 builder 常量、重新生成镜像；
5. 校验、刷写、测试。

详细步骤见第 9 节。

---

## 1. 最终行为与验证

### 1.1 行为表

| Di2 操作 | 串口事件 | 注入键值 | GUI 消息 | 码表行为 |
|---|---|---|---|---|
| 单按 | `Get ShftBtnEvent:2-1-0-1` | `0x0e` → `0x4b` | `src:0 type:75` | 下一页 |
| 双击 | `Get ShftBtnEvent:2-1-0-2` | `0x0f` → `0x99` | `src:0 type:153` | 上一页 |
| 长按 | `Get ShftBtnEvent:2-1-0-4` | `0x10` → `0x99` | `src:0 type:153` | 上一页 |
| 松开 | `Get ShftBtnEvent:2-1-0-0` | 不处理 | 无 | 无动作 |

### 1.2 正常变速

- 左手下方按钮：前拨 1/2；
- 右手两个按钮：后拨升/降；
- 补丁只处理 `0x0e`、`0x0f`、`0x10`，其他键值直接返回，不进入 GUI 消息发送。

### 1.3 实机证据

最终抓包：

```text
notes/serial_di2_gui_test4_20261019.log
```

单按：

```text
Di2p4 flag=1ff,seq=5,0,0,0,rcv=5 0 0 0
Ch1Pos=1,Ass=0,Evt=1,Seq=5
Get ShftBtnEvent:2-1-0-1
Recv GUI event, src:0 type:75
YES, RidePageSwitch called by gesture, sLayout.mPageId:0 !
PageId:0 Dial Layout[28]:9
```

连续单按后，页码按 `0 -> 1 -> 2 -> 3` 前进。

双击：

```text
Di2p4 flag=1ff,seq=8,0,0,0,rcv=9 0 0 0
Ch1Pos=1,Ass=0,Evt=2,Seq=9
Get ShftBtnEvent:2-1-0-2
Recv GUI event, src:0 type:153
YES, RidePageSwitch called by gesture, sLayout.mPageId:2 !
PageId:2 Dial Layout[22]:7
```

连续双击后，页码按 `3 -> 2 -> 1 -> 0` 后退。

最终抓包统计：

- `Guru` / `panic` / `LoadProhibited`：0 次；
- `RidePageSwitch called`：10 次，其中 8 次由 Di2 注入消息触发，2 次来自物理按键测试；
- Di2 注入消息：`src:0 type:75` 6 次，`src:0 type:153` 3 次；
- 设备没有因按键重启；
- 正常变速数据继续更新。

### 1.4 长按验证说明

长按在代码中映射为 `0x10 -> 0x99`，和双击走同一条上一页路径。最终这份串口日志中没有捕获到 `Evt=4` / `Get ShftBtnEvent:2-1-0-4`，所以长按尚未由该份日志单独确认。

建议后续补一次长按抓包；不补也不影响已经确认的单按/双击结果。

---

## 2. 还原原厂固件

### 2.1 先确认端口、活动槽和文件

#### 端口

下面的示例使用 `COM5`，这是本次设备的 CDC 串口。换机器或换 USB 口后，端口可能变化。先用设备管理器或 esptool 确认：

```powershell
py -3 -m esptool --port COM5 flash_id
```

如果打不开端口，先关闭串口抓包、串口助手和其他占用 COM5 的程序。

#### 当前活动槽

本次验证时，启动日志和 otadata 都指向 `ota_0`：

```text
ota_0  0x20000  0x7d0000
ota_1  0x7f0000  0x7d0000
otadata 0xd000  0x2000
```

判断活动槽最可靠的方法是看启动日志中的实际加载偏移，例如：

```text
Loaded app from partition at offset 0x20000
```

表示从 `ota_0` 启动；如果显示 `0x7f0000`，则是 `ota_1`。

也可以读 otadata：

```powershell
py -3 -m esptool --port COM5 read_flash 0xd000 0x2000 extracts\otadata_current.bin
```

本次备份中 otadata 首 4 字节为 `01 00 00 00`，对应 `ota_0`。新固件或新设备不要只凭这个值判断，以启动日志为准。

#### 文件与校验值

| 文件 | 大小 | SHA-256 | 说明 |
|---|---:|---|---|
| `extracts/ota_0_app.bin` | `0x7d0000` | `261805152eb9716ae6ff83a2773b2e3e45d950e0461867ab1ad63280ff77cfac` | 原厂 V1.905 app |
| `extracts/ota_0_app_di2_gui.bin` | `0x7d0000` | `abaff7dd921aa6b3a64986c05f988f746d1d658084d72f370c8b4214c859bc03` | 已测试补丁 app |
| `dumps/cc700pro_flash_16MB_v1.905_20261019.bin` | `0x1000000` | `d40584dd83c549bc90080a881ffc0b8003dea643b39514c111a30fce9fdac8a8` | 完整 16 MB 备份 |

已核对：完整备份中 `0x20000` 起、长度 `0x7d0000` 的内容与 `extracts/ota_0_app.bin` 完全一致，说明这份全盘备份确实包含原厂 app。

`extracts/ota_0_app.bin` 是从 `ota_0` 分区读回的 **0x7d0000 字节分区镜像**（包含 app 镜像和尾部 0xFF 填充），不是紧凑的 OTA 包；刷写时写到 `0x20000` 即可。

原厂 app 的 ESP 镜像 checksum 是 `0xda`，补丁 app 是 `0x79`。可以用 `esptool image_info` 复核：

```powershell
py -3 -m esptool image_info extracts\ota_0_app.bin
py -3 -m esptool image_info extracts\ota_0_app_di2_gui.bin
```

> `image_info` 在 esptool 5.6 中会提示已弃用，建议改用 `image-info`；两者都能用。

#### 恢复前先备份当前状态

如果设备里已经有新的骑行数据、新的 BLE 绑定或新的校准，先做一次当前状态的全盘备份：

```powershell
py -3 -m esptool --port COM5 --baud 921600 read_flash 0x0 0x1000000 dumps\cc700pro_flash_before_restore_20261019.bin
```

这样即使恢复错了，也还有退路。

### 2.2 方案 A：只还原 app 分区（保留 NVS/绑定/校准）

这是最常用的“去掉补丁、保留设备数据”方案。

> 下面的 `extracts\ota_0_app.bin` 是 **V1.905 原厂 app**。如果设备已经升级到新固件，不要用它；按 2.4 节先读回新版本 app。

#### 当前活动槽是 ota_0

```powershell
py -3 -m esptool --port COM5 --baud 921600 write_flash 0x20000 extracts\ota_0_app.bin
```

#### 当前活动槽是 ota_1

```powershell
py -3 -m esptool --port COM5 --baud 921600 write_flash 0x7f0000 extracts\ota_0_app.bin
```

#### 不确定活动槽，或想彻底确保两个槽都不含补丁

把原厂 app 同时写到两个 OTA 槽：

```powershell
py -3 -m esptool --port COM5 --baud 921600 write_flash 0x20000 extracts\ota_0_app.bin 0x7f0000 extracts\ota_0_app.bin
```

这样无论 otadata 选择哪个槽，启动的都是原厂 app。写入前确认 `ota_1` 中没有需要保留的回滚版本；如果有，先备份。

#### 验证

1. 断电重启，确认能正常启动；
2. 启动日志中的 app 版本应为 `CC700Pro_1.9_V1.905-dirty`；
3. BLE 能连接 Di2，正常变速；
4. 按 Di2 左上手按钮，串口不应再出现 `Recv GUI event, src:0 type:75/153`，也不应翻页；
5. 如果仍然翻页，说明另一个槽里还有补丁，或者设备仍从旧槽启动；按 2.5 节检查。

### 2.3 方案 B：完整 16 MB flash 还原（最彻底）

```powershell
py -3 -m esptool --port COM5 --baud 921600 write_flash 0x0 dumps\cc700pro_flash_16MB_v1.905_20261019.bin
```

这会恢复：

- bootloader；
- 分区表；
- NVS（包括 BLE 绑定密钥、校准数据）；
- otadata；
- coredump；
- 原厂 app。

注意事项：

1. **只能使用本机的完整备份。** 不要用另一台设备的全盘备份，否则会复制 BLE 身份、绑定关系和校准数据。
2. 恢复后，备份时间之后的骑行记录、设置变更、重新绑定等都会丢失。
3. 如果设备已经升级到新固件，恢复这个旧备份等于降级。确认你确实想回到 V1.905，而不是保留新固件。
4. 完整备份包含敏感数据，不要上传、公开或发给别人。
5. 如果 921600 波特率不稳定，可以降到 460800：

```powershell
py -3 -m esptool --port COM5 --baud 460800 write_flash 0x0 dumps\cc700pro_flash_16MB_v1.905_20261019.bin
```

#### 可选：写回后读回校验

完整写入后，esptool 默认会校验写入数据。需要更强确认时，可以读回整片 flash 并比较 SHA-256：

```powershell
py -3 -m esptool --port COM5 --baud 921600 read_flash 0x0 0x1000000 dumps\verify_restore_20261019.bin
Get-FileHash dumps\verify_restore_20261019.bin -Algorithm SHA256
```

读回文件的 SHA-256 应与备份文件一致：

```text
d40584dd83c549bc90080a881ffc0b8003dea643b39514c111a30fce9fdac8a8
```

16 MB 读取大约需要 1 分钟，耐心等待。

### 2.4 设备已经升级到新原厂固件时怎么恢复

不要用旧的 `extracts/ota_0_app.bin` 去恢复新固件。它会把设备降回 V1.905，而不是“恢复当前原厂状态”。

正确做法：

1. 先完整备份新固件：

```powershell
py -3 -m esptool --port COM5 --baud 921600 read_flash 0x0 0x1000000 dumps\cc700pro_flash_16MB_<新版本>_<日期>.bin
```

2. 确认新固件的活动槽，然后读回对应 app 分区：

```powershell
# 活动槽 ota_0
py -3 -m esptool --port COM5 --baud 921600 read_flash 0x20000 0x7d0000 extracts\ota_0_app_<新版本>.bin

# 活动槽 ota_1
py -3 -m esptool --port COM5 --baud 921600 read_flash 0x7f0000 0x7d0000 extracts\ota_1_app_<新版本>.bin
```

3. 用 `esptool image_info` 确认读回的是有效的 app 镜像，并记录版本、entry、segment 表：

```powershell
py -3 -m esptool image_info <新版本app镜像>
# 例如：extracts\ota_0_app_<新版本>.bin 或 extracts\ota_1_app_<新版本>.bin
```

4. 如果要恢复当前新固件，把读回的新 app 写到当前活动槽；要彻底去补丁，就写到两个槽：

```powershell
py -3 -m esptool --port COM5 --baud 921600 write_flash 0x20000 <新版本app镜像> 0x7f0000 <新版本app镜像>
```

5. 如果新固件的分区布局或 app 分区大小变了，按新分区表调整偏移和长度，不要照抄 `0x20000/0x7d0000`。

### 2.5 OTA A/B 槽：为什么只写一个槽可能不够

本机有两个 OTA app 槽：

```text
ota_0  0x20000  0x7d0000
ota_1  0x7f0000  0x7d0000
```

原厂 OTA 通常会把新固件写到**非活动槽**，然后切换启动槽。因此：

- 补丁刷在 `ota_0`；
- 以后原厂 OTA 可能把新固件写到 `ota_1` 并切换到 `ota_1`；
- 此时 `ota_0` 里仍然是补丁镜像；
- 如果发生回滚、手动切换槽，或者 bootloader 重新选择 `ota_0`，补丁可能再次运行。

所以：

- 只想“当前启动原厂”：写当前活动槽即可；
- 想“彻底不再出现补丁”：写两个槽，或做完整 16 MB 恢复；
- 如果 OTA 后仍然出现翻页，先检查当前启动槽和另一个槽的内容。

### 2.6 恢复后检查清单

- [ ] 启动日志显示正确的 app 版本；
- [ ] `esptool image_info` 对原厂 app 显示 checksum valid、validation hash valid；
- [ ] BLE 能连接 Di2；
- [ ] 左手下方前拨 1/2 正常；
- [ ] 右手后拨升/降正常；
- [ ] Di2 左上手按钮不再触发 `Recv GUI event, src:0 type:75/153`；
- [ ] 没有新的 panic / 重启；
- [ ] 如果恢复了完整备份，骑行记录和设置回到备份时间点（这是预期行为）。

### 2.7 恢复失败时

按以下顺序排查，不要盲目继续刷：

1. **端口/线/供电**：确认 COM 口正确，关闭串口抓包，换 USB 线或 USB 口。
2. **降低波特率**：`--baud 460800` 或 `--baud 115200`。
3. **确认写入偏移**：`ota_0` 是 `0x20000`，`ota_1` 是 `0x7f0000`；不要写错槽。
4. **写两个槽**：排除另一个槽里仍有补丁或损坏镜像。
5. **先重写 ota_0，再擦除 otadata**：

```powershell
py -3 -m esptool --port COM5 --baud 921600 write_flash 0x20000 extracts\ota_0_app.bin
py -3 -m esptool --port COM5 erase_region 0xd000 0x2000
```

这会清除 OTA 选择记录，但不会清除 NVS。只在确认 `ota_0` 已写入有效原厂 app 后使用；顺序不要反，否则写入失败时可能连启动槽记录也没有了。

6. **完整 16 MB 恢复**：如果单 app 恢复无法启动，用 2.3 节的全盘备份恢复。
7. **Secure Boot / Flash Encryption**：如果启动日志显示启用了 Secure Boot 或 Flash Encryption，修改过的 app 无法启动，停止操作，不要继续刷。

---

## 3. 修改位置速查

### 3.1 功能修改

| 序号 | 修改位置 | VA | 文件偏移 | 大小 | 原内容 | 新内容 | 作用 |
|---|---|---|---:|---:|---|---|---|
| 1 | Di2 键值注入字面量 | `0x4203f520` | `0x48f520` | 4 字节 | `0x422e4138` | `0x422f4d24` | 把空 stub 改成 hook |
| 2 | code cave 基址 | `0x422f4d1c` | `0x744d1c` | 60 字节 | segment 3 末尾之后的追加区 | 见 3.2 | 存放 GUI 发送指针和 hook |
| 2a | hook 代码 | `0x422f4d24` | `0x744d24` | 50 字节 | — | 见第 5 节 | 键值判断 + 构造消息 + 发送 |
| 2b | hook 对齐填充 | `0x422f4d56` | `0x744d56` | 2 字节 | — | `00 00` | 4 字节对齐 |

### 3.2 cave 布局

```text
0x422f4d1c  +0x00  u32  0x420f65b4   ; GUI 消息发送函数指针
0x422f4d20  +0x04  u32  0             ; 保留
0x422f4d24  +0x08  hook code          ; 50 字节
0x422f4d56  +0x3a  padding            ; 2 字节
0x422f4d58  +0x3c  segment 4 header   ; 下一个 segment 从这里开始
```

### 3.3 镜像完整性字段（不是功能修改）

| 位置 | 文件偏移 | 原值 | 新值 | 说明 |
|---|---|---:|---:|---|
| segment 3 length 字段 | `0x45001c` | `0x2f4cfc` | `0x2f4d38` | 追加 60 字节后的长度 |
| 镜像 footer | `0x75cfd4` | 原 checksum / SHA | checksum `0x79` + 新 SHA | 由 builder 自动重算 |

> 不要手工改 app 镜像而不重算 segment 长度、checksum 和 SHA-256。ESP 镜像校验会失败，设备也不会正常启动。

### 3.4 文件偏移计算公式

当前 app 的 segment 3：

```text
load address          = 0x42000020
segment data file off = 0x450020
```

任意 VA 对应的文件偏移：

```text
file_offset = 0x450020 + (va - 0x42000020)
```

例子：

```text
注入字面量 VA 0x4203f520
file_offset = 0x450020 + 0x3f500 = 0x48f520

cave VA 0x422f4d1c
file_offset = 0x450020 + 0x2f4cfc = 0x744d1c
```

如果新固件的 segment 布局变了，用 `esptool image-info` 重新取 load address 和 file offset，不要套用上面的数字。

---

## 4. 修改位置 1：Di2 键值注入字面量

### 4.1 当前值

```text
VA          0x4203f520
文件偏移    0x48f520
原值        0x422e4138  （小端字节 38 41 2e 42）
新值        0x422f4d24  （小端字节 24 4d 2f 42）
```

这个字面量位于 Di2 page-4 mapper 的共享键值注入调用点：

```text
BLE_Di2_Handler            0x421e3968
  -> Di2 page-4 mapper     FUN_4205c178
     -> key injector       0x4205c32f
        l32r a8, 0x4203f520
        callx8 a8
```

原目标是空 stub：

```text
0x422e4138:  entry a1, 0x10
             movi.n a2, 0
             retw.n
```

它不做任何事，只是返回 0。把字面量改成 cave 里的 hook 后，Di2 键值会先经过 hook。

### 4.2 为什么改这里

- 这是 Di2 BLE 按键映射完成后的统一注入点；
- 不用改 BLE GATT 解析、不用改按键映射表；
- hook 只过滤 `0x0e/0x0f/0x10`，其他键值原样返回，不影响正常变速；
- 比直接调用完整的 `KeyFunc_SwitchPageHorRight/Left` 包装函数轻得多，避免 BLE 任务上的窗口溢出崩溃。

### 4.3 新固件如何重新定位

原厂固件更新后，地址会变。不要搜索旧值 `0x422e4138` 就以为找到了；旧值也可能被其他常量复用。按下面的顺序定位：

1. **找 Di2 page-4 逻辑**
   - 在 Ghidra 中搜索字符串 `Di2p4`、`Get ShftBtnEvent`、`Ch1Pos`、`Ass`、`Evt`、`Seq`；
   - 找这些字符串的 xref，定位 BLE Di2 handler 和 page-4 mapper；
   - 当前版本对应 `BLE_Di2_Handler` `0x421e3968`、mapper `FUN_4205c178`。

2. **找键值注入调用点**
   - 在 mapper 中找把单按/双击/长按映射为键值的分支；
   - 当前键值是 `0x0e`、`0x0f`、`0x10`；
   - 找调用点附近的 `l32r a8, <literal>` 和 `callx8 a8`；
   - 当前调用点是 `0x4205c32f`，字面量槽是 `0x4203f520`。

3. **确认字面量指向空 stub**
   - 读出字面量指向的函数；
   - 当前是 `0x422e4138`，函数体只有 `entry`、`movi.n a2,0`、`retw.n`；
   - 如果新固件里该目标不是空函数，不要直接覆盖；见 4.5。

4. **确认键值所在寄存器**
   - 当前调用方在 `callx8` 前把键值放在 `a10`；
   - 由于 `call8` 的窗口旋转，被调方看到的是 `a2`；
   - 所以 hook 从 `a2` 读键值；
   - 如果新固件的调用点把键值放在别的寄存器，或者使用 `call4`/`call12`，必须按实际 ABI 调整 hook。

5. **检查 xref**
   - 确认这个字面量/调用点只服务目标 Di2 按键，或者 hook 的键值过滤足够窄；
   - 如果同一注入点还接收其他来源的 `0x0e/0x0f/0x10`，可能会误触发翻页，需要换注入点或增加来源判断。

### 4.4 验证注入点

在 Ghidra 中至少确认：

- [ ] `0x4203f520` 处的 4 字节等于 `0x422e4138`；
- [ ] `0x4205c32f` 是 `callx8`，调用目标来自该字面量；
- [ ] 目标函数是空 stub，返回 0；
- [ ] 调用前键值在 `a10`；
- [ ] 该调用点位于 Di2 page-4 mapper 内；
- [ ] 没有其他关键路径依赖这个空 stub 的返回值。

在镜像中确认：

```text
文件 0x48f520 处应为 38 41 2e 42（原厂）
补丁后应为 24 4d 2f 42
```

### 4.5 如果新固件里目标不是空 stub

不要直接覆盖一个正在工作的函数。可选方案：

1. **改为 hook 调用点**：如果调用点是直接 `call8`/`callx8` 到某个函数，可以把调用目标改成 cave，在 cave 里处理目标键值，其他键值再尾调用原函数。
2. **包装原函数**：hook 先保存现场，对目标键值发 GUI 消息，对其他键值跳回原函数。必须严格保持 ABI 和栈帧。
3. **换注入点**：找 mapper 内更靠近 Di2 按键来源、且只处理目标按键的位置。

无论哪种方案，都要重新验证：

- 正常变速键值不受影响；
- 原函数在非目标键值下仍被调用；
- 没有窗口溢出或栈破坏。

---

## 5. 修改位置 2：代码 cave / hook

### 5.1 当前布局

```text
cave VA       0x422f4d1c
cave 文件偏移 0x744d1c
cave 长度     60 字节
hook VA       0x422f4d24
hook 文件偏移 0x744d24
hook 长度     50 字节
```

cave 位于 IROM segment 3 的末尾。原 segment 3 结束于 `0x422f4cfc`，追加 60 字节后结束于 `0x422f4d38`。原 segment 4 header 在文件偏移 `0x744d1c`；追加 cave 后，它后移到 `0x744d58`，builder 会重新排列所有后续 segment 的文件偏移。

### 5.2 最终 hook 机器码

```text
366100 a2a099 b2a04b 82a00e 8082c0 c2a003 c7b81a 80ab83
a26105 82a000 826104 826106 826107 a2c110 81f3ff e00800
1df0
```

对应汇编：

```asm
entry   a1, 0x30              ; 栈帧 0x30；消息在 a1+0x10，保存区在 a1+0x20
movi    a10, 0x99             ; 默认：上一页
movi    a11, 0x4b             ; 下一页
movi    a8, 0x0e
sub     a8, a2, a8            ; a8 = key - 0x0e
movi    a12, 3
bgeu    a8, a12, done         ; 只接受 0x0e/0x0f/0x10
moveqz  a10, a11, a8          ; key == 0x0e 时选 0x4b
s32i    a10, a1, 0x14         ; message[4] = GUI key
movi    a8, 0
s32i    a8, a1, 0x10          ; message[0] = src = 0
s32i    a8, a1, 0x18          ; message[8] = 0
s32i    a8, a1, 0x1c          ; 对齐填充
addi    a10, a1, 0x10         ; 关键：消息指针放在 a10（调用方窗口参数）
l32r    a8, 0x422f4d1c        ; FUN_420f65b4
callx8  a8
done:
retw.n
```

### 5.3 键值映射

| Di2 键值 `a2` | GUI 键值 | 行为 |
|---:|---:|---|
| `0x0e` | `0x4b` | 下一页 |
| `0x0f` | `0x99` | 上一页（双击） |
| `0x10` | `0x99` | 上一页（长按） |
| 其他 | — | 直接 `retw.n`，不发送消息 |

### 5.4 关键 ABI 细节：`a10` 不是 `a2`

`FUN_420f65b4` 是窗口化 ABI 函数。它的第一个参数在**被调方 `a2`**，对应**调用方 `a10`**。

物理右翻页包装函数的尾部也是这么做的：

```asm
0x420f7fea  movi.n a8, 0x4b
0x420f7fec  addi   a10, a1, 0x10
0x420f7fef  s32i.n a8, a1, 0x14
0x420f7ff1  call8  0x420f65b4
0x420f7ff4  retw.n
```

所以 hook 必须使用：

```asm
addi a10, a1, 0x10
```

不能写成：

```asm
addi a2, a1, 0x10    ; 错误：FUN_420f65b4 会读到无效指针
```

这个错误已经实际导致过 `LoadProhibited`：

```text
PC: 0x40056fc0 (memcpy)
EXCVADDR: 0x00000048
Backtrace: memcpy -> FUN_420f65b4 -> hook 0x422f4d51 -> injector 0x4205c32f
```

### 5.5 栈帧细节

`entry a1, 0x30` 的保存区在 `a1+0x20..a1+0x2f`。hook 把 12 字节消息放在 `a1+0x10..a1+0x1b`，并额外清零 `a1+0x1c`，不会覆盖保存的 `a0-a3`。

如果新 hook 需要更大的消息或更多临时空间：

- 增大 `entry` 的帧；
- 重新计算消息区和保存区，确保不重叠；
- 重新检查 `callx8` 的窗口溢出风险；
- 不要在 BLE 任务里调用带日志、锁或大栈帧的 UI 包装函数。

### 5.6 为什么不能直接调用完整包装函数

第一版尝试把 `0x0e` 路由到 `KeyFunc_SwitchPageHorRight`，把 `0x0f/0x10` 路由到 `KeyFunc_SwitchPageHorLeft`。按下 Di2 按钮后出现：

```text
Guru Meditation Error: Core 0 panic'ed (Double exception)
PC: 0x4038f4e6
Backtrace: 0x4038f4e3 ... |<-CORRUPTED
```

`0x4038f4e6` 位于 Xtensa 窗口溢出/恢复处理器，不是 GUI 代码。包装函数还会打日志，调用链远重于必要的消息发送。最终改为：

- 不调用包装函数；
- 直接构造 12 字节 GUI 消息；
- 直接调用轻量的 `FUN_420f65b4`。

### 5.7 新固件如何选择 code cave

原则：选择一段**可执行、不会被引用、追加后不会覆盖其他 segment**的空间。

当前做法：

```text
cave_va = segment_load + original_segment_length
cave_file_off = segment_data_file_off + original_segment_length
```

当前：

```text
cave_va = 0x42000020 + 0x2f4cfc = 0x422f4d1c
cave_file_off = 0x450020 + 0x2f4cfc = 0x744d1c
```

新固件推荐：

1. 用 `esptool image-info` 找到 IROM segment（load 地址通常在 `0x42000000` 附近）；
2. 读取 segment 长度和文件偏移；
3. 在该 segment 末尾追加 cave；
4. 确认追加后不会与下一个 segment 的 header/data 重叠；
5. 确认 app 镜像总大小仍在 app 分区内（当前分区 `0x7d0000`，实际镜像体只到 `0x75cfd0`，有充足填充空间）；
6. 确认 cave 位于可执行内存，且 `l32r` 能到达函数指针字面量。

如果新固件的 IROM segment 不是 index 3，或者 segment 3 不是 IROM，需要修改 builder 的 segment index/断言，或者把 cave 放到另一个可执行 segment。

### 5.8 重新汇编 hook

`scripts/AssembleHookGui.java` 目前硬编码了：

```text
hook 起始地址        0x422f4d24
条件跳转目标         0x422f4d54
函数指针字面量地址   0x422f4d1c
```

新固件必须同步修改：

1. `Address at = ...` 改成新 hook 地址；
2. `bgeu a8, a12, ...` 的目标改成新 `retw.n` 地址；
3. `l32r a8, ...` 的目标改成新 cave 中的函数指针地址；
4. 在 Ghidra 中运行脚本，记录输出的 `HOOK_HEX`、`HOOK_LEN`、`HOOK_END`；
5. 确认 hook 长度仍为 50 字节；如果变了，同步调整 cave 布局、builder 中的长度断言和 segment 长度；
6. 把 `HOOK_HEX` 粘贴到 `build_patched_app_gui.py` 的 `HOOK_CODE`。

> 不要直接复制本文的 50 字节机器码到新固件。分支偏移、`l32r` 偏移和函数地址都变了。

### 5.9 cave 约束

- 必须 4 字节对齐；
- 函数指针字面量必须在 hook 的 `l32r` 可达范围内；
- hook 不能覆盖 segment 4 的 header；
- hook 不能写入只读数据段；
- hook 不能调用会阻塞、打日志或占用大栈帧的 UI 包装函数；
- hook 只做键值判断、12 字节消息构造和一次非阻塞队列发送；
- 如果新固件的 GUI 发送函数不是线程安全的，改为在 GUI 任务中消费标志，不要从 BLE 任务直接调用 UI 代码。

---

## 6. GUI 翻页消息链

### 6.1 调用链

```text
物理翻页按键 / Di2 hook
  -> 构造 12 字节消息
     offset 0: src  = 0
     offset 4: type = 0x4b（下一页）或 0x99（上一页）
     offset 8: 0
  -> FUN_420f65b4
       -> 复制 12 字节到栈
       -> FUN_4205158c(queue, msg, 0)   ; xQueueGenericSend
  -> GUI 事件循环 FUN_420f5ed4
       -> 日志：Recv GUI event, src:0 type:75/153
       -> 键处理 FUN_4208e8e0
           0x4b -> RidePageSwitch(0)   ; 下一页
           0x99 -> RidePageSwitch(1)   ; 上一页
```

### 6.2 消息布局

| 偏移 | 长度 | 值 | 说明 |
|---:|---:|---:|---|
| 0 | 4 | 0 | 消息来源；0 表示按键/手势路径 |
| 4 | 4 | `0x4b` / `0x99` | GUI 键值 |
| 8 | 4 | 0 | 保留 |

总长度 12 字节。GUI 队列由 `FUN_420f6594` 创建：

```c
xQueueCreate(0x32, 0xc, 1);   /* 50 项，每项 12 字节 */
```

如果新固件的队列项大小变了，hook 构造的消息长度也必须跟着变。

### 6.3 当前版本地址

| 对象 | 地址 |
|---|---|
| 左翻页包装函数 | `0x420f7ef4` |
| 右翻页包装函数 | `0x420f7f78` |
| 右包装函数消息发送尾部 | `0x420f7fea` |
| GUI 消息发送 | `0x420f65b4` |
| GUI 队列句柄持有者 | `0x3c77aa2c` |
| GUI 队列创建 | `0x420f6594` |
| GUI 事件循环 | `0x420f5ed4` |
| GUI 键处理 | `0x4208e8e0` |

### 6.4 新固件如何定位 GUI 发送路径

1. **找翻页相关字符串/xref**
   - 搜索 `RidePageSwitch called by gesture`、`PageSettingEventCbDeleteCanvas`、`Dial Layout`、`Recv GUI event`；
   - 找 `RidePageSwitch` 的 xref 和 page button handler。

2. **找物理翻页包装函数**
   - 当前左包装 `0x420f7ef4` 使用 `0x99`；
   - 当前右包装 `0x420f7f78` 使用 `0x4b`；
   - 两者都构造 12 字节消息，并在尾部调用同一个发送函数；
   - 右包装的真实尾部在 `0x420f7fea`，调用目标是 `FUN_420f65b4`。

3. **找 GUI 队列**
   - 搜索 `xQueueCreate` 调用；
   - 当前参数是 `0x32`（50 项）和 `0xc`（12 字节）；
   - 跟踪返回的队列句柄，当前是 `_DAT_3c77aa2c`；
   - 找引用该句柄并调用 `xQueueGenericSend` 的函数，就是发送函数。

4. **确认消息布局**
   - 反编译包装函数；
   - 确认消息偏移 0 是 src，偏移 4 是 key；
   - 确认 key `0x4b` 对应下一页，`0x99` 对应上一页；
   - 如果 key 或偏移变了，修改 hook。

5. **确认 ABI**
   - 反汇编包装函数尾部的 `call8`/`callx8`；
   - 确认发送函数的第一个参数在调用方哪个寄存器；
   - 当前是 `addi a10,a1,0x10`，被调方看到 `a2`；
   - 如果使用 `call4`/`call12`，窗口旋转不同，必须重新确认。

### 6.5 如果发送函数被内联

新固件可能把 `FUN_420f65b4` 内联，或者换名。此时：

1. 找队列句柄和 `xQueueGenericSend` 调用；
2. 确认队列项大小是 12；
3. 在 hook 中直接调用 `xQueueGenericSend(queue, msg, 0, 0)`；
4. 严格确认 RTOS API 的参数顺序和调用方 ABI；
5. 这是最后手段，优先使用现有的 12 字节发送函数。

如果发送函数不是线程安全的，改用“hook 置标志，GUI 任务轮询发送”的方案，不要从 BLE 任务直接操作 UI。

---

## 7. 构建、校验、刷写、测试（当前版本）

### 7.1 前置条件

- Python 3 + esptool；
- 已安装 Ghidra（仅重新汇编 hook 时需要）；
- 已确认 COM 口；
- 已做完整 flash 备份；
- 已确认当前活动槽；
- 设备电量充足，USB 连接稳定。

### 7.2 构建

```powershell
cd <仓库根目录>
py -3 scripts\build_patched_app_gui.py
```

预期输出：

```text
image size   : 0x7d0000 (8192000)
seg3 length  : 0x2f4cfc -> 0x2f4d38
hook address : 0x422f4d24
injector lit : 0x422e4138 -> 0x422f4d24 (file offset 0x48f520)
checksum     : 0xda -> 0x79
sha256       : abaff7dd921aa6b3a64986c05f988f746d1d658084d72f370c8b4214c859bc03
OK
```

### 7.3 校验镜像

```powershell
py -3 -m esptool image_info extracts\ota_0_app_di2_gui.bin
```

应看到：

```text
Segment 3: Length 0x2f4d38, Load addr 0x42000020
Checksum: 0x79 (valid)
Validation hash: 8b3a3296d9e1b6e68a670fc2217036d479d1aec797594d97c49148a6a76e44ea (valid)
App version: CC700Pro_1.9_V1.905-dirty
```

注意区分两个哈希：

- `Validation hash`：ESP 镜像内部校验，当前 `8b3a...`；
- 文件 SHA-256：整个 `0x7d0000` 文件（含 0xFF 填充），当前 `abaff...`。

### 7.4 再次备份

刷写前，如果设备里有新数据，先备份当前完整 flash：

```powershell
py -3 -m esptool --port COM5 --baud 921600 read_flash 0x0 0x1000000 dumps\cc700pro_flash_before_patch_<日期>.bin
```

### 7.5 刷写

当前活动槽是 `ota_0`：

```powershell
py -3 -m esptool --port COM5 --baud 921600 write_flash 0x20000 extracts\ota_0_app_di2_gui.bin
```

写入成功应看到：

```text
Wrote 8192000 bytes ...
Hash of data verified.
Hard resetting via RTS pin...
```

如果活动槽是 `ota_1`，地址改为 `0x7f0000`。如果不确定，先看启动日志，不要猜。

### 7.6 测试步骤

1. 设备正常启动；
2. BLE 连接 Di2（使用你自己的 Di2 BLE 名称）；
3. 开始骑行记录；
4. 单按左上手按钮 → 下一页，设备不重启；
5. 双击 → 上一页；
6. 长按 → 上一页（建议补抓包）；
7. 左手下方前拨 1/2，右手后拨升/降，确认正常；
8. 串口检查 `Recv GUI event, src:0 type:75/153`，且没有 `Guru` / `LoadProhibited`。

串口抓包：

```powershell
py -3 scripts\capture_serial_reconnect.py COM5 1800 notes\serial_di2_gui_test_<日期>.log
```

### 7.7 失败回退

如果按键后重启、死机或不翻页：

```powershell
py -3 -m esptool --port COM5 --baud 921600 write_flash 0x20000 extracts\ota_0_app.bin
```

然后读 coredump、检查串口日志，再决定是否继续调试。不要在没有备份的情况下反复刷写。

---

## 8. 当前镜像与文件清单

### 8.1 镜像

| 文件 | 大小 | checksum | SHA-256 | 用途 |
|---|---:|---:|---|---|
| `extracts/ota_0_app.bin` | `0x7d0000` | `0xda` | `261805152eb9716ae6ff83a2773b2e3e45d950e0461867ab1ad63280ff77cfac` | 原厂 app，恢复用 |
| `extracts/ota_0_app_di2_gui.bin` | `0x7d0000` | `0x79` | `abaff7dd921aa6b3a64986c05f988f746d1d658084d72f370c8b4214c859bc03` | 已测试补丁 app |
| `dumps/cc700pro_flash_16MB_v1.905_20261019.bin` | `0x1000000` | — | `d40584dd83c549bc90080a881ffc0b8003dea643b39514c111a30fce9fdac8a8` | 完整 16 MB 恢复点 |

### 8.2 代码和脚本

| 文件 | 用途 |
|---|---|
| `scripts/build_patched_app_gui.py` | 生成补丁 app 镜像 |
| `scripts/AssembleHookGui.java` | Ghidra 汇编 hook 源码 |
| `scripts/capture_serial.py` | 固定时长串口抓包 |
| `scripts/capture_serial_reconnect.py` | USB 断线自动重连抓包 |
| `scripts/split_app_segments.py` | 按 ESP app header 拆分 segment，生成 manifest |
| `scripts/make_elf.py` | 把 app segment 包装成 Ghidra 可导入的 ELF |
| `scripts/decompile_selected.py` | Ghidra 批量反编译指定函数 |
| `scripts/PseudoDisasm.java` | Ghidra 指定地址反汇编 |
| `ghidra/cc700pro.gpr` + `ghidra/cc700pro.rep` | 已分析的 Ghidra 项目 |
| `ghidra/cc700pro_app.elf` | 供 Ghidra 导入的包装 ELF |

### 8.3 日志和记录

| 文件 | 用途 |
|---|---|
| `notes/serial_di2_gui_test4_20261019.log` | 最终成功日志 |
| `notes/serial_di2_gui_test3_20261019.log` | `a2/a10` 错误版本的崩溃日志 |
| `notes/di2_page_turn_status.md` | 调试过程与状态记录 |
| `notes/00-findings-ledger.md` | 逆向发现台账 |
| `notes/decompile_gui_dispatch.txt` | GUI 事件循环反编译 |
| `docs/di2-page-turn.md` | 本文档，交接与复现 |

### 8.4 敏感数据

完整 flash 备份包含：

- NVS；
- BLE 绑定密钥；
- 校准数据；
- 设备配置。

不要上传、公开或发给别人。需要分享分析结果时，只分享代码、地址、日志片段和脱敏后的结论。

---

## 9. 原厂固件更新后的复现流程

> 这一节是交接文档的核心。原厂固件更新后，地址、函数、消息布局和键值都可能变化；不要直接复用旧镜像或旧机器码。

### 9.1 原则

1. **地址绑定版本**：本文所有地址只对 V1.905 成立。
2. **先备份，再动手**：新固件也要先做完整备份和 app 分区备份。
3. **最小修改**：只改 Di2 键值注入点和 cave；不要改 bootloader、分区表、NVS、GUI 主体。
4. **不调用重包装**：不要在 BLE 任务里调用完整翻页包装函数。
5. **逐步验证**：先确认 GUI 路径，再确认 Di2 路径，最后才写 hook。
6. **失败可回退**：每一步都保留原厂镜像和完整备份。

### 9.2 第一步：归档新原厂固件

```powershell
# 1) 完整备份
py -3 -m esptool --port COM5 --baud 921600 read_flash 0x0 0x1000000 dumps\cc700pro_flash_16MB_<新版本>_<日期>.bin

# 2) 确认活动槽后读回 app
# ota_0:
py -3 -m esptool --port COM5 --baud 921600 read_flash 0x20000 0x7d0000 extracts\ota_0_app_<新版本>.bin
# ota_1:
py -3 -m esptool --port COM5 --baud 921600 read_flash 0x7f0000 0x7d0000 extracts\ota_1_app_<新版本>.bin

# 3) 记录版本、entry、segment 表（用实际读回的 app 文件）
py -3 -m esptool image_info <新版本app镜像>
```

记录：

- app 版本；
- entry point；
- segment 数量；
- 每个 segment 的 load address、length、file offset；
- checksum、validation hash；
- app 分区偏移和大小。

如果厂商提供 OTA 包，优先从设备 flash 读回；OTA 包格式可能不是裸 app 镜像。

### 9.3 第二步：导入 Ghidra

当前项目使用两个脚本：

- `scripts/split_app_segments.py`：按 ESP app header 拆分 segment，生成 `manifest.json` 和 `segN_0xLOAD.bin`；
- `scripts/make_elf.py`：把 segment 包装成 Ghidra 可导入的 ELF。

新固件流程：

```powershell
# 1) 拆分新 app（用实际读回的 app 文件）
py -3 scripts\split_app_segments.py <新版本app镜像> extracts\app_segments_<新版本>

# 2) 生成 ELF（entry 从 manifest.json 读取）
py -3 scripts\make_elf.py extracts\app_segments_<新版本> ghidra\cc700pro_app_<新版本>.elf
```

然后在 Ghidra 中：

1. 新建项目，或复制现有项目；
2. 导入新的 `ghidra\cc700pro_app_<新版本>.elf`；
3. 运行自动分析；
4. 保留旧项目作为对照，不要覆盖旧版本。

`make_elf.py` 的默认参数仍然指向 `extracts/app_segments` 和 `ghidra/cc700pro_app.elf`；不传参数时行为与旧版本一致。新固件建议显式传路径，避免覆盖旧分析。

> 如果新 app 的 segment 数量或内存类型与当前版本不同，先检查 `split_app_segments.py` 生成的 flags 是否合理；必要时在 manifest 中手动修正 `flags`。

### 9.4 第三步：定位 GUI 翻页路径

先找“翻页消息怎么发”，因为这部分比 Di2 协议更稳定。

1. 搜索字符串：
   - `RidePageSwitch called by gesture`
   - `PageSettingEventCbDeleteCanvas`
   - `Dial Layout`
   - `Recv GUI event`
2. 找 `RidePageSwitch` 的 xref；
3. 找物理翻页按键的包装函数；
4. 确认它们构造的消息：
   - 12 字节；
   - offset 0 = 0；
   - offset 4 = `0x4b`（下一页）或 `0x99`（上一页）；
5. 找两个包装函数共同调用的发送函数；
6. 确认发送函数：
   - 复制 12 字节；
   - 调用 `xQueueGenericSend`；
   - 队列由 `xQueueCreate(0x32, 0xc, 1)` 创建；
7. 反汇编包装函数尾部，确认发送函数的第一个参数在调用方哪个寄存器；
8. 记录新地址，填入下表：

| 对象 | 新地址 | 备注 |
|---|---|---|
| 左翻页包装 |  |  |
| 右翻页包装 |  |  |
| 发送函数 |  |  |
| 队列句柄 |  |  |
| 队列创建 |  |  |
| GUI 事件循环 |  |  |
| GUI 键处理 |  |  |

如果找不到 12 字节消息或 `xQueueCreate(50,12,1)`，不要假设布局没变；按实际反编译结果调整 hook。

### 9.5 第四步：定位 Di2 注入点

1. 搜索 `Di2p4`、`Get ShftBtnEvent`、`Ch1Pos`、`Ass`、`Evt`、`Seq`；
2. 找 BLE Di2 handler 和 page-4 mapper；
3. 找 mapper 中把按键事件映射为键值的分支；
4. 找键值注入调用点：
   - `l32r a8, <literal>`
   - `callx8 a8`
5. 读字面量目标：
   - 当前是空 stub `0x422e4138`；
   - 新固件可能仍是空 stub，也可能已经变成真实函数；
6. 确认键值所在寄存器；
7. 确认键值：
   - 单按 `0x0e`；
   - 双击 `0x0f`；
   - 长按 `0x10`；
8. 检查 xref，确认注入点只服务目标按键，或者 hook 过滤足够窄。

记录：

| 对象 | 新地址/值 | 备注 |
|---|---|---|
| BLE Di2 handler |  |  |
| page-4 mapper |  |  |
| 注入调用点 |  |  |
| 注入字面量槽 |  |  |
| 原 stub |  | 是否为空 |
| 键值寄存器 |  | 调用方 |
| 单按键值 |  |  |
| 双击键值 |  |  |
| 长按键值 |  |  |

### 9.6 第五步：确认键值和正常变速

在改代码前，先用串口确认新固件的行为：

```powershell
py -3 scripts\capture_serial_reconnect.py COM5 1800 notes\serial_new_fw_di2.log
```

依次操作：

1. BLE 连接 Di2；
2. 开始骑行记录；
3. 单按左上手按钮；
4. 双击；
5. 长按；
6. 左手下方前拨；
7. 右手后拨升/降。

在日志中确认：

- 单按/双击/长按对应的 `Get ShftBtnEvent`；
- mapper 是否仍使用 `0x0e/0x0f/0x10`；
- 正常变速键值是否与目标键值冲突。

如果新固件的键值变了，修改 hook 的过滤和映射；不要硬套旧值。

### 9.7 第六步：选择 cave 并重新汇编 hook

1. 从新 app 的 IROM segment 末尾选择 cave；
2. 计算：

```text
cave_va = segment_load + original_segment_length
cave_file_off = segment_data_file_off + original_segment_length
```

3. 预留：

```text
+0x00  u32 新 GUI 发送函数地址
+0x04  u32 0
+0x08  hook code
+...   padding 到 4 字节
```

4. 修改 `scripts/AssembleHookGui.java`：
   - `Address at` = 新 hook 地址；
   - 条件跳转目标 = 新 `retw.n` 地址；
   - `l32r` 目标 = 新函数指针字面量地址；
5. 在 Ghidra 中运行脚本；
6. 记录 `HOOK_HEX`、`HOOK_LEN`、`HOOK_END`；
7. 检查 hook 长度；如果不再是 50 字节，更新 cave 布局和 builder 断言。

### 9.8 第七步：更新 builder 常量

`scripts/build_patched_app_gui.py` 中需要检查/修改：

| 常量/断言 | 当前值 | 新固件操作 |
|---|---|---|
| `SRC` | `extracts/ota_0_app.bin` | 改成新原厂 app 路径 |
| `OUT` | `extracts/ota_0_app_di2_gui.bin` | 改成新输出路径 |
| `GUI_SEND` | `0x420f65b4` | 改成新发送函数地址 |
| `HOOK_ADDR` | `0x422f4d24` | 改成新 hook 地址 |
| `CAVE_ADDR` | `0x422f4d1c` | 改成新 cave 基址 |
| `INJECTOR_LITERAL` | `0x4203f520` | 改成新注入字面量槽 |
| `OLD_INJECTOR_VALUE` | `0x422e4138` | 改成新原 stub 地址 |
| `HOOK_CODE` | 50 字节 | 粘贴新 `HOOK_HEX` |
| `seg3` 断言 | load `0x42000020`, len `0x2f4cfc` | 改成新 IROM segment 的 load/length；如果 index 不是 3，也要改 |
| `len(cave) == 58` / `60` | 固定 60 字节 | 如果 hook 长度变了，同步修改 |
| `parsed[3][1] == 0x2F4D38` | 固定新长度 | 改成新长度 |

builder 里的断言是**故意设置的 fail-safe**：如果新固件的长度、原值或布局不符合预期，它会直接失败，而不是生成一个坏镜像。不要为了“让它跑通”而删除断言；应按新固件更新断言值。

### 9.9 第八步：构建和校验

```powershell
py -3 scripts\build_patched_app_gui.py
py -3 -m esptool image_info extracts\ota_0_app_di2_gui_<新版本>.bin
```

检查：

- [ ] segment 数量与原文一致；
- [ ] IROM segment 长度增加了 cave 大小；
- [ ] 下一个 segment 的 file offset 相应后移；
- [ ] checksum valid；
- [ ] validation hash valid；
- [ ] 文件大小不超过 app 分区；
- [ ] 文件 SHA-256 记录到文档。

如果 `image_info` 报 checksum/hash 无效，检查：

- footer 是否 16 字节对齐；
- segment 长度是否更新；
- checksum 是否覆盖了所有 segment；
- SHA 是否覆盖到 checksum 字节为止。

### 9.10 第九步：刷写和测试

刷写前：

```powershell
py -3 -m esptool --port COM5 --baud 921600 read_flash 0x0 0x1000000 dumps\cc700pro_flash_before_new_patch_<日期>.bin
```

刷写当前活动槽（示例假设活动槽是 `ota_0`；如果启动日志显示 `ota_1`，地址改为 `0x7f0000`）：

```powershell
py -3 -m esptool --port COM5 --baud 921600 write_flash 0x20000 extracts\ota_0_app_di2_gui_<新版本>.bin
```

测试：

1. 正常启动；
2. BLE 连接 Di2；
3. 开始骑行；
4. 单按下一页；
5. 双击上一页；
6. 长按上一页；
7. 正常变速；
8. 串口无 panic/重启；
9. 日志出现 `Recv GUI event, src:0 type:75/153`。

失败立即回退（同样按实际活动槽调整；`ota_1` 用 `0x7f0000`）：

```powershell
py -3 -m esptool --port COM5 --baud 921600 write_flash 0x20000 <新版本app镜像>
```

### 9.11 第十步：更新交接文档

成功之后，更新本文档：

- 新固件版本；
- 新 app 的 SHA-256、checksum、validation hash；
- 新地址表；
- 新 hook 字节和长度；
- 新 cave 地址/文件偏移；
- 新测试日志；
- 已知限制。

否则下一位接手的人会以为旧地址仍然有效。

### 9.12 复现检查清单（Go / No-Go）

动手前：

- [ ] 已做完整 16 MB 备份；
- [ ] 已读回新原厂 app；
- [ ] `image_info` 显示 app 有效；
- [ ] 已确认活动槽；
- [ ] 已确认没有 Secure Boot / Flash Encryption；
- [ ] 已记录分区表和 app 分区大小。

定位阶段：

- [ ] 找到 GUI 翻页包装函数；
- [ ] 找到 12 字节 GUI 发送函数；
- [ ] 确认消息布局和 key `0x4b/0x99`；
- [ ] 确认发送函数的调用方 ABI 寄存器；
- [ ] 找到 Di2 page-4 mapper；
- [ ] 找到键值注入点；
- [ ] 确认原目标是空 stub；
- [ ] 确认键值和正常变速键值不冲突。

生成阶段：

- [ ] cave 在可执行 segment 内；
- [ ] cave 不覆盖下一个 segment；
- [ ] hook 已重新汇编，不是复制旧字节；
- [ ] `l32r` 可达函数指针；
- [ ] hook 长度和 cave 布局一致；
- [ ] builder 断言已按新值更新；
- [ ] `image_info` checksum/hash valid。

测试阶段：

- [ ] 设备正常启动；
- [ ] BLE Di2 连接；
- [ ] 单按下一页；
- [ ] 双击上一页；
- [ ] 长按上一页；
- [ ] 正常变速；
- [ ] 无 panic/重启；
- [ ] 串口日志有 `src:0 type:75/153`。

任何一项不满足，不要继续刷写；先回退并检查。

### 9.13 常见问题定位树

| 现象 | 可能原因 | 检查 |
|---|---|---|
| 按键后完全没反应 | 注入点没命中 / hook 没执行 | 日志是否有 `Get ShftBtnEvent`；字面量是否改对；hook 地址是否可执行 |
| 有 `Get ShftBtnEvent`，但没有 `Recv GUI event` | hook 未发送 / 发送函数地址错 / 消息布局错 | hook 是否过滤了该键值；`FUN_420f65b4` 地址；消息 offset 4；队列句柄 |
| 有 `Recv GUI event`，但页码不变 | GUI key 不对 / GUI handler 变了 | 日志中的 type 是 75/153 吗；新固件的 key 映射 |
| 按键后重启 / Double exception | 调用了重包装 / 栈帧太小 / 窗口溢出 | 不要调用 `KeyFunc_*`；检查 `entry` 帧和保存区 |
| 按键后 LoadProhibited | ABI 参数错 / 消息指针错 | 发送函数第一个参数是否在调用方 `a10`；是否误写 `a2` |
| 正常变速受影响 | hook 过滤太宽 / 键值冲突 | 只接受 `0x0e/0x0f/0x10`；检查新固件键值 |
| 一次按键翻两页 | 按下和松开都映射 / 双击事件重复 | 过滤 release 事件；确认 `Evt` 值 |
| 只有单按有效，双击/长按无效 | 键值映射变了 | 重新抓 `Get ShftBtnEvent`；检查 mapper 分支 |
| `image_info` 校验失败 | segment 长度/checksum/SHA/footer 对齐错 | 用 builder 重新生成；不要手改 |
| 刷写后不启动 | 写错槽 / 镜像损坏 / Secure Boot | 检查偏移；回退原厂；检查启动日志 |

### 9.14 停止条件

出现以下情况时停止修改，先恢复原厂：

- 启动日志显示 Secure Boot 或 Flash Encryption 已启用；
- 新固件的分区布局与备份不一致，且无法确认 app 分区；
- 找不到空 stub，且无法安全包装原函数；
- 无法确认 GUI 发送函数的 ABI；
- 无法确认队列项大小或消息布局；
- 没有完整备份；
- 设备出现无法回退的启动问题。

---

## 10. 调试历史与已确认的坑

### 10.1 第一次：调用完整包装函数导致 Double exception

第一版 hook 直接调用 `KeyFunc_SwitchPageHorRight/Left` 包装函数。按键后：

```text
Guru Meditation Error: Core 0 panic'ed (Double exception)
PC: 0x4038f4e6
Backtrace: 0x4038f4e3 ... |<-CORRUPTED
```

`0x4038f4e6` 位于 Xtensa 窗口溢出/恢复处理器，不是 GUI 代码。包装函数还会打日志，调用链远重于必要的消息发送。

结论：**不要从 BLE 任务调用完整翻页包装函数。**

### 10.2 第二次：`a2` / `a10` 用错导致 LoadProhibited

第二版已经改成直接调用 `FUN_420f65b4`，但消息指针写进了 `a2`：

```text
Guru Meditation Error: Core 0 panic'ed (LoadProhibited)
PC: 0x40056fc0
EXCVADDR: 0x00000048
Backtrace: memcpy -> FUN_420f65b4 -> hook 0x422f4d51
```

`FUN_420f65b4` 从被调方 `a2`（调用方 `a10`）取消息指针，实际拿到 `0x48`，`memcpy` 读 `0x48` 崩溃。

结论：**消息指针必须放在调用方 `a10`。**

### 10.3 右包装函数调用目标的误判

早期曾把右包装函数 `0x420f7f78` 的尾部误判为调用 `0x420f657c` 的空 stub。原因是把 `0x420f7ff1` 处的字节 `25 5c fe` 放到了错误地址 `0x420f7fb9` 去解码。

实际右包装函数尾部是：

```text
0x420f7fea  movi.n a8, 0x4b
0x420f7fec  addi   a10, a1, 0x10
0x420f7fef  s32i.n a8, a1, 0x14
0x420f7ff1  call8  0x420f65b4
0x420f7ff4  retw.n
```

结论：**物理右翻页按键确实通过 `FUN_420f65b4` 发送 `0x4b`；反汇编时地址要对准指令边界。**

### 10.4 ESP 镜像 footer 对齐

ESP 镜像的 SHA-256 footer 必须 16 字节对齐。`build_patched_app_gui.py` 会在 footer 前补零，使：

```text
(footer_offset + 12) % 16 == 0
```

当前补丁镜像：

```text
segment 数据结束  0x75cfd0
对齐填充          4 字节
footer            0x75cfd4
checksum          0x79
validation hash   8b3a...
```

如果不做对齐，即使 segment 数据正确，`esptool image_info` 也会报 checksum/hash 无效。

### 10.5 旧 coredump

第一次和第二次失败版本的 coredump 可能仍在 `coredump` 分区（`0x10000`，大小 `0x10000`）。它不影响当前运行，但会干扰后续崩溃分析。

需要清理时：

```powershell
py -3 -m esptool --port COM5 erase_region 0x10000 0x10000
```

清理前如果还想分析旧崩溃，先读出来：

```powershell
py -3 -m esptool --port COM5 read_flash 0x10000 0x10000 extracts\coredump_old.bin
```

---

## 11. 限制、风险与注意事项

1. **版本绑定**：地址、机器码、文件偏移只对 `CC700Pro_1.9_V1.905-dirty` 成立。新固件必须重新定位、重新汇编。
2. **只改 app 分区**：没有改 bootloader、分区表、NVS、BLE 绑定和校准数据。
3. **BLE only**：本补丁只覆盖 BLE Di2 路径；ANT+ 路径未修改。
4. **长按未单独抓包**：代码已映射 `0x10 -> 0x99`，但最终日志没有单独捕获 `Evt=4`。建议补测。
5. **队列满时消息可能丢弃**：hook 使用非阻塞发送；队列满时不会阻塞 BLE 任务，但该次翻页可能丢失。
6. **旧 coredump**：失败版本的 coredump 可能仍在；不影响运行，可按需清理。
7. **完整备份敏感**：包含 NVS、BLE 密钥、校准数据；不要公开。
8. **不保证未来固件兼容**：原厂可能改变 Di2 协议、GUI 消息、队列布局、分区表，甚至启用 Secure Boot/Flash Encryption。
9. **刷写有风险**：即使有备份，也可能因硬件、线材、供电或操作失误导致设备无法启动；确认自己能承担风险。
10. **不要用其他设备的全盘备份**：会复制 BLE 身份和校准数据。

---

## 12. 一句话总结

通过把 Di2 BLE 按键注入点的空 stub 替换为 50 字节轻量 hook，将 `0x0e/0x0f/0x10` 映射为 GUI 翻页消息 `0x4b/0x99`，复用码表原有的 `RidePageSwitch` 路径，实现单按下一页、双击/长按上一页，并保持正常变速不变。

---

## 附录 A：当前版本地址表

### A.1 关键函数/全局

| 对象 | 地址 |
|---|---|
| BLE Di2 handler | `0x421e3968` |
| Di2 page-4 mapper | `0x4205c178` |
| 键值注入调用点 | `0x4205c32f` |
| 注入字面量槽 | `0x4203f520` |
| 原空 stub | `0x422e4138` |
| 左翻页包装 | `0x420f7ef4` |
| 右翻页包装 | `0x420f7f78` |
| 右包装发送尾部 | `0x420f7fea` |
| GUI 消息发送 | `0x420f65b4` |
| GUI 队列句柄 | `0x3c77aa2c` |
| GUI 队列创建 | `0x420f6594` |
| GUI 事件循环 | `0x420f5ed4` |
| GUI 键处理 | `0x4208e8e0` |

### A.2 补丁位置

| 位置 | VA | 文件偏移 | 大小 |
|---|---|---:|---:|
| 注入字面量 | `0x4203f520` | `0x48f520` | 4 |
| cave 基址 | `0x422f4d1c` | `0x744d1c` | 60 |
| hook 代码 | `0x422f4d24` | `0x744d24` | 50 |
| hook 填充 | `0x422f4d56` | `0x744d56` | 2 |
| segment 3 length 字段 | — | `0x45001c` | 4 |
| 镜像 footer | — | `0x75cfd4` | 44 |

### A.3 segment 表（补丁镜像）

| Segment | Load address | Length | File header | File data |
|---|---|---:|---:|---:|
| 0 DROM | `0x3c300020` | `0x441734` | `0x18` | `0x20` |
| 1 DRAM | `0x3fc9f700` | `0xb4e0` | `0x441754` | `0x44175c` |
| 2 IRAM | `0x40374000` | `0x33d4` | `0x44cc3c` | `0x44cc44` |
| 3 IROM | `0x42000020` | `0x2f4d38` | `0x450018` | `0x450020` |
| 4 IRAM | `0x403773d4` | `0x18270` | `0x744d58` | `0x744d60` |

### A.4 分区表（本机）

| 分区 | 偏移 | 大小 |
|---|---:|---:|
| nvs | `0x9000` | `0x4000` |
| otadata | `0xd000` | `0x2000` |
| phy_init | `0xf000` | `0x1000` |
| coredump | `0x10000` | `0x10000` |
| ota_0 | `0x20000` | `0x7d0000` |
| ota_1 | `0x7f0000` | `0x7d0000` |

> 新固件可能改变分区表。每次升级后用启动日志或 `partition_table` 重新确认，不要长期依赖这张表。

---

## 附录 B：当前 hook 字节

```text
366100 a2a099 b2a04b 82a00e 8082c0 c2a003 c7b81a 80ab83
a26105 82a000 826104 826106 826107 a2c110 81f3ff e00800
1df0
```

长度：50 字节。

逐指令：

| 偏移 | 字节 | 汇编 |
|---:|---|---|
| +0x00 | `36 61 00` | `entry a1, 0x30` |
| +0x03 | `a2 a0 99` | `movi a10, 0x99` |
| +0x06 | `b2 a0 4b` | `movi a11, 0x4b` |
| +0x09 | `82 a0 0e` | `movi a8, 0x0e` |
| +0x0c | `80 82 c0` | `sub a8, a2, a8` |
| +0x0f | `c2 a0 03` | `movi a12, 3` |
| +0x12 | `c7 b8 1a` | `bgeu a8, a12, 0x422f4d54` |
| +0x15 | `80 ab 83` | `moveqz a10, a11, a8` |
| +0x18 | `a2 61 05` | `s32i a10, a1, 0x14` |
| +0x1b | `82 a0 00` | `movi a8, 0` |
| +0x1e | `82 61 04` | `s32i a8, a1, 0x10` |
| +0x21 | `82 61 06` | `s32i a8, a1, 0x18` |
| +0x24 | `82 61 07` | `s32i a8, a1, 0x1c` |
| +0x27 | `a2 c1 10` | `addi a10, a1, 0x10` |
| +0x2a | `81 f3 ff` | `l32r a8, 0x422f4d1c` |
| +0x2d | `e0 08 00` | `callx8 a8` |
| +0x30 | `1d f0` | `retw.n` |

> 偏移是相对 hook 起始地址 `0x422f4d24` 的字节偏移；不是绝对地址。

---

## 附录 C：串口日志关键字

| 关键字 | 含义 |
|---|---|
| `Di2p4` | Di2 page-4 数据 |
| `Ch1Pos=1,Ass=0,Evt=1` | 左上手单按 |
| `Evt=2` | 双击 |
| `Evt=4` | 长按 |
| `Get ShftBtnEvent:2-1-0-1` | 单按事件 |
| `Get ShftBtnEvent:2-1-0-2` | 双击事件 |
| `Get ShftBtnEvent:2-1-0-4` | 长按事件 |
| `Recv GUI event, src:0 type:75` | GUI 收到下一页键 `0x4b` |
| `Recv GUI event, src:0 type:153` | GUI 收到上一页键 `0x99` |
| `RidePageSwitch called` | 页码切换被调用 |
| `Guru Meditation Error` | 崩溃 |
| `LoadProhibited` | 非法内存访问 |
| `rst:0x...` | 重启原因 |

PowerShell 去 ANSI 颜色码：

```powershell
$t = Get-Content -Raw -Encoding UTF8 notes\serial.log
$t = $t -replace "`e\[[0-9;]*m", ''
$t -split "`r?`n" | Select-String 'Di2p4|Get ShftBtnEvent|Recv GUI event|RidePageSwitch|Guru|LoadProhibited'
```

---

## 附录 D：命令速查

```powershell
# 端口/芯片信息
py -3 -m esptool --port COM5 flash_id

# 构建补丁镜像
py -3 scripts\build_patched_app_gui.py

# 校验镜像
py -3 -m esptool image_info extracts\ota_0_app_di2_gui.bin

# 备份完整 flash
py -3 -m esptool --port COM5 --baud 921600 read_flash 0x0 0x1000000 dumps\backup_<日期>.bin

# 读回 app 分区
py -3 -m esptool --port COM5 --baud 921600 read_flash 0x20000 0x7d0000 extracts\ota_0_app_<版本>.bin

# 刷写补丁到 ota_0
py -3 -m esptool --port COM5 --baud 921600 write_flash 0x20000 extracts\ota_0_app_di2_gui.bin

# 恢复原厂 app 到 ota_0
py -3 -m esptool --port COM5 --baud 921600 write_flash 0x20000 extracts\ota_0_app.bin

# 恢复原厂 app 到两个 OTA 槽
py -3 -m esptool --port COM5 --baud 921600 write_flash 0x20000 extracts\ota_0_app.bin 0x7f0000 extracts\ota_0_app.bin

# 完整 16 MB 恢复
py -3 -m esptool --port COM5 --baud 921600 write_flash 0x0 dumps\cc700pro_flash_16MB_v1.905_20261019.bin

# 串口抓包（自动重连）
py -3 scripts\capture_serial_reconnect.py COM5 1800 notes\serial_<日期>.log

# 清理旧 coredump
py -3 -m esptool --port COM5 erase_region 0x10000 0x10000
```

> 所有示例中的 `COM5` 都要替换成实际端口；所有地址/偏移只对本文注明的固件版本成立。
