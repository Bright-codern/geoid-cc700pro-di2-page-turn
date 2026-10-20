# Di2 BLE → GUI 翻页链路（V1.905）

本文只记录 Di2 按键到 GUI 翻页的静态链路和实机证据，不包含云端接口、
鉴权、NVS 或其他与翻页无关的逆向内容。

## 1. 设备与镜像

- 设备：GEOID CC700 Pro，ESP32-S3，16 MB flash，8 MB PSRAM。
- 固件：`CC700Pro_1.9_V1.905-dirty`。
- app 分区：`ota_0` 位于 `0x20000`，大小 `0x7d0000`。
- 原厂 app：8,192,000 字节，checksum `0xda`。
- 补丁 app：8,192,000 字节，checksum `0x79`，SHA-256
  `abaff7dd921aa6b3a64986c05f988f746d1d658084d72f370c8b4214c859bc03`。

`esptool image-info` 的补丁镜像布局：

| Segment | Length | Load addr | File offset | 类型 |
|---|---:|---|---:|---|
| 0 | `0x441734` | `0x3c300020` | `0x00000018` | DROM |
| 1 | `0x0b4e0` | `0x3fc9f700` | `0x00441754` | DRAM |
| 2 | `0x033d4` | `0x40374000` | `0x0044cc3c` | IRAM |
| 3 | `0x2f4d38` | `0x42000020` | `0x00450018` | IROM |
| 4 | `0x18270` | `0x403773d4` | `0x00744d58` | IRAM |

## 2. BLE 侧

已知调用链：

```text
BLE_Di2_Handler            0x421e3968
  -> Di2 page-4 mapper     FUN_4205c178
     -> key injector       0x4205c32f
        l32r a8, 0x4203f520
        callx8 a8
```

page-4 按键事件与键值：

| 串口事件 | 含义 | 键值 |
|---|---|---:|
| `Get ShftBtnEvent:2-1-0-1` | 单按 | `0x0e` |
| `Get ShftBtnEvent:2-1-0-2` | 双击 | `0x0f` |
| `Get ShftBtnEvent:2-1-0-4` | 长按 | `0x10` |
| `Get ShftBtnEvent:2-1-0-0` | 松开 | 不处理 |

原厂字面量 `0x4203f520` 指向 `0x422e4138`，函数体只有：

```asm
entry a1, 0x10
movi.n a2, 0
retw.n
```

所以原厂固件能收到 Di2 按键事件，但注入器调用的是空 stub，界面没有任何
反应。这是“设备无法蓝牙翻页”的直接原因。

调用点 `0x4205c32f` 把键值放在 `a10`；由于 Xtensa 窗口化 ABI 的窗口旋转，
hook 入口看到的是 `a2`。因此 hook 从 `a2` 读键值。

## 3. GUI 侧

左侧翻页包装函数 `KeyFunc_SwitchPageHorLeft` `0x420f7ef4` 和右侧
`KeyFunc_SwitchPageHorRight` `0x420f7f78` 都会构造 12 字节消息并调用
`FUN_420f65b4`。

消息布局（4 个小端 u32）：

```text
message[0] = 0
message[1] = key code      ; 0x4b = next, 0x99 = previous
message[2] = 0
message[3] = 0
```

`FUN_420f65b4(param_1)` 把 12 字节复制到自己的栈，然后调用
`FUN_4205158c(queue, buffer, 0)`（`xQueueGenericSend`）。GUI 队列由
`FUN_420f6594` 创建：`xQueueCreate(0x32, 0xc, 1)`，即 50 个 12 字节项。

GUI 事件处理 `FUN_4208e8e0`：

- `0x4b` → `RidePageSwitch(0)`（下一页）
- `0x99` → `RidePageSwitch(1)`（上一页）

最终串口表现为 `Recv GUI event, src:0 type:75`（`0x4b`）和
`src:0 type:153`（`0x99`）。

## 4. 补丁

### 4.1 注入点

| 项目 | 值 |
|---|---|
| 字面量 VA | `0x4203f520` |
| 字面量文件偏移 | `0x48f520` |
| 原值 | `0x422e4138`（字节 `38 41 2e 42`） |
| 新值 | `0x422f4d24`（字节 `24 4d 2f 42`） |

### 4.2 cave

```text
0x422f4d1c  +0x00  u32  0x420f65b4   ; GUI 消息发送函数
0x422f4d20  +0x04  u32  0             ; 保留
0x422f4d24  +0x08  hook code          ; 50 字节
0x422f4d56  +0x3a  padding            ; 2 字节
0x422f4d58  +0x3c  segment 4 header   ; 原 segment 4 后移到这里
```

cave 位于 IROM segment 3 末尾。segment 3 的长度从 `0x2f4cfc` 增加到
`0x2f4d38`；segment 4 的文件偏移从 `0x744d1c` 后移到 `0x744d58`。

### 4.3 hook

```asm
entry   a1, 0x30              ; 保存区 a1+0x20..0x2f，消息区 a1+0x10..0x1b
movi    a10, 0x99             ; 默认上一页
movi    a11, 0x4b             ; 下一页
movi    a8, 0x0e
sub     a8, a2, a8            ; a8 = key - 0x0e
movi    a12, 3
bgeu    a8, a12, done         ; 只接受 0x0e/0x0f/0x10
moveqz  a10, a11, a8          ; key == 0x0e 时选 0x4b
s32i    a10, a1, 0x14         ; message[1] = GUI key
movi    a8, 0
s32i    a8, a1, 0x10          ; message[0] = 0
s32i    a8, a1, 0x18          ; message[2] = 0
s32i    a8, a1, 0x1c          ; 对齐填充
addi    a10, a1, 0x10         ; 消息指针放在调用方 a10
l32r    a8, 0x422f4d1c        ; FUN_420f65b4
callx8  a8
done:
retw.n
```

机器码（50 字节）：

```text
366100 a2a099 b2a04b 82a00e 8082c0 c2a003 c7b81a 80ab83
a26105 82a000 826104 826106 826107 a2c110 81f3ff e00800
1df0
```

## 5. 两个已经踩过的坑

### 5.1 不要在 BLE 任务里调用完整包装函数

第一版把 `0x0e` 路由到 `KeyFunc_SwitchPageHorRight`，`0x0f/0x10` 路由到
`KeyFunc_SwitchPageHorLeft`。按下 Di2 按钮后出现：

```text
Guru Meditation Error: Core 0 panic'ed (Double exception)
PC: 0x4038f4e6
Backtrace: 0x4038f4e3 ... |<-CORRUPTED
```

`0x4038f4e6` 位于 Xtensa 窗口溢出/恢复处理器，不是 GUI 代码。包装函数还会
打日志、增加 `0x40` 栈帧，从 BLE 回调调用会耗尽/重叠窗口溢出区。最终改为
不调用包装函数，直接构造消息并调用轻量的 `FUN_420f65b4`。

### 5.2 消息指针必须在 `a10`

第二版 hook 使用了 `addi a2, a1, 0x10`，被调方 `FUN_420f65b4` 实际从
callee `a2`（caller `a10`）读参数，结果读到 `0x48`：

```text
PC: 0x40056fc0 (memcpy)
EXCVADDR: 0x00000048
Backtrace: memcpy -> FUN_420f65b4 -> hook 0x422f4d51 -> injector 0x4205c32f
```

改成 `addi a10, a1, 0x10` 后通过。物理右侧翻页包装函数的尾部也是这么写的。

## 6. 实机结果

- 单按：`0x0e` → `0x4b` → `Recv GUI event, src:0 type:75` → 下一页。
- 双击：`0x0f` → `0x99` → `src:0 type:153` → 上一页。
- 长按：代码映射 `0x10` → `0x99`；最终日志没有单独捕获 `Evt=4`。
- 连续单按页码 `0 -> 1 -> 2 -> 3`；连续双击 `3 -> 2 -> 1 -> 0`。
- 最终抓包中 `Guru` / `panic` / `LoadProhibited` 为 0，正常变速数据继续更新。

脱敏日志见 `notes/serial_di2_gui_test4_excerpt.log`。
